#!/usr/bin/env python3
"""Extract a *placement graph* from the netlist for auto-layout experiments.

Nodes  = components (footprint, courtyard size, pads, block, power flag)
Anchors= only the two main connectors: 1J1 (XT60 input) and 5J2 (XT30 output).
Edges  = net connectivity, decomposed as an MST per net (k-1 edges), with a
         required trace width derived from the net's design current (IPC-2221).

**GND is dropped.**  It is a plane, so its traces are irrelevant to placement;
including it (71 parts) just glues the whole design into a hairball.

The same graph feeds every layout engine (d3-force, dagre, ELK, graphviz), so
they can be compared apple-to-apple.  It also carries `power_order` — the power
components in power-flow order (BFS from the input over the rail nets) — which
the incremental engine places one by one.

Usage:
    /opt/eda/venv/bin/python hardware/layout_poc/extract.py [--keep-gnd] [--drop NETS]
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
sys.path.insert(0, os.path.dirname(HERE))          # hardware/
sys.path.insert(0, HERE)

from blocks import PREFIXED_BLOCKS, kind, label                 # noqa: E402
from gen_pcb import ANCHORS, BOARD_H, BOARD_W, parse, _find_all  # noqa: E402
from power_spec import (CAP_ESR, DESIGN_CURRENT, RIPPLE_V_RMS,   # noqa: E402
                        SW_FREQ)
from power_map import (_cap, _num, component_is_power,           # noqa: E402
                        OVERRIDES)

NETLIST = os.path.join(ROOT, "build", "tinyups.net")
FP_ROOT = "/usr/share/kicad/footprints"
OUT = os.path.join(ROOT, "build", "layout", "graph.json")

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

    tree = parse(open(NETLIST).read())

    comps: dict[str, dict] = {}
    for c in _find_all(tree, "comp"):
        ref = next(x for x in c if isinstance(x, list) and x[0] == "ref")[1]
        val = next((x[1] for x in c if isinstance(x, list) and x[0] == "value"), "")
        fp = next((x[1] for x in c if isinstance(x, list) and x[0] == "footprint"), "")
        comps[ref] = {"value": val, "fp": fp}

    pin_net: dict[tuple[str, str], str] = {}
    nets: dict[str, list[str]] = {}
    for net in _find_all(tree, "net"):
        name = next(x[1] for x in net if isinstance(x, list) and x[0] == "name")
        name = name.lstrip("/")
        for node in net:
            if isinstance(node, list) and node[0] == "node":
                ref = next(x[1] for x in node if isinstance(x, list) and x[0] == "ref")
                pad = next(x[1] for x in node if isinstance(x, list) and x[0] == "pin")
                pin_net[(ref, pad)] = name
                nets.setdefault(name, []).append(ref)

    ref_block = {r: b for b, refs in PREFIXED_BLOCKS.items() for r in refs}
    # pin only the two power terminals; USB/SWD/PACK/CELLS/fan headers move free.
    anchors = {label(k): v for k, v in ANCHORS.items() if k in PINNED}

    nodes = []
    for ref, info in sorted(comps.items()):
        lib, name = info["fp"].split(":", 1)
        fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib + ".pretty"), name)
        if fp is None:
            print("missing footprint", info["fp"], file=sys.stderr)
            return 1
        # local bbox relative to the (unrotated) footprint origin.
        # Prefer the F.CrtYd courtyard: that is what KiCad's DRC actually checks,
        # so a legalizer built on the *body* bbox still leaves courtyard overlaps.
        bb = fp.GetBoundingBox(False, False)
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        if poly.OutlineCount() > 0:
            bb = poly.BBox()
        o = fp.GetPosition()
        bx, by = pcbnew.ToMM(bb.GetX() - o.x), pcbnew.ToMM(bb.GetY() - o.y)
        bw, bh = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
        pads = []
        for p in fp.Pads():
            pos = p.GetPosition()
            pads.append({
                "num": p.GetNumber(),
                "net": pin_net.get((ref, p.GetNumber()), ""),
                "dx": round(pcbnew.ToMM(pos.x - o.x), 3),
                "dy": round(pcbnew.ToMM(pos.y - o.y), 3),
            })
        nets_of = {p["net"] for p in pads if p["net"]}
        nodes.append({
            "id": ref,
            "value": info["value"],
            "fp": info["fp"],
            "kind": kind(ref),
            "block": ref_block.get(ref, "?"),
            "power": component_is_power(ref, info["value"], nets_of),
            "w": round(bw, 2), "h": round(bh, 2),
            "bbox": [round(bx, 2), round(by, 2), round(bw, 2), round(bh, 2)],
            "anchor": anchors.get(ref),
            "pads": pads,
        })
    node_by_id = {n["id"]: n for n in nodes}

    # per-net current -> required width
    net_current = {n: DESIGN_CURRENT.get(n, 0.0) for n in nets}
    net_width = {n: round(ipc_width_mm(c), 2) for n, c in net_current.items()}

    # edges: MST per net over the distinct comps on it
    edges = []
    for net, refs in nets.items():
        if net in drop:
            continue
        uniq = sorted(set(refs))
        if len(uniq) < 2:
            continue
        # candidate edges, ordered so the MST links the *current-carrying* parts
        # together first (and attaches the sense/supply stubs afterwards).
        # Otherwise a size-based distance happily wires a FET to the chip.
        share = {r: conducted(r, node_by_id[r]["kind"],
                             node_by_id[r]["value"], net) for r in uniq}
        cand = []
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                a, b = node_by_id[uniq[i]], node_by_id[uniq[j]]
                d = math.hypot(a["w"] + b["w"], a["h"] + b["h"])
                cand.append((-min(share[uniq[i]], share[uniq[j]]), d,
                             uniq[i], uniq[j]))
        cand.sort()
        parent = {r: r for r in uniq}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _n, _d, a, b in cand:
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            parent[ra] = rb
            # the *connection* current, not the whole rail: a sense pin on a
            # 17 A net carries milliamps, a FET carries the rail
            ecur = min(share[a], share[b])
            edges.append({
                "source": a, "target": b, "net": net,
                "current": round(ecur, 3),
                "width": round(ipc_width_mm(ecur), 2),
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
