#!/usr/bin/env python3
"""PoC engine: Graphviz layouts (dot / neato / fdp / sfdp / osage).

Graphviz is the classic open-source layout toolbox:
  dot    layered / hierarchical (Sugiyama)  — the "orthogonal-ish" one
  neato  stress majorisation (Kamada-Kawai)
  fdp    Fruchterman-Reingold spring embedder
  sfdp   multiscale spring embedder
  osage  clustered layout

Nodes are drawn as fixed-size empty boxes; edge `len`/`weight` are driven by the
required trace width (wide nets sit farther apart).  Output is read back from
`-Tjson` (node centres + edge splines), converted to mm and written in the
common positions format.

Usage: graphviz.py <graph.json> <out.json> [engine]
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys

WREF = 18.71
MM_PER_IN = 25.4


def build_dot(graph, engine, seed=None, shuffle=False):
    P = lambda k, d: float(os.environ.get(k, d))  # noqa: E731
    k = P("GV_K", 1.0)
    lines = ["graph G {"]
    if engine == "dot":
        lines += [f"  graph [rankdir={os.environ.get('RANKDIR','LR')} "
                  f"nodesep={P('NODESEP',8)/MM_PER_IN:.3f} "
                  f"ranksep={P('RANKSEP',24)/MM_PER_IN:.3f} splines=polyline];"]
    else:
        lines += [f"  graph [overlap=prism, splines=true, "
                  f"sep=\"+{P('SEP',4)/MM_PER_IN:.3f}\", "
                  f"K={k}, start={seed if seed is not None else 13}];"]
    lines += ["  node [shape=box, fixedsize=true, label=\"\", style=filled];",
              "  edge [len=2];"]
    nodes = list(graph["nodes"])
    edges = list(graph["edges"])
    if shuffle:                       # order-sensitive tie-breaking
        random.Random(seed).shuffle(nodes)
        random.Random(seed + 1).shuffle(edges)
    for n in nodes:
        w = max(n["w"], 2) / MM_PER_IN
        h = max(n["h"], 2) / MM_PER_IN
        fill = "#ff3b3b" if n["power"] else "#2d6cdf"
        if n["kind"] == "J":
            fill = "#c8a2ff"
        lines.append(f'  "{n["id"]}" [width={w:.3f}, height={h:.3f}, '
                     f'fillcolor="{fill}"];')
    for i, e in enumerate(graph["edges"]):
        # len: wide nets sit farther apart; weight: pull strength
        ln = 1.5 + 3.5 * (e["width"] / WREF) ** 0.5
        wt = 1 + 8 * (e["width"] / WREF) ** 1.2
        lines.append(f'  "{e["source"]}" -- "{e["target"]}" '
                     f'[len={ln:.2f}, weight={wt:.2f}];')
    lines.append("}")
    return "\n".join(lines)


def main() -> int:
    graph_path, out_path = sys.argv[1], sys.argv[2]
    engine = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("GV_ENGINE", "sfdp")
    graph = json.load(open(graph_path))
    seed = int(os.environ["GV_SEED"]) if "GV_SEED" in os.environ else None
    shuffle = os.environ.get("GV_SHUFFLE") == "1"
    dot = build_dot(graph, engine, seed, shuffle)
    tmp = "/tmp/opencode/tinyups-layout.gv"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    open(tmp, "w").write(dot)
    out = subprocess.run([engine, "-Tjson", tmp], capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        return out.returncode
    data = json.loads(out.stdout)

    # graphviz y grows downward already (same as PCB), units = points (1/72 in)
    pt = MM_PER_IN / 72.0
    bb = data.get("bb", "0,0,0,0").split(",")
    ox, oy = float(bb[0]), float(bb[1])
    positions = {}
    for obj in data["objects"]:
        if obj.get("name") is None:
            continue
        px, py = obj["pos"].rstrip("!").split(",")[:2]
        positions[obj["name"]] = {
            "x": round((float(px) - ox) * pt, 2),
            "y": round((float(py) - oy) * pt, 2),
            "angle": 0,
        }
    routes = []
    for e in data.get("edges", []):
        pts = []
        for seg in e.get("pos", "").split(" "):
            for pair in seg.split(";"):
                if not pair or pair[0] in "es":
                    pair = pair[1:]
                if not pair:
                    continue
                try:
                    x, y = pair.split(",")
                    pts.append([round((float(x) - ox) * pt, 2),
                                round((float(y) - oy) * pt, 2)])
                except ValueError:
                    pass
        if pts:
            routes.append({"edge": "gv", "width": 0.25, "points": pts})

    json.dump({"engine": f"graphviz:{engine}",
               "positions": positions, "routes": []},
              open(out_path, "w"), indent=1)
    print(f"graphviz:{engine}: {len(positions)} nodes -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
