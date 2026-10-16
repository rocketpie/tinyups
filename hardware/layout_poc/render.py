#!/usr/bin/env python3
"""Render an engine's placement to SVG and score it.

Consumes build/layout/graph.json plus a positions JSON produced by any engine
({"engine": name, "positions": {ref: {x, y, angle}}}), draws the board, the
reserved power corridor, the nets (coloured / weighted by required width) and
the components, then prints placement metrics:

  HPWL          Σ per-net pad bounding-box (w+h)            (unweighted / by-width)
  wire          Σ edge length (the spring graph)
  overlap       courtyards that intersect
  outside       parts past the board edge
  corridor      parts intruding into the reserved band

Usage: render.py <positions.json> <out.svg> [--label]
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")


def rot(p, a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def corners(node, x, y, angle):
    bx, by, bw, bh = node["bbox"]
    pts = [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]
    return [(x + rx, y + ry) for rx, ry in (rot(p, angle) for p in pts)]


def aabb(node, x, y, angle):
    xs = corners(node, x, y, angle)
    return (min(p[0] for p in xs), min(p[1] for p in xs),
            max(p[0] for p in xs), max(p[1] for p in xs))


def pad_xy(node, x, y, angle, pad):
    rx, ry = rot((pad["dx"], pad["dy"]), angle)
    return (x + rx, y + ry)


def inter(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def metrics(graph, pos):
    nodes = {n["id"]: n for n in graph["nodes"]}
    board = graph["board"]
    placed = {r: p for r, p in pos.items() if r in nodes}

    # HPWL over nets: bbox of all pads on the net
    net_pads: dict[str, list] = {}
    for ref, p in placed.items():
        for pad in nodes[ref]["pads"]:
            if pad["net"]:
                net_pads.setdefault(pad["net"], []).append(
                    pad_xy(nodes[ref], p["x"], p["y"], p.get("angle", 0), pad))
    hpwl = whit = 0.0
    for net, pts in net_pads.items():
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        d = (max(xs) - min(xs)) + (max(ys) - min(ys))
        hpwl += d
        w = graph["nets"][net]["width"]
        whit += d * w

    wire = sum(math.dist((placed[e["source"]]["x"], placed[e["source"]]["y"]),
                         (placed[e["target"]]["x"], placed[e["target"]]["y"]))
               for e in graph["edges"]
               if e["source"] in placed and e["target"] in placed)
    wirew = sum(e["width"] * math.dist(
        (placed[e["source"]]["x"], placed[e["source"]]["y"]),
        (placed[e["target"]]["x"], placed[e["target"]]["y"]))
        for e in graph["edges"]
        if e["source"] in placed and e["target"] in placed)

    boxes = {r: aabb(nodes[r], p["x"], p["y"], p.get("angle", 0))
             for r, p in placed.items()}
    refs = sorted(boxes)
    overlap = sum(1 for i in range(len(refs)) for j in range(i + 1, len(refs))
                  if inter(boxes[refs[i]], boxes[refs[j]]))
    outside = sum(1 for r in refs if boxes[r][0] < 0 or boxes[r][1] < 0
                  or boxes[r][2] > board["w"] or boxes[r][3] > board["h"])
    cx0, cx1, cy0, cy1 = board["corridor"]
    corridor = sum(1 for r in refs if nodes[r]["kind"] != "J" and inter(
        boxes[r], (cx0, cy0, cx1, cy1)))
    return {"hpwl": hpwl, "hpwl_w": whit, "wire": wire, "wire_w": wirew,
            "overlap": overlap, "outside": outside, "corridor": corridor,
            "n": len(placed)}


def color(current):
    if current >= 15:
        return "#d62728"
    if current >= 5:
        return "#ff7f0e"
    if current >= 1:
        return "#e6c700"
    if current > 0:
        return "#7f7f7f"
    return "#cfcfcf"


def render(graph, pos, out, label=True):
    nodes = {n["id"]: n for n in graph["nodes"]}
    b = graph["board"]
    placed = {r: p for r, p in pos.items() if r in nodes}
    PX = 8.0
    W, H = (b["w"] + 6) * PX, (b["h"] + 6) * PX
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" '
         f'height="{H:.0f}" viewBox="-3 -3 {b["w"] + 6} {b["h"] + 6}">',
         '<rect x="0" y="0" width="%.1f" height="%.1f" fill="#0f3d1a"/>'
         % (b["w"], b["h"])]
    cx0, cx1, cy0, cy1 = b["corridor"]
    L.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
             'fill="#00ff7f" fill-opacity="0.06" stroke="#00ff7f" '
             'stroke-opacity="0.5" stroke-dasharray="1.5,1"/>'
             % (cx0, cy0, cx1 - cx0, cy1 - cy0))
    # edges under the parts
    for e in graph["edges"]:
        if e["source"] not in placed or e["target"] not in placed:
            continue
        a, t = placed[e["source"]], placed[e["target"]]
        w = e["width"]
        sw = 0.12 + 0.9 * (w / 18.71) ** 0.6 if w > 0 else 0.08
        op = 0.25 + 0.75 * (w / 18.71) ** 0.5
        L.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                 'stroke="%s" stroke-width="%.2f" stroke-opacity="%.2f"/>'
                 % (a["x"], a["y"], t["x"], t["y"], color(e["current"]),
                    sw, op))
    # orthogonal routes (ELK) under the edges
    for rt in pos.get("__routes__", []):
        pts = rt["points"]
        L.append('<polyline fill="none" stroke="#00e5ff" stroke-width="0.18" '
                 'stroke-opacity="0.5" points="%s"/>'
                 % " ".join("%.1f,%.1f" % (p[0], p[1]) for p in pts))
    # parts
    for r, p in placed.items():
        n = nodes[r]
        pts = " ".join("%.2f,%.2f" % q for q in
                       corners(n, p["x"], p["y"], p.get("angle", 0)))
        fill = "#ff3b3b" if n["power"] else "#2d6cdf"
        if n["kind"] == "J":
            fill = "#c8a2ff"
        if n["id"] in {x["id"] for x in graph["nodes"] if x.get("anchor")}:
            fill = "#ffd400"
        L.append('<polygon points="%s" fill="%s" fill-opacity="%.2f" '
                 'stroke="#000" stroke-width="0.15" '
                 'stroke-opacity="0.8"/>'
                 % (pts, fill, 0.55 if n["power"] else 0.7))
    if label:
        for r, p in placed.items():
            n = nodes[r]
            fs = max(1.6, min(n["w"], n["h"]) * 0.55)
            L.append('<text x="%.1f" y="%.1f" font-size="%.1f" '
                     'text-anchor="middle" dominant-baseline="central" '
                     'fill="#fff" font-family="monospace">%s</text>'
                     % (p["x"], p["y"], fs, r))
    L.append("</svg>")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write("\n".join(L))


def render_png(graph, pos, out, label=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Rectangle as MRect

    nodes = {n["id"]: n for n in graph["nodes"]}
    b = graph["board"]
    placed = {r: p for r, p in pos.items() if r in nodes}
    fig, ax = plt.subplots(figsize=(b["w"] / 12, b["h"] / 12), dpi=140)
    ax.set_facecolor("#0f3d1a")
    ax.add_patch(MRect((0, 0), b["w"], b["h"], fill=False, ec="#7fffa0", lw=1))
    cx0, cx1, cy0, cy1 = b["corridor"]
    ax.add_patch(MRect((cx0, cy0), cx1 - cx0, cy1 - cy0, fc="#00ff7f",
                       alpha=0.07, ec="#00ff7f", ls="--", lw=0.8))
    for e in graph["edges"]:
        if e["source"] not in placed or e["target"] not in placed:
            continue
        a, t = placed[e["source"]], placed[e["target"]]
        w = e["width"]
        ax.plot([a["x"], t["x"]], [a["y"], t["y"]], color=color(e["current"]),
                lw=0.3 + 3.5 * (w / 18.71) ** 0.6,
                alpha=0.25 + 0.75 * (w / 18.71) ** 0.5, solid_capstyle="round")
    for r, p in placed.items():
        n = nodes[r]
        pts = corners(n, p["x"], p["y"], p.get("angle", 0))
        fill = "#ff3b3b" if n["power"] else "#2d6cdf"
        if n["kind"] == "J":
            fill = "#c8a2ff"
        if n.get("anchor"):
            fill = "#ffd400"
        ax.add_patch(MPoly(pts, closed=True, fc=fill, alpha=0.75, ec="black",
                           lw=0.4, zorder=3))
        if label:
            ax.text(p["x"], p["y"], r, ha="center", va="center",
                    fontsize=3.2, color="white", family="monospace", zorder=4)
    ax.set_xlim(-3, b["w"] + 3)
    ax.set_ylim(b["h"] + 3, -3)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout(pad=0.2)
    fig.savefig(out, facecolor="#101010")
    plt.close(fig)


def main() -> int:
    posfile, out = sys.argv[1], sys.argv[2]
    graph = json.load(open(GRAPH))
    data = json.load(open(posfile))
    pos = data["positions"]
    pos["__routes__"] = data.get("routes", [])
    m = metrics(graph, pos)
    if out.endswith(".png"):
        render_png(graph, pos, out, label="--label" in sys.argv)
    else:
        render(graph, pos, out, label="--label" in sys.argv)
    print(f"  {data.get('engine','?'):14} n={m['n']:3} "
          f"HPWL {m['hpwl']:7.0f} mm (w {m['hpwl_w']:8.0f}) "
          f"wire {m['wire']:7.0f} mm  "
          f"overlap {m['overlap']:3}  outside {m['outside']:2}  "
          f"corridor {m['corridor']:2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
