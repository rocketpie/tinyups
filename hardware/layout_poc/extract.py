#!/usr/bin/env python3
"""Extract a *placement graph* from the netlist for auto-layout experiments.

Nodes  = components (footprint, size, per-pad local geometry, block, power flag)
Anchors= the board connectors, pinned to the board edges (from gen_pcb.ANCHORS)
Edges  = net connectivity, decomposed as an MST per net (k-1 edges), with a
         required trace width derived from the net's design current (IPC-2221).

The same graph feeds every layout engine (d3-force, dagre, ELK, graphviz), so
they can be compared apple-to-apple.

Usage:
    /opt/eda/venv/bin/python hardware/layout_poc/extract.py [--drop NETS]
Writes:  build/layout/graph.json
"""
from __future__ import annotations

import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))          # hardware/
sys.path.insert(0, HERE)

from blocks import PREFIXED_BLOCKS, kind                      # noqa: E402
from gen_pcb import ANCHORS, BOARD_H, BOARD_W, parse, _find_all  # noqa: E402
from power_spec import DESIGN_CURRENT                          # noqa: E402
from power_map import component_is_power                       # noqa: E402

NETLIST = os.path.join(ROOT, "build", "tinyups.net")
FP_ROOT = "/usr/share/kicad/footprints"
OUT = os.path.join(ROOT, "build", "layout", "graph.json")

# IPC-2221 external-layer trace width for a given current (mm).
#   I = k * dT**0.44 * A**0.725  (A in mil^2, k=0.048 external, 1 oz = 1.378 mil)
K_EXT, THICK_MIL, DT_C = 0.048, 1.378, 10.0
SIG_WIDTH_MM = 0.25            # default width for nets with no design current


def ipc_width_mm(current_a: float, layers: int = 1) -> float:
    if current_a <= 0:
        return SIG_WIDTH_MM
    area_mil2 = (current_a / (K_EXT * DT_C ** 0.44)) ** (1.0 / 0.725)
    return max(SIG_WIDTH_MM, area_mil2 / THICK_MIL / layers * 0.0254)


def main() -> int:
    drop = set()
    if "--drop" in sys.argv:
        drop = set(sys.argv[sys.argv.index("--drop") + 1].split(","))

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
    # gen_pcb ANCHORS use *base* refs (J1..); map to the prefixed netlist refs.
    from blocks import label
    anchors = {label(k): v for k, v in ANCHORS.items()}

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
    skipped = []
    for net, refs in nets.items():
        if net in drop:
            skipped.append(net)
            continue
        uniq = sorted(set(refs))
        if len(uniq) < 2:
            continue
        cand = []
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                a, b = node_by_id[uniq[i]], node_by_id[uniq[j]]
                # distance between footprint centres (start: schematic-square guess)
                d = math.hypot(a["w"] + b["w"], a["h"] + b["h"])
                cand.append((d, uniq[i], uniq[j]))
        cand.sort()
        parent = {r: r for r in uniq}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for _d, a, b in cand:
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            parent[ra] = rb
            edges.append({
                "source": a, "target": b, "net": net,
                "current": net_current[net],
                "width": net_width[net],
            })

    graph = {
        "board": {
            "w": BOARD_W, "h": BOARD_H,
            "corridor": [BOARD_W / 2 - 10.0, BOARD_W / 2 + 10.0, 20.0, 120.0],
        },
        "nodes": nodes,
        "edges": edges,
        "nets": {n: {"current": net_current[n], "width": net_width[n],
                     "comps": len(set(nets[n]))} for n in nets},
        "dropped": skipped,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(graph, f, indent=1)
    print(f"wrote {OUT}")
    print(f"  {len(nodes)} nodes, {len(edges)} edges "
          f"({len(nets)} nets), anchors {len(anchors)}")
    wide = sorted(net_width.items(), key=lambda kv: -kv[1])[:6]
    print("  widest nets: " + ", ".join(f"{n}={w}mm" for n, w in wide))
    if skipped:
        print("  dropped from springs: " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
