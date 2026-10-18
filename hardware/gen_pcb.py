#!/usr/bin/env python3
"""Generate the TinyUPS PCB from the netlist.

* Reads the KiCad netlist (`build/tinyups.net`) for components, footprints and
  net connectivity.
* Builds a 4-layer board, assigns nets to pads, and places the footprints with
  a simple shelf-packing algorithm (guarantees no courtyard overlap).
* Board outline is sized to the packed placement, capped to the ATX bay.

Routing is done separately with freerouting (see hardware/README.md).

Run:  /opt/eda/venv/bin/python hardware/gen_pcb.py
"""
from __future__ import annotations

import math
import os
import re
import sys

import pcbnew

from blocks import (CORRIDOR_MM, CORRIDOR_TARGET_MM, PREFIXED_BLOCKS as BLOCKS,
                    kind as _kind, label)  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NETLIST = os.path.join(ROOT, "build", "tinyups.net")
OUT = os.path.join(HERE, "tinyups.kicad_pcb")
FP_ROOT = "/usr/share/kicad/footprints"

MARGIN = 3.0          # mm board margin around placement
GAP = 1.5             # mm gap between footprints
MAX_W, MAX_H = 150.0, 140.0   # ATX-bay cap (150 x 140)

# ---- floorplan (power-path-first) ----------------------------------------- #
# Back (top, small y) = input; front (bottom) = output.  A vertical power
# corridor down the centre carries the power path (blocks A+B+D); the charger
# (C) and the battery AFE (E) branch off to the right; the MCU (F) sits on the
# left.  Connectors are anchored on the edges first (see ANCHORS).
BOARD_W, BOARD_H = 150.0, 140.0
CORRIDOR_HALF = 25.0                  # half-width of the power corridor
ANCHORS = {                           # ref -> (x, y) centre, mm
    "J1": (BOARD_W / 2, 11.0),               # XT60 input   — back centre
    "J2": (BOARD_W / 2, BOARD_H - 11.0),     # XT30 output  — front centre
    "J3": (18.0, BOARD_H - 11.0),            # USB header   — front left
    "J4": (38.0, BOARD_H - 11.0),            # SWD header   — front, left of centre
    "J5": (BOARD_W - 14.0, BOARD_H - 11.0),  # fan header   — front right
    "J6": (BOARD_W - 40.0, BOARD_H - 12.0),  # PACK terminal — front
    "J7": (BOARD_W - 62.0, BOARD_H - 15.0),  # cell sense    — front
}
ZONES = {                             # group -> (x0, y0, x1, y1) mm
    "SPINE": (48.0, 20.0, 102.0, 122.0),  # power path, on the centreline
    "L": (4.0, 20.0, 46.0, 122.0),        # signal: A/B/D/F
    "R": (104.0, 20.0, BOARD_W - 4.0, 122.0),  # signal: C/E
}


