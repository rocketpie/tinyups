#!/usr/bin/env python3
"""Fit an engine's raw coordinates onto the TinyUPS board, then pin connectors.

Layered/stress engines (dagre, ELK, graphviz) lay the graph out in their own
coordinate space and ignore the physical board.  This step applies a *uniform*
scale + translation so every part lands inside the 150x140 mm outline, then
snaps the seven edge connectors to their fixed anchor positions (gen_pcb.ANCHORS)
so a comparison against the hand floorplan is fair.

Usage: fitpos.py <in.json> <out.json> [--pad MM]
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    pad = 4.0
    if "--pad" in sys.argv:
        pad = float(sys.argv[sys.argv.index("--pad") + 1])
    graph = json.load(open(GRAPH))
    data = json.load(open(src))
    pos = data["positions"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    board = graph["board"]

    # bbox of the placed node *centres* (ignoring part size) then scale to fit
    xs = [p["x"] for r, p in pos.items() if r in nodes]
    ys = [p["y"] for r, p in pos.items() if r in nodes]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    avail_w, avail_h = board["w"] - 2 * pad, board["h"] - 2 * pad
    span_w, span_h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = min(avail_w / span_w, avail_h / span_h)
    off_x = pad + (avail_w - span_w * scale) / 2
    off_y = pad + (avail_h - span_h * scale) / 2
    out = {}
    for r, p in pos.items():
        if r not in nodes:
            continue
        out[r] = {"x": round((p["x"] - x0) * scale + off_x, 2),
                  "y": round((p["y"] - y0) * scale + off_y, 2),
                  "angle": p.get("angle", 0)}
    # routes (ELK) transform the same way
    routes = []
    for rt in data.get("routes", []):
        routes.append({"edge": rt["edge"], "width": rt.get("width", 0.25),
                       "points": [[round((px - x0) * scale + off_x, 2),
                                   round((py - y0) * scale + off_y, 2)]
                                  for px, py in rt["points"]]})
    for r, n in nodes.items():
        if n.get("anchor") and r in out:
            out[r]["x"], out[r]["y"] = n["anchor"]
    json.dump({"engine": data.get("engine", "?"), "params": data.get("params", {}),
               "positions": out, "routes": routes},
              open(dst, "w"), indent=1)
    print(f"fit {data.get('engine','?'):16} scale {scale:6.3f} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
