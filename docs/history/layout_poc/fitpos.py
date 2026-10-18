#!/usr/bin/env python3
"""Fit an engine's raw coordinates onto the TinyUPS board.

Layered / stress engines (dagre, ELK, graphviz) lay the graph out in their own
coordinate space, ignore the physical board *and have no idea which end is the
input*: sfdp, for instance, reliably produced the power chain rotated 180°
(a power-path correlation of -0.4 .. -0.8).  That is not a seeding artefact —
reshuffling the seed/order keeps the sign — it is free orientation.

So this step does two things:

  1. **orient** — try the 8 orientations (4 rotations x mirror) and keep the one
     whose power flow best matches the board: maximise `axisR`, the correlation
     between a part's flow position (input=0 .. output=1, from the rail graph)
     and where it lands along the input->output axis.
  2. **fit** — uniform scale + translation into the 150x140 outline, then snap
     the seven connectors to their anchors.

The two d3 engines don't come here: they already work in board millimetres and
are seeded by flow position, so they start the right way round.

Usage: fitpos.py <in.json> <out.json> [--pad MM] [--no-orient]
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")


def transform(p, kind):
    """Rotate/mirror a point about the origin (0..7, 4 rotations x mirror)."""
    x, y = p
    if kind & 1:
        x = -x
    for _ in range(kind >> 1):
        x, y = -y, x
    return x, y


def axis_r(graph, pos):
    """Corr(flow position, position along the input->output axis)."""
    nodes = {n["id"]: n for n in graph["nodes"]}
    pin = next((n["anchor"] for n in graph["nodes"]
                if n["id"] == graph["io"]["in"]), None)
    pout = next((n["anchor"] for n in graph["nodes"]
                 if n["id"] == graph["io"]["out"]), None)
    if not pin or not pout:
        return 0.0
    ux, uy = pout[0] - pin[0], pout[1] - pin[1]
    nrm = math.hypot(ux, uy) or 1.0
    fs, us = [], []
    for r in graph["power_order"]:
        if r not in pos:
            continue
        f = nodes[r].get("flow")
        if f is None:
            continue
        px, py = pos[r]["x"] - pin[0], pos[r]["y"] - pin[1]
        fs.append(f)
        us.append((px * ux + py * uy) / nrm / nrm)
    if len(fs) < 3:
        return 0.0
    mf, mu = sum(fs) / len(fs), sum(us) / len(us)
    cov = sum((a - mf) * (b - mu) for a, b in zip(fs, us))
    sf = math.sqrt(sum((a - mf) ** 2 for a in fs))
    su = math.sqrt(sum((b - mu) ** 2 for b in us))
    return cov / (sf * su) if sf and su else 0.0


def fit(raw, graph, pad, keep_scale=False):
    """Uniform fit of the raw points into the board (or identity: keep_scale).

    keep_scale is for the d3 engines: they already work in board millimetres and
    are seeded by flow, so rescaling them would only distort spacing — but they
    should still get the same orientation choice as everyone else.
    """
    board = graph["board"]
    if keep_scale:
        return {r: {"x": round(px, 2), "y": round(py, 2), "angle": 0}
                for r, (px, py) in raw.items()}
    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    avail_w, avail_h = board["w"] - 2 * pad, board["h"] - 2 * pad
    span_w, span_h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = min(avail_w / span_w, avail_h / span_h)
    off_x = pad + (avail_w - span_w * scale) / 2
    off_y = pad + (avail_h - span_h * scale) / 2
    out = {}
    for r, (px, py) in raw.items():
        out[r] = {"x": round((px - x0) * scale + off_x, 2),
                  "y": round((py - y0) * scale + off_y, 2), "angle": 0}
    return out


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    pad = 4.0
    if "--pad" in sys.argv:
        pad = float(sys.argv[sys.argv.index("--pad") + 1])
    do_orient = "--no-orient" not in sys.argv
    keep_scale = "--keep-scale" in sys.argv
    graph = json.load(open(GRAPH))
    data = json.load(open(src))
    raw0 = {r: (p["x"], p["y"]) for r, p in data["positions"].items()
            if any(n["id"] == r for n in graph["nodes"])}
    # rotate/mirror about the layout's own centre, so keep-scale stays in place
    cx = sum(p[0] for p in raw0.values()) / max(len(raw0), 1)
    cy = sum(p[1] for p in raw0.values()) / max(len(raw0), 1)

    best, best_kind, best_r = None, None, None
    kinds = range(8) if do_orient else (0,)
    for kind in kinds:
        raw = {}
        for r, (px, py) in raw0.items():
            tx, ty = transform((px - cx, py - cy), kind)
            raw[r] = (cx + tx, cy + ty)
        pos = fit(raw, graph, pad, keep_scale)
        for n in graph["nodes"]:                 # pin the connectors
            if n.get("anchor") and n["id"] in pos:
                pos[n["id"]]["x"], pos[n["id"]]["y"] = n["anchor"]
        r = axis_r(graph, pos)
        if best_r is None or r > best_r:
            best, best_kind, best_r = pos, kind, r

    # routes (ELK) transform the same way as the chosen orientation
    routes = []
    if data.get("routes") and not keep_scale:
        board = graph["board"]
        xs = [p[0] for p in raw0.values()]
        ys = [p[1] for p in raw0.values()]
        x0, y0 = min(xs), min(ys)
        span_w, span_h = max(max(xs) - x0, 1e-6), max(max(ys) - y0, 1e-6)
        avail_w, avail_h = board["w"] - 2 * pad, board["h"] - 2 * pad
        scale = min(avail_w / span_w, avail_h / span_h)
        off_x = pad + (avail_w - span_w * scale) / 2
        off_y = pad + (avail_h - span_h * scale) / 2
        for rt in data["routes"]:
            pts = []
            for px, py in rt["points"]:
                tx, ty = transform((px - cx, py - cy), best_kind)
                pts.append([round((cx + tx - x0) * scale + off_x, 2),
                            round((cy + ty - y0) * scale + off_y, 2)])
            routes.append({"edge": rt["edge"], "width": rt.get("width", 0.25),
                           "points": pts})

    json.dump({"engine": data.get("engine", "?"), "params": data.get("params", {}),
               "positions": best, "routes": routes}, open(dst, "w"), indent=1)
    print(f"fit {data.get('engine','?'):16} orient {best_kind} "
          f"(axisR {best_r:+.2f}) -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