# --------------------------------------------------------------------------- #
# tiny s-expression parser
# --------------------------------------------------------------------------- #
def tokenize(s: str):
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and s[j] != '"':
                if s[j] == "\\":
                    j += 1
                buf.append(s[j])
                j += 1
            yield ("str", "".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()"':
                j += 1
            yield ("sym", s[i:j])
            i = j


def parse(s: str):
    toks = list(tokenize(s))
    pos = 0

    def rd():
        nonlocal pos
        t = toks[pos]
        pos += 1
        if t == "(":
            lst = []
            while toks[pos] != ")":
                lst.append(rd())
            pos += 1
            return lst
        return t[1]

    return rd()


def _find_all(node, key):
    out = []
    if isinstance(node, list) and node and node[0] == key:
        out.append(node)
    if isinstance(node, list):
        for c in node:
            out.extend(_find_all(c, key))
    return out


# --------------------------------------------------------------------------- #
def add_plane_keepout(board, x0, y0, x1, y1, layer=pcbnew.In1_Cu,
                      inset=0.5) -> None:
    """Rule area: no copper *tracks* on a plane layer.

    NOT WIRED IN — see the call site in `main()` and docs/history/0013.  The
    intent is sound: the inner GND plane is a surface, not routing space, and
    traces crossing it chop it into islands that cost the return path its
    ampacity (177 tracks on `In1.Cu` left the 20 A return with a 9.38 mm min cut
    and 5 islands, docs/history/0012).  But KiCad exports this as
    `(wire_keepout …)` in the Specctra DSN, and freerouting applies a keepout to
    *every* object on that layer — including the pad of a through via.  With the
    one via padstack KiCad emits (`Via[0-3]`, all four layers) that blocks every
    layer change: 0 vias, 106 unconnected, against 237 vias / 15 unconnected
    without it.

    To use it, the DSN must also offer a via whose padstack skips the plane
    (physically a through via with an antipad at `In1.Cu`), or the guard must be
    scoped to a corridor rather than the whole layer.
    """
    ka = pcbnew.ZONE(board)
    ka.SetIsRuleArea(True)
    ka.SetDoNotAllowTracks(True)
    ka.SetDoNotAllowVias(False)
    ka.SetDoNotAllowCopperPour(False)
    ka.SetDoNotAllowPads(False)
    ka.SetDoNotAllowFootprints(False)
    ka.SetLayer(layer)
    ka.SetZoneName("no tracks on the GND plane")
    o = ka.Outline()
    o.NewOutline()
    for px, py in ((x0 + inset, y0 + inset), (x1 - inset, y0 + inset),
                   (x1 - inset, y1 - inset), (x0 + inset, y1 - inset)):
        o.Append(pcbnew.FromMM(px), pcbnew.FromMM(py))
    board.Add(ka)


def main() -> int:
    if not os.path.exists(NETLIST):
        print("error: run `make netlist` first", file=sys.stderr)
        return 1
    tree = parse(open(NETLIST).read())

    # components
    comps = {}
    for c in _find_all(tree, "comp"):
        ref = next(x for x in c if isinstance(x, list) and x[0] == "ref")[1]
        val = next((x[1] for x in c if isinstance(x, list) and x[0] == "value"), "")
        fp = next((x[1] for x in c if isinstance(x, list) and x[0] == "footprint"), "")
        comps[ref] = {"value": val, "fp": fp}

    # nets: netname -> [(ref, pad)]
    pin_net = {}
    for net in _find_all(tree, "net"):
        name = next(x[1] for x in net if isinstance(x, list) and x[0] == "name")
        for node in net:
            if isinstance(node, list) and node[0] == "node":
                ref = next(x[1] for x in node if isinstance(x, list) and x[0] == "ref")
                pad = next(x[1] for x in node if isinstance(x, list) and x[0] == "pin")
                pin_net[(ref, pad)] = name

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)

    # design rules (also feeds the Specctra export): JLCPCB standard 5 mil.
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = pcbnew.FromMM(0.127)
    ds.m_MinClearance = pcbnew.FromMM(0.127)
    ds.m_ViasMinSize = pcbnew.FromMM(0.6)
    ds.m_ViasMinDrill = pcbnew.FromMM(0.3)
    try:
        nc = ds.GetDefault()
        nc.SetTrackWidth(pcbnew.FromMM(0.3))
        nc.SetClearance(pcbnew.FromMM(0.2))
        nc.SetViaDiameter(pcbnew.FromMM(0.8))
        nc.SetViaDrill(pcbnew.FromMM(0.4))
    except Exception as e:  # pragma: no cover
        print("netclass note:", e)

    # load footprints
    loaded = []
    for ref, info in comps.items():
        lib, name = info["fp"].split(":", 1)
        fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib + ".pretty"), name)
        if fp is None:
            print(f"error: footprint not found {info['fp']} for {ref}", file=sys.stderr)
            return 2
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        bb = fp.GetBoundingBox()
        w, h = bb.GetWidth(), bb.GetHeight()
        if _kind(ref) == "J":            # connectors: extra clearance
            w += pcbnew.FromMM(8)
            h += pcbnew.FromMM(8)
        loaded.append([ref, fp, w, h])

    # ---- block-aware placement ------------------------------------------- #
    # group parts by functional block (single source: hardware/blocks.py, which
    # also defines the block-prefixed references)
    ref_block = {r: b for b, refs in BLOCKS.items() for r in refs}

    def shelf(items, maxw, gap=GAP, sort=True):
        """pack (ref, fp, w, h) into rows; return placed [(ref, fp, cx, cy)] + size."""
        if sort:
            items = sorted(items, key=lambda t: -t[3])
        x = y = 0.0
        row_h = uw = uh = 0.0
        out = []
        for ref, fp, w, h in items:
            wmm, hmm = pcbnew.ToMM(w), pcbnew.ToMM(h)
            if x > 0 and x + wmm > maxw:
                y += row_h + gap
                x = 0.0
                row_h = 0.0
            out.append((ref, fp, x + wmm / 2, y + hmm / 2))
            x += wmm + gap
            row_h = max(row_h, hmm)
            uw = max(uw, x)
            uh = max(uh, y + row_h)
        return out, uw, uh

    by_block: dict[str, list] = {}
    for item in loaded:
        by_block.setdefault(ref_block.get(item[0], "X"), []).append(item)

    # Stage 2: decoupling-aware ordering. Within a block, emit each IC followed
    # by the caps that share a power net with it, so the shelf packs the caps
    # right next to the IC (short decap distance) before other parts.
    POWER_NETS = {"+3V3", "VIN_SYS", "VBAT", "VOUT12", "N_DVDD", "+12V_IN",
                  "N_REG1", "N_REG2", "N_REG18", "VCC", "REGN", "VDDA"}
    ref_nets: dict[str, set] = {}
    for (r, _p), nm in pin_net.items():
        ref_nets.setdefault(r, set()).add(nm.lstrip("/"))

    def order_block(items):
        by_ref = {it[0]: it for it in items}
        ics = sorted([r for r in by_ref if _kind(r) == "U"],
                     key=lambda r: -by_ref[r][3])
        caps = sorted([r for r in by_ref if _kind(r) == "C"],
                      key=lambda r: -by_ref[r][3])
        used, out = set(), []
        for ic in ics:
            out.append(by_ref[ic]); used.add(ic)
            icp = ref_nets.get(ic, set()) & POWER_NETS
            for c in caps:
                if c not in used and (ref_nets.get(c, set()) & icp):
                    out.append(by_ref[c]); used.add(c)
        for it in sorted(items, key=lambda t: -t[3]):
            if it[0] not in used:
                out.append(it)
        return out

    def block_units(items):
        """Group each IC with its decoupling caps, so a group stays together."""
        by_ref = {it[0]: it for it in items}
        ics = sorted([r for r in by_ref if _kind(r) == "U"],
                     key=lambda r: -by_ref[r][3])
        caps = sorted([r for r in by_ref if _kind(r) == "C"],
                      key=lambda r: -by_ref[r][3])
        used, units = set(), []
        for ic in ics:
            grp = [by_ref[ic]]; used.add(ic)
            icp = ref_nets.get(ic, set()) & POWER_NETS
            for c in caps:
                if c not in used and (ref_nets.get(c, set()) & icp):
                    grp.append(by_ref[c]); used.add(c)
            units.append(grp)
        units.extend([[it] for it in sorted(items, key=lambda t: -t[3])
                      if it[0] not in used])
        return units

    # ---- floorplan placement (power-path-first) --------------------------- #
    from power_map import component_is_power
    items_by_ref = {it[0]: it for it in loaded}

    def ref_power(r):
        return component_is_power(r, comps[r]["value"], ref_nets.get(r, set()))

    # ---- orient power parts ------------------------------------------------ #
    # Each power part's "input" pad is the one on the net closest to the source
    # (shallower in the net graph).  Rotate, snapped to 90 deg, so the input
    # pad faces the power rail: east for parts left of the corridor, west for
    # parts right of it.  2-pad parts (R, L) therefore only take 0 or 180.
    import math
    from collections import deque
    from power_spec import DESIGN_CURRENT as _DC
    POWER_NET_SET = set(_DC)
    LEFT_BLOCKS = {"A", "B", "D", "F"}     # 1,3,5,6 -> left of the path

    def pad_net(ref, pad):
        return pin_net.get((ref, pad.GetNumber()), "").lstrip("/")

    def power_pads(ref, fp):
        return [p for p in fp.Pads() if pad_net(ref, p) in POWER_NET_SET]

    nets_of: dict[str, set] = {}
    comps_of: dict[str, set] = {}
    for ref, fp, *_ in loaded:
        for p in fp.Pads():
            nm = pad_net(ref, p)
            if nm in POWER_NET_SET:
                nets_of.setdefault(ref, set()).add(nm)
                comps_of.setdefault(nm, set()).add(ref)
    depth: dict[str, int] = {"+12V_IN": 0}
    q = deque(["+12V_IN"])
    while q:
        n = q.popleft()
        for c in comps_of.get(n, ()):
            for m in nets_of.get(c, ()):
                if m not in depth:
                    depth[m] = depth[n] + 1
                    q.append(m)

    def snap90(a):
        return round(a / 90.0) * 90.0

    # nets carried by the central pour (rails).  A power pad on one of these
    # faces the corridor; a pad on a local node faces its partner part instead.
    POUR_NETS = {"+12V_IN", "N_AF", "VIN_LM", "VIN_SYS", "VBAT", "VSYS",
                 "VOUT12", "VBUS", "N_ACN", "N_CATH"}

    # chain depth from the *input* rail only (+12V_IN), so the column index is
    # monotonic from input to output: rail -> FET -> node -> L -> node -> FET.
    comp_depth: dict[str, int] = {
        c: 1 + min((depth.get(n, 99) for n in ns), default=99)
        for c, ns in nets_of.items()}

    for ref, fp, *_ in loaded:
        if not ref_power(ref):
            continue
        pp = power_pads(ref, fp)
        if len(pp) < 2:
            continue
        pp.sort(key=lambda p: depth.get(pad_net(ref, p), 99))
        in_pad = pp[0]
        dx = in_pad.GetPosition().x - fp.GetPosition().x
        dy = in_pad.GetPosition().y - fp.GetPosition().y
        ang = math.degrees(math.atan2(dy, dx))
        if pad_net(ref, in_pad) in POUR_NETS:
            # input on the rail -> face the pour (east left / west right)
            target = 0.0 if ref_block.get(ref) in LEFT_BLOCKS else 180.0
        else:
            # input on a local node -> point the upstream pad up (toward the
            # previous part); screen y is down, so "up" is -90 deg
            target = -90.0
        fp.SetOrientationDegrees(snap90(target - ang))

    # ---- staged placement -------------------------------------------------- #
    # Stage 1: connectors + reserved power corridor (silkscreen box).
    # Stage 2: power components, in path order, flanking the corridor.
    # Stage 3: everything else fills the remaining space.
    from collections import deque
    STAGE = int(os.environ.get("PCB_STAGE", "3"))
    CW = CORRIDOR_TARGET_MM
    cx = BOARD_W / 2
    cor_x0, cor_x1 = cx - CW / 2, cx + CW / 2
    X0, X1 = 4.0, BOARD_W - 4.0
    ANCHOR_REFS = {label(r) for r in ANCHORS}
    LEFT_BLOCKS = {"A", "B", "D", "F"}     # 1,3,5,6 -> left of the path
    RIGHT_BLOCKS = {"C", "E"}              # 2,4     -> right of the path

    def side_of(ref):
        return "L" if ref_block.get(ref) in LEFT_BLOCKS else "R"

    def place(ref, x, y):
        fp = items_by_ref[ref][1]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        board.Add(fp)

    def add_rect(x0, y0, x1, y1):
        r = pcbnew.PCB_SHAPE(board)
        r.SetShape(pcbnew.SHAPE_T_RECT)
        r.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
        r.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        r.SetLayer(pcbnew.F_SilkS)
        r.SetWidth(pcbnew.FromMM(0.25))
        board.Add(r)

    # stage 1: connectors + the reserved corridor
    add_rect(cor_x0, 20.0, cor_x1, 120.0)
    for ref, (ax, ay) in ANCHORS.items():
        if label(ref) in items_by_ref:
            place(label(ref), ax, ay)

    # ---- power components, in path order (BFS over shared power nets) ------ #
    by_net: dict[str, set] = {}
    for ref, fp, *_ in loaded:
        if ref in ANCHOR_REFS:
            continue
        for p in fp.Pads():
            nm = pad_net(ref, p)
            if nm in POWER_NET_SET:
                by_net.setdefault(nm, set()).add(ref)
    adj: dict[str, set] = {}
    for refs in by_net.values():
        for r in refs:
            adj.setdefault(r, set()).update(refs - {r})

    order, seen = [], set()
    q = deque([label("J1")])
    while q:
        r = q.popleft()
        if r in seen:
            continue
        seen.add(r)
        if r not in ANCHOR_REFS and ref_power(r):
            order.append(r)
        for nb in sorted(adj.get(r, [])):
            if nb not in seen:
                q.append(nb)
    for ref, fp, *_ in loaded:
        if ref not in ANCHOR_REFS and ref_power(ref) and ref not in order:
            order.append(ref)

    # ---- stage 2: power components (PoC gradient-descent placement) -------- #
    # Place the fixed connectors, then each power part in path order. For each:
    # rotate (done above), drop it below the previous part, then line-search its
    # position along the direction of the target pad: step, measure the routed
    # length (grid A*), keep if shorter, reverse + halve if longer or illegal.
    GRID = float(os.environ.get("PP_GRID", "2.0"))
    CLEAR = float(os.environ.get("PP_CLEAR", "2.0"))
    TARGET = float(os.environ.get("PP_TARGET", "2.0"))
    MINSTEP = float(os.environ.get("PP_MINSTEP", "2.0"))
    BRANCH = float(os.environ.get("PP_BRANCH", "10.0"))
    MAXSTEPS = int(os.environ.get("PP_MAXSTEPS", "20"))

    def bbox(fp):
        bb = fp.GetBoundingBox(False, False)
        return (pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))

    def hits(a, b, m):
        return not (a[2] + m < b[0] or b[2] + m < a[0]
                    or a[3] + m < b[1] or b[3] + m < a[1])

    def pad_xy(fp, pad):
        p = pad.GetPosition()
        return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

    def in_pad(ref, fp):
        pp = power_pads(ref, fp)
        if not pp:
            return None
        pp.sort(key=lambda p: depth.get(pad_net(ref, p), 99))
        return pp[0]

    placed_boxes: list = []
    for ref, (ax, ay) in ANCHORS.items():
        it = items_by_ref.get(label(ref))
        if it:
            placed_boxes.append(bbox(it[1]))

    def legal(fp, x, y):
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        b = bbox(fp)
        if b[0] < 2 or b[1] < 2 or b[2] > BOARD_W - 2 or b[3] > BOARD_H - 2:
            return False
        return not any(hits(b, q, CLEAR) for q in placed_boxes)

    def blocked():
        cells = set()
        for (x0, y0, x1, y1) in placed_boxes:
            for i in range(int((x0 - CLEAR) / GRID), int((x1 + CLEAR) / GRID) + 2):
                for j in range(int((y0 - CLEAR) / GRID), int((y1 + CLEAR) / GRID) + 2):
                    cells.add((i, j))
        return cells

    import heapq

    def route_len(p, q):
        blk = blocked()
        start = (int(p[0] / GRID), int(p[1] / GRID))
        goal = (int(q[0] / GRID), int(q[1] / GRID))
        g = {start: 0.0}
        heap = [(0.0, start)]
        while heap:
            _f, cur = heapq.heappop(heap)
            if cur == goal:
                return g[cur] * GRID
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if not (dx or dy):
                        continue
                    nb = (cur[0] + dx, cur[1] + dy)
                    if nb in blk or not (0 <= nb[0] <= BOARD_W / GRID
                                         and 0 <= nb[1] <= BOARD_H / GRID):
                        continue
                    ng = g[cur] + (1.4142 if dx and dy else 1.0)
                    if ng < g.get(nb, 1e9):
                        g[nb] = ng
                        heapq.heappush(heap, (ng + math.hypot(
                            nb[0] - goal[0], nb[1] - goal[1]), nb))
        return None

    if STAGE >= 2:
        prev_ref = label("J1")
        prev_pad = None
        COLW = 11.0
        col_y: dict = {}                            # (side, depth) -> y cursor
        for ref in order:
            fp = items_by_ref[ref][1]
            my_pad = in_pad(ref, fp)
            bb = fp.GetBoundingBox(False, False)
            w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
            left = side_of(ref) == "L"
            side = "L" if left else "R"
            dep = min(comp_depth.get(ref, 1), 6)     # column = chain depth
            key = (side, dep)
            # branch/merge gap: shared net fans out to >=3 power parts
            shared = nets_of.get(ref, set()) & nets_of.get(prev_ref, set())
            branch = any(len(comps_of.get(n, ())) >= 3 for n in shared)
            gap = BRANCH if branch else TARGET
            y = col_y.get(key, 22.0) + gap + h / 2
            x = (cor_x0 - 2.0 - w / 2 - (dep - 1) * COLW) if left \
                else (cor_x1 + 2.0 + w / 2 + (dep - 1) * COLW)
            # legalise downward
            while not legal(fp, x, y) and y < BOARD_H - 4:
                y += GRID
            # target = previous part's pad on the shared net (or its in-pad)
            tgt = None
            if prev_pad is not None:
                tgt = pad_xy(items_by_ref[prev_ref][1], prev_pad)
            if tgt is None:
                tgt = pad_xy(items_by_ref[prev_ref][1], in_pad(prev_ref,
                             items_by_ref[prev_ref][1]))
            # 2D hill-climb: at each step try the four grid directions and move
            # to whichever shortens the routed length most; else halve the step
            best_len = route_len(pad_xy(fp, my_pad), tgt) if (my_pad and tgt) else None
            step = (math.hypot(tgt[0] - x, tgt[1] - y) / 3.0) if tgt else 0.0
            cur = [x, y]
            DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
            for _ in range(MAXSTEPS):
                if step < MINSTEP or best_len is None:
                    break
                move = None
                for dxn, dyn in DIRS:
                    nx, ny = cur[0] + dxn * step, cur[1] + dyn * step
                    if not legal(fp, nx, ny):
                        continue
                    l = route_len(pad_xy(fp, my_pad), tgt)
                    if l is not None and l < best_len - 1e-6:
                        if move is None or l < move[0]:
                            move = (l, nx, ny)
                if move:
                    best_len, cur = move[0], [move[1], move[2]]
                else:
                    step /= 2.0
            legal(fp, cur[0], cur[1])
            board.Add(fp)
            placed_boxes.append(bbox(fp))
            col_y[key] = max(col_y.get(key, 22.0), cur[1] + h / 2)
            prev_ref, prev_pad = ref, my_pad
        left_y = max((v for (s, _d), v in col_y.items() if s == "L"), default=22.0)
        right_y = max((v for (s, _d), v in col_y.items() if s == "R"), default=22.0)

    # ---- stage 3: everything else fills the remaining space ---------------- #
    if STAGE >= 3:
        PW = 26.0                               # power strip width (for the fill)
        rest = [it for it in loaded
                if it[0] not in ANCHOR_REFS and not ref_power(it[0])]
        left = order_block([it for it in rest if side_of(it[0]) == "L"])
        right = order_block([it for it in rest if side_of(it[0]) == "R"])
        lw = cor_x0 - 2.0 - PW - X0
        rw = X1 - (cor_x1 + 2.0 + PW)
        lplaced, _a, lh = shelf(left, lw)
        rplaced, _b, rh = shelf(right, rw)
        for ref, fp, px, py in lplaced:
            place(ref, X0 + px, 22.0 + py)
        for ref, fp, px, py in rplaced:
            place(ref, cor_x1 + 2.0 + PW + px, 22.0 + py)
        left_y = max(left_y, 22.0 + lh)
        right_y = max(right_y, 22.0 + rh)
    if STAGE >= 2 and max(left_y, right_y) > BOARD_H - 14:
        print(f"  WARNING: parts reach {max(left_y, right_y):.1f} mm "
              f"(board {BOARD_H})")

    # nets -> pads
    netcache = {}
    for ref, fp, *_ in loaded:
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            name = pin_net.get(key)
            if not name:
                continue
            if name not in netcache:
                n = pcbnew.NETINFO_ITEM(board, name)
                board.Add(n)
                netcache[name] = n
            pad.SetNet(netcache[name])

    # outline = the fixed floorplan board (0,0)-(BOARD_W,BOARD_H)
    x0, y0, x1, y1 = 0.0, 0.0, BOARD_W, BOARD_H
    for fp in board.GetFootprints():
        bb = fp.GetBoundingBox(False, False)          # body only, ignore text
        if (pcbnew.ToMM(bb.GetX()) < x0 or pcbnew.ToMM(bb.GetY()) < y0
                or pcbnew.ToMM(bb.GetRight()) > x1
                or pcbnew.ToMM(bb.GetBottom()) > y1):
            print(f"  WARNING: {fp.GetReference()} extends past the board edge")
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
    r.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    r.SetLayer(pcbnew.Edge_Cuts)
    r.SetWidth(pcbnew.FromMM(0.1))
    board.Add(r)
    bw, bh = x1 - x0, y1 - y0

    # planes: a solid GND plane on In1.Cu. In2.Cu is left as a signal layer
    # (a dedicated VIN_SYS plane cost a signal layer and the router perforated
    # it anyway — see docs). Power is carried as wide traces / pours instead.
    for netname, layer in (("GND", pcbnew.In1_Cu),):
        net = board.FindNet(netname) or board.FindNet("/" + netname)
        if net is None:
            print("warn: plane net not found:", netname)
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNetCode(net.GetNetCode())
        o = z.Outline()
        o.NewOutline()
        ins = 0.5
        for px, py in ((x0 + ins, y0 + ins), (x1 - ins, y0 + ins),
                       (x1 - ins, y1 - ins), (x0 + ins, y1 - ins)):
            o.Append(pcbnew.FromMM(px), pcbnew.FromMM(py))
        z.SetMinThickness(pcbnew.FromMM(0.25))
        try:
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        except Exception:
            pass
        board.Add(z)

    # NOTE: the high-current pours are added by hardware/pour_power.py on a
    # *loaded* board — in-memory, pad.GetPosition() still returns pre-placement
    # positions, so the corridor would be swept through the wrong points.

    # The GND plane layer is a plane, not routing space — but the guard is NOT
    # switched on here.  KiCad exports a rule area as (wire_keepout ...), and
    # freerouting blocks every via whose padstack touches that layer; with a
    # single through via (Via[0-3]) that is every via, so the board drops from
    # 237 vias / 15 unconnected to 0 vias / 106 unconnected (docs/history/0013).
    # It becomes usable once the DSN offers a via padstack that *skips* the
    # plane (F.Cu-In2.Cu-B.Cu, i.e. a through via with an antipad), or when the
    # guard is scoped to a corridor instead of the whole plane.
    # add_plane_keepout(board, x0, y0, x1, y1)

    # NOTE: zone filling is done separately (hardware/fill_zones.py); calling
    # ZONE_FILLER on the freshly-built board crashes in the pcbnew bindings.

    pcbnew.SaveBoard(OUT, board)
    print(f"wrote {OUT}")
    print(f"  {len(loaded)} footprints, {len(netcache)} nets, board {bw:.1f} x {bh:.1f} mm")
    if bw > MAX_W + 1 or bh > MAX_H + 1:
        print(f"  WARNING: board exceeds ATX cap {MAX_W}x{MAX_H} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
