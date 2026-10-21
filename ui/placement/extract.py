#!/usr/bin/env python3
"""Extract the *placement graph* from the board.

Nodes  = components (the board's real footprint, courtyard, pads, block, power
         flag) at their current rotation.  The **board** is the source of truth:
         if a component was swapped on the board but not in the schematic, the
         netlist's footprint id (and therefore pad geometry) is stale.  Using the
         board also makes a pad-clearance metric mean something.
Anchors= only the two main connectors: 1J1 (XT60 input) and 5J2 (XT30 output).
Edges  = net connectivity, decomposed as an MST per net (k-1 edges), with a
         required trace width derived from the net's design current (IPC-2221).

**GND is dropped.**  It is a plane, so its traces are irrelevant to placement;
including it (71 parts) just glues the whole design into a hairball.

`power_order` — the power components in power-flow order (BFS from the input
over the rail nets) — is carried for the incremental engine.

Usage:
    /opt/eda/venv/bin/python ui/placement/extract.py [--keep-gnd] [--drop NETS]
Writes:  build/layout/graph.json
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import deque

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "hardware"))   # blocks.py, power_*.py
sys.path.insert(0, HERE)

from blocks import (BLOCK_NUM, PREFIX, PREFIXED_BLOCKS, kind,      # noqa: E402
                    label)
from power_spec import (CAP_ESR, DESIGN_CURRENT, RIPPLE_V_RMS,   # noqa: E402
                        SW_FREQ)
from power_report import width_for                              # noqa: E402
from power_map import (_cap, _num, component_is_power,           # noqa: E402
                        OVERRIDES)
import placement_spec as pspec                                  # noqa: E402

BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")
OUT = os.path.join(ROOT, "build", "layout", "graph.json")

# Board outline.  The two terminal positions are read from the board too: the
# hand-tuned placement moved them off the old gen_pcb floorplan.
BOARD_W, BOARD_H = 150.0, 140.0


# --------------------------------------------------------------------------- #
# board geometry -> footprint-local frame
# --------------------------------------------------------------------------- #
def rot(p, a):
    """Rotate a local offset by `a` degrees, KiCad Y-DOWN frame."""
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)


def local_bbox(fp) -> tuple[float, float, float, float]:
    """Courtyard AABB in the footprint's own (unrotated) frame.

    The board stores the courtyard in board coordinates; `setExtents` in the UI
    re-applies the placement rotation, so the graph must carry the local shape.
    """
    o = fp.GetPosition()
    pts = []
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    if poly.OutlineCount() == 0:
        poly = fp.GetCourtyard(pcbnew.B_CrtYd)
    if poly.OutlineCount() > 0:
        for i in range(poly.OutlineCount()):
            outline = poly.Outline(i)
            for j in range(outline.PointCount()):
                q = outline.CPoint(j)
                pts.append(rot((pcbnew.ToMM(q.x - o.x),
                                pcbnew.ToMM(q.y - o.y)),
                               -fp.GetOrientationDegrees()))
    if not pts:                                  # no courtyard: body bbox
        bb = fp.GetBoundingBox(False, False)
        for dx, dy in ((bb.GetX(), bb.GetY()),
                       (bb.GetX() + bb.GetWidth(), bb.GetY()),
                       (bb.GetX() + bb.GetWidth(), bb.GetY() + bb.GetHeight()),
                       (bb.GetX(), bb.GetY() + bb.GetHeight())):
            pts.append(rot((pcbnew.ToMM(dx - o.x), pcbnew.ToMM(dy - o.y)),
                           -fp.GetOrientationDegrees()))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (round(min(xs), 2), round(min(ys), 2),
            round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2))

# leading digit of the ref -> block mnemonic, e.g. 2R11 -> CHG-2R11
# (single source: blocks.py; 1=IP 2=CHG 3=PP 4=BMS 5=OR 6=CTL)
DIGIT_MNEMONIC = {str(BLOCK_NUM[b]): PREFIX[b] for b in PREFIX}


def mnemonic(ref: str) -> str:
    """'2R11' -> 'CHG-2R11'.  Labels never need to be short here."""
    m = DIGIT_MNEMONIC.get(ref[:1])
    return f"{m}-{ref}" if m else ref

# the two terminals of the power path: everything else is free to move.
PINNED = ("J1", "J2")          # base refs -> 1J1 (XT60 in), 5J2 (XT30 out)
DROP_DEFAULT = {"GND"}         # planes: no placement signal
STUB_A = 0.1                   # current a sense / supply / bias pin really carries

# IPC-2221 external-layer trace width for a given current (mm).
#   I = k * dT**0.44 * A**0.725  (A in mil^2, k=0.048 external, 1 oz = 1.378 mil)
K_EXT, THICK_MIL, DT_C = 0.048, 1.378, 10.0
SIG_WIDTH_MM = 0.25            # default width for nets with no design current


def conducted(ref: str, kind_: str, value: str, net: str) -> float:
    """Current that actually flows *through this part* on this net.

    A rail's design current is carried by its **series** elements (FETs,
    inductors, shunts, fuses, connectors).  An IC's sense/supply pin sitting on
    that same net — 5U1's N_CS and SW1_OUT pins, say — carries milliamps.  Using
    the net current for those pins gives a bogus 17 A link and a bogus 100:1
    spring that drags the chip into the power cluster.

    Per-component overrides (fan header, cell-sense header) win, matching
    power_map.py.
    """
    if ref in OVERRIDES:
        return float(OVERRIDES[ref])
    cu = DESIGN_CURRENT.get(net, 0.0)
    if kind_ in ("Q", "L", "F", "J"):
        return cu
    if kind_ == "R":
        r = _num(value)
        return cu if (r is not None and r < 1.0) else STUB_A     # shunt vs bias
    if kind_ == "C":
        c = _cap(value)
        if not c:
            return STUB_A
        z = CAP_ESR + 1.0 / (2 * math.pi * SW_FREQ * c)         # |Z| at fsw
        return min(cu or 1e9, RIPPLE_V_RMS / z)                  # ripple RMS
    return STUB_A


def ipc_width_mm(current_a: float, layers: int = 1) -> float:
    if current_a <= 0:
        return SIG_WIDTH_MM
    area_mil2 = (current_a / (K_EXT * DT_C ** 0.44)) ** (1.0 / 0.725)
    return max(SIG_WIDTH_MM, area_mil2 / THICK_MIL / layers * 0.0254)


def main() -> int:
    drop = set(DROP_DEFAULT)
    if "--keep-gnd" in sys.argv:
        drop = set()
    if "--drop" in sys.argv:
        drop |= set(sys.argv[sys.argv.index("--drop") + 1].split(","))

    board = pcbnew.LoadBoard(BOARD)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}

    nets: dict[str, list[str]] = {}
    for ref, fp in fps.items():
        for p in fp.Pads():
            net = p.GetNetname().lstrip("/")
            if net:
                nets.setdefault(net, []).append(ref)

    ref_block = {r: b for b, refs in PREFIXED_BLOCKS.items() for r in refs}
    # pin only the two power terminals; USB/SWD/PACK/CELLS/fan headers move free.
    anchors = {}
    for base in PINNED:
        fp = fps.get(label(base))
        if fp is not None:
            p = fp.GetPosition()
            anchors[label(base)] = (round(pcbnew.ToMM(p.x), 2),
                                    round(pcbnew.ToMM(p.y), 2))

    def spec_payload(ref: str) -> dict:
        """Design-intent limits for one part, plus the host/ring the UI uses.

        The host is the *most demanding* reach in the spec (smallest allowed
        max), so a hold-up cap that must be within 10 mm of the FET is pulled
        there rather than to a 15 mm controller.  Free/anchor parts get no host:
        the UI no longer invents one.
        """
        limits = pspec.as_json(ref)
        role = pspec.ROLES.get(ref, "")
        reach = [l for l in limits
                 if l["max"] is not None and l["host"] != "BOARD_EDGE"]
        if not reach:
            return {"role": role, "limits": limits, "host": None}
        # primary host first; then the smallest reach; prefer a pad rule
        best = min(reach, key=lambda l: (not l["primary"], l["max"],
                                        l["measure"] != "pad", l["host"]))
        return {
            "role": role,
            "limits": limits,
            "host": best["host"],
            "max": best["max"],
            "min": best["min"],
            "measure": best["measure"],
            "net": best["net"],
            "why": best["why"],
            "ring": round(min(best["max"], 8.0), 2),
        }

    nodes = []
    for ref, fp in sorted(fps.items()):        # The board's footprint, not the netlist's: a swapped part keeps its
        # schematic footprint id in the netlist until the schematic is re-synced,
        # and the resulting pad geometry would be a different part.
        bx, by, bw, bh = local_bbox(fp)
        fpid = fp.GetFPID()
        fp_name = f"{fpid.GetLibNickname()}:{fpid.GetLibItemName()}"
        value = fp.GetValue()
        k = kind(ref)
        pads = []
        for p in fp.Pads():
            rel = p.GetFPRelativePosition()     # already footprint-local
            sz = p.GetSize()
            net = p.GetNetname().lstrip("/")
            pads.append({
                "num": p.GetNumber(),
                "net": net,
                "dx": round(pcbnew.ToMM(rel.x), 3),
                "dy": round(pcbnew.ToMM(rel.y), 3),
                # Pad geometry is what a *clearance* is measured on; the
                # courtyard is the placement collision, not the copper.
                "w": round(pcbnew.ToMM(sz.x), 3),
                "h": round(pcbnew.ToMM(sz.y), 3),
                "angle": round((p.GetOrientationDegrees()
                                - fp.GetOrientationDegrees()) % 360, 2),
                # What *this* pad really carries on this net (a 100k pull-up on
                # +12V_IN is 0.1 A, not 20 A).  The pad-level ratsnest colours
                # by this, so a tap does not look like a power trace.
                "current": round(conducted(ref, k, value, net), 3) if net else 0.0,
            })
        nets_of = {p["net"] for p in pads if p["net"]}
        nodes.append({
            "id": ref,
            "label": mnemonic(ref),
            "value": value,
            "fp": fp_name,
            "kind": k,
            "block": ref_block.get(ref, "?"),
            "power": component_is_power(ref, value, nets_of),
            "role": pspec.ROLES.get(ref, ""),
            "spec": spec_payload(ref),
            "w": bw, "h": bh,
            "bbox": [bx, by, bw, bh],
            "anchor": anchors.get(ref),
            "pads": pads,
        })
    node_by_id = {n["id"]: n for n in nodes}

    # per-net current -> required width.  `width` is the force model's 1 oz
    # reference (the springs' relative width); `required` is the board's real
    # 2 oz IPC-2221 width, the number the UI must show and the pour channel
    # must meet (ADR-0008: 20 A -> 9.4 mm, not 18.7 mm).
    net_current = {n: DESIGN_CURRENT.get(n, 0.0) for n in nets}
    net_width = {n: round(ipc_width_mm(c), 2) for n, c in net_current.items()}
    net_required = {n: round(max(SIG_WIDTH_MM, width_for(c)), 2) if c > 0
                    else SIG_WIDTH_MM for n, c in net_current.items()}

    # edges: for the *force model*, the clique of each net — every pair gets an
    # equal share of the net's total weight.  A net is electrically one node, so
    # an MST is equally "valid", but it makes whichever part the tree happens to
    # root look like a hub (2R11 with degree 12 on +3V3, 2U1 with 27).  The
    # clique is the textbook HPWL model: no part is special, and the net's total
    # pull is bounded by its required width, so a 21-pad supply rail cannot
    # out-gun a 2-pad one and bundle unrelated parts.
    # `draw` marks the MST subset, which is what the renderer draws (a clique
    # would put ~625 lines on the picture).
    edges = []
    for net, refs in nets.items():
        if net in drop:
            continue
        uniq = sorted(set(refs))
        k = len(uniq)
        if k < 2:
            continue
        share = {r: conducted(r, node_by_id[r]["kind"],
                             node_by_id[r]["value"], net) for r in uniq}
        pairs = []
        for i in range(k):
            for j in range(i + 1, k):
                a, b = node_by_id[uniq[i]], node_by_id[uniq[j]]
                d = math.hypot(a["w"] + b["w"], a["h"] + b["h"])
                pairs.append((-min(share[uniq[i]], share[uniq[j]]), d,
                              uniq[i], uniq[j]))
        # MST over the same ordering, only to pick a readable subset to draw
        parent = {r: r for r in uniq}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        mst = set()
        for _n, _d, a, b in sorted(pairs):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
                mst.add(frozenset((a, b)))

        # What to DRAW.  For a net with real current carriers, draw the
        # current-ordered path (informative: it is the trace).  For a pure
        # distribution rail (all stubs — +3V3, or GND if kept) there is no path
        # to draw, and an MST would root it at whichever part came first
        # (2R11's degree-12).  Draw a star from the net's hub instead — the
        # largest part, which is the meaningful one (the RP2040, not a pull-up).
        carriers = [r for r in uniq if share[r] > STUB_A * 1.5]
        if len(carriers) >= 2:
            draw_set = mst
        else:
            hub = max(uniq, key=lambda r: node_by_id[r]["w"] * node_by_id[r]["h"])
            draw_set = {frozenset((hub, r)) for r in uniq if r != hub}

        # equal share per clique edge, so the net's TOTAL weight is bounded
        wfrac = 2.0 / (k * (k - 1))
        for _n, _d, a, b in pairs:
            # the *connection* current, not the whole rail: a sense pin on a
            # 17 A net carries milliamps, a FET carries the rail
            ecur = min(share[a], share[b])
            edges.append({
                "source": a, "target": b, "net": net,
                "current": round(ecur, 3),
                "width": round(ipc_width_mm(ecur), 2),
                "weight": round(wfrac, 6),
                "draw": frozenset((a, b)) in draw_set,
            })

    # ---- power-flow order (BFS from the input over the rail nets) ----------
    # the order the incremental engine places power parts in: rail -> FET ->
    # node -> L -> node -> FET, so the chain runs input -> output.
    rails = {n for n in nets if n in DESIGN_CURRENT}
    adj: dict[str, set] = {}
    for n in rails:                       # parts sharing a rail are adjacent
        refs = set(nets[n])
        for r in refs:
            adj.setdefault(r, set()).update(refs - {r})

    start, end = label("J1"), label("J2")

    def bfs_depths(origin: str) -> dict[str, int]:
        d = {origin: 0}
        q = deque([origin])
        while q:
            r = q.popleft()
            for nb in sorted(adj.get(r, ())):
                if nb not in d:
                    d[nb] = d[r] + 1
                    q.append(nb)
        return d

    din, dout = bfs_depths(start), bfs_depths(end)
    # flow position 0..1: hops from the input / (hops from input + from output).
    # 0 = at the input, 1 = at the output, monotonic along the chain.
    for n in nodes:
        a, b = din.get(n["id"]), dout.get(n["id"])
        n["flow_in"], n["flow_out"] = a, b
        n["flow"] = (a / (a + b)) if (a is not None and b is not None and a + b) \
            else None
    # the power path, input-first / output-last.  The two ends are pinned by the
    # incremental engine, so pick them explicitly: the part electrically closest
    # to the input, and the one closest to the output.
    cands = [n["id"] for n in nodes if n["power"] and n["id"] not in anchors]
    flowof = lambda r: node_by_id[r]["flow"] if node_by_id[r]["flow"] is not None else 2.0  # noqa: E731
    first = min(cands, key=lambda r: (node_by_id[r]["flow_in"] or 99, flowof(r)))
    last = min(cands, key=lambda r: (node_by_id[r]["flow_out"] or 99, -flowof(r)))
    middle = sorted((r for r in cands if r not in (first, last)),
                    key=lambda r: (flowof(r), din.get(r, 99)))
    power_order = [first, *middle, last]

    graph = {
        "board": {"w": BOARD_W, "h": BOARD_H},
        "io": {"in": label("J1"), "out": label("J2")},
        "nodes": nodes,
        "edges": edges,
        "power_order": power_order,
        "nets": {n: {"current": net_current[n], "width": net_width[n],
                     "required": net_required[n],
                     "comps": len(set(nets[n]))} for n in nets},
        "dropped": sorted(drop),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(graph, f, indent=1)
    print(f"wrote {OUT}")
    print(f"  {len(nodes)} nodes, {len(edges)} edges "
          f"({len(nets)} nets), pinned {sorted(anchors)}")
    print(f"  dropped nets: {', '.join(sorted(drop)) or '(none)'}")
    print(f"  power order ({len(power_order)}), "
          f"{power_order[0]} (in) -> {power_order[-1]} (out): "
          f"{' '.join(power_order[:5])} ... {' '.join(power_order[-4:])}")
    onrail = [n for n in nodes if n["flow"] is not None]
    print(f"  on the rails: {len(onrail)} parts, "
          f"flow 0..1, input hops<= {max(n['flow_in'] for n in onrail)}, "
          f"output hops<= {max(n['flow_out'] for n in onrail)}")
    wide = sorted(net_width.items(), key=lambda kv: -kv[1])[:5]
    print("  widest nets: " + ", ".join(f"{n}={w}mm" for n, w in wide))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
