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

import os
import re
import sys

import pcbnew

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
        if ref.startswith("J"):        # connectors: reserve extra clearance
            w += pcbnew.FromMM(8)
            h += pcbnew.FromMM(8)
        loaded.append([ref, fp, w, h])

    # ---- block-aware placement ------------------------------------------- #
    # group parts by functional block (same split as the schematic), lay each
    # block out in a sub-rectangle, then pack the block rectangles into rows.
    BLOCKS = {
        "A": {"J1", "F1", "D1", "R1", "R2", "R3", "R4", "R5", "C1", "R6", "R7", "Q1", "U1"},
        "B": {"U2", "Q2", "C2", "C3", "C4", "R8"},
        "C": {"U3", "Q3", "Q4", "Q5", "Q6", "L2", "R9", "R10", "C5", "C6", "C7",
              "C8", "R11", "R12", "R13", "R14", "R15", "R40", "C29", "C30",
              "C31", "R41", "C32", "R42", "C33", "R43", "R44"},
        "D": {"U4", "Q7", "Q8", "Q9", "Q10", "L3", "R16", "R17", "R18", "R19",
              "R20", "R21", "R22", "R23", "R24", "C9", "C10", "C11", "C12",
              "C13", "C14", "C15", "C16", "C17", "C18", "J2"},
        "E": {"U5", "Q11", "Q12", "R25", "Rf0", "Rf1", "Rf2", "Rf3", "Rf4",
              "Cf0", "Cf1", "Cf2", "Cf3", "Cf4", "C19", "C20", "C21", "C22",
              "C23", "R26", "R27", "R28", "R29", "R30", "R45", "R46",
              "J6", "J7"},
        "F": {"U6", "U7", "U8", "J3", "J4", "J5", "Y1", "R31", "R36", "R37",
              "R38", "R32", "R33", "R34", "R35", "D2", "D3", "D4", "D5",
              "C24", "C25", "C26", "C27", "C28"},
    }
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
        ics = sorted([r for r in by_ref if r.startswith("U")],
                     key=lambda r: -by_ref[r][3])
        caps = sorted([r for r in by_ref if r.startswith("C")],
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
        ics = sorted([r for r in by_ref if r.startswith("U")],
                     key=lambda r: -by_ref[r][3])
        caps = sorted([r for r in by_ref if r.startswith("C")],
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

    # ---- power-path bands ------------------------------------------------- #
    # Each functional stage is a horizontal band: its power-handling parts sit
    # on the centreline (in flow order) and its signal parts flank them, so the
    # power parts cluster on the path without separating them from their
    # decoupling/compensation parts.
    BANDS = [["A"], ["C"], ["B", "E"], ["D", "F"]]   # back -> front (flow)
    PW = 54.0                                   # power column width (mm)
    X0, X1 = 4.0, BOARD_W - 4.0
    flank = (X1 - X0 - PW) / 2.0
    y = 20.0
    for blocks in BANDS:
        bname = "+".join(blocks)
        items = [items_by_ref[r] for b in blocks for r in BLOCKS.get(b, [])
                 if r in items_by_ref and r not in ANCHORS]
        power = [it for it in items if ref_power(it[0])]
        signal = order_block([it for it in items if not ref_power(it[0])])
        pplaced, _pw, ph = shelf(power, PW - GAP, sort=True)
        half = len(signal) // 2
        lplaced, _lw, lh = shelf(signal[:half], flank - GAP)
        rplaced, _rw, rh = shelf(signal[half:], flank - GAP)
        band_h = max(ph, lh, rh, 1.0)
        for ref, fp, cx, cy in pplaced:
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(X0 + flank + cx),
                                           pcbnew.FromMM(y + cy)))
            board.Add(fp)
        for ref, fp, cx, cy in lplaced:            # right-align to the spine
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(X0 + flank - cx),
                                           pcbnew.FromMM(y + cy)))
            board.Add(fp)
        for ref, fp, cx, cy in rplaced:
            fp.SetPosition(pcbnew.VECTOR2I(
                pcbnew.FromMM(X0 + flank + PW + cx), pcbnew.FromMM(y + cy)))
            board.Add(fp)
        y += band_h + GAP
    if y - GAP > BOARD_H - 14:
        print(f"  WARNING: bands reach {y - GAP:.1f} mm (board {BOARD_H})")

    # connectors: anchored on the edges, placed first
    for ref, (ax, ay) in ANCHORS.items():
        it = items_by_ref.get(ref)
        if it is None:
            continue
        it[1].SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(ax), pcbnew.FromMM(ay)))
        board.Add(it[1])

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
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        except Exception:
            pass
        board.Add(z)
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
