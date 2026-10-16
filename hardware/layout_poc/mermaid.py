#!/usr/bin/env python3
"""Write a mermaid `flowchart` of the placement graph.

components -> nodes, nets -> links (same graph the other engines use).  Feed the
result to `mmdc` to get the actual mermaid render (it runs dagre under the
hood), or just eyeball the text in any mermaid viewer.

Usage: mermaid.py <graph.json> <out.mmd>
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

BLOCK = {"1": "IP", "2": "CHG", "3": "PP", "4": "BMS", "5": "OR", "6": "CTL", "default": "?"}


def main() -> int:
    graph = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    lines = ["flowchart LR"]
    # one subgraph per power block, like the schematic
    blocks: dict[str, list] = {}
    for n in graph["nodes"]:
        b = BLOCK.get(n["id"][0], "X")
        blocks.setdefault(b, []).append(n)
    for b in sorted(blocks):
        lines.append(f'  subgraph {b}["block {b}"]')
        for n in sorted(blocks[b], key=lambda n: n["id"]):
            shape = "([{0}])".format(n["value"] or n["id"])
            lines.append(f'    {n["id"]}{shape}')
        lines.append("  end")
    for e in graph["edges"]:
        lbl = ""
        if e["current"] > 0:
            lbl = f'|"{e["net"]} {e["current"]:g}A"|'
        lines.append(f'  {e["source"]} -->{lbl} {e["target"]}')
    lines.append("  classDef power fill:#ff6b6b,stroke:#900,color:#000;")
    lines.append("  classDef sig fill:#4d79ff,stroke:#003,color:#fff;")
    for n in graph["nodes"]:
        lines.append(f'  class {n["id"]} '
                     f'{"power" if n["power"] else "sig"};')
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"wrote {out} ({len(graph['nodes'])} nodes, {len(graph['edges'])} links)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
