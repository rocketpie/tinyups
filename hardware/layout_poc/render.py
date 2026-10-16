#!/usr/bin/env python3
"""Render an engine's placement to SVG/PNG and score it.

Consumes build/layout/graph.json plus a positions JSON produced by any engine
({"engine": name, "positions": {ref: {x, y, angle}}}), draws the board, the nets
(coloured / weighted by required width) and the components (no GND, no corridor
— see extract.py), then prints placement metrics:

  HPWL          Σ per-net pad bounding-box (w+h)            (plain / by-width)
  wire          Σ edge length (the spring graph)
  overlap       courtyards that intersect
  outside       parts past the board edge
  path          Σ consecutive distance along the power order — how long the
                power chain is (the hand R7-at-the-bottom problem)
  straight      path / |input - output| — 1.0 is a perfectly straight chain
  d_in, d_out   first power part -> input, last power part -> output (mm)

Usage: render.py <positions.json> <out.svg|png> [--label]
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
        whit += d * graph["nets"][net]["width"]

    dist = lambda a, b: math.dist((a["x"], a["y"]), (b["x"], b["y"]))  # noqa: E731
    drawn = [e for e in graph["edges"] if e.get("draw", True)]
    wire = sum(dist(placed[e["source"]], placed[e["target"]])
               for e in drawn
               if e["source"] in placed and e["target"] in placed)
    wirew = sum(e["width"] * dist(placed[e["source"]], placed[e["target"]])
                for e in drawn
                if e["source"] in placed and e["target"] in placed)

    boxes = {r: aabb(nodes[r], p["x"], p["y"], p.get("angle", 0))
             for r, p in placed.items()}
    refs = sorted(boxes)
    overlap = sum(1 for i in range(len(refs)) for j in range(i + 1, len(refs))
                  if inter(boxes[refs[i]], boxes[refs[j]]))
    outside = sum(1 for r in refs if boxes[r][0] < 0 or boxes[r][1] < 0
                  or boxes[r][2] > board["w"] or boxes[r][3] > board["h"])

    # power-path metrics: how long / how flow-ordered is the input -> output chain
    order = [r for r in graph.get("power_order", []) if r in placed]
    path = sum(dist(placed[order[i]], placed[order[i + 1]])
               for i in range(len(order) - 1)) if len(order) > 1 else 0.0
    arid = {n["id"]: n["anchor"] for n in graph["nodes"] if n.get("anchor")}
    io = graph.get("io", {})
    pin, pout = arid.get(io.get("in")), arid.get(io.get("out"))
    span = math.dist(pin, pout) if pin and pout else 0.0
    straight = path / span if span else 0.0
    d_in = math.dist((placed[order[0]]["x"], placed[order[0]]["y"]), pin) \
        if order and pin else 0.0
    d_out = math.dist((placed[order[-1]]["x"], placed[order[-1]]["y"]), pout) \
        if order and pout else 0.0
    # flow-ordered?  correlation between a part's flow position (input=0 ..
    # output=1, from the rail graph) and where it sits along the input->output
    # axis.  1.0 = the power parts walk from the input to the output in order;
    # ~0    = flow and geometry are unrelated (the R7-at-the-bottom problem).
    axis_r = 0.0
    if pin and pout and len(order) > 2:
        ux, uy = pout[0] - pin[0], pout[1] - pin[1]
        nrm = math.hypot(ux, uy) or 1.0
        fs, us = [], []
        for r in order:
            f = nodes[r].get("flow")
            if f is None:
                continue
            fs.append(f)
            us.append(((placed[r]["x"] - pin[0]) * ux
                       + (placed[r]["y"] - pin[1]) * uy) / nrm / nrm)
        if len(fs) > 2:
            mf, mu = sum(fs) / len(fs), sum(us) / len(us)
            cov = sum((a - mf) * (b - mu) for a, b in zip(fs, us))
            sf = math.sqrt(sum((a - mf) ** 2 for a in fs))
            su = math.sqrt(sum((b - mu) ** 2 for b in us))
            axis_r = cov / (sf * su) if sf and su else 0.0
    return {"hpwl": hpwl, "hpwl_w": whit, "wire": wire, "wire_w": wirew,
            "overlap": overlap, "outside": outside, "path": path,
            "straight": straight, "axis_r": axis_r,
            "d_in": d_in, "d_out": d_out, "n": len(placed)}


def color(current):
    if current >= 15:
        return "#d62728"
    if current >= 5:
        return "#ff7f0e"
    if current >= 1:
        return "#e6c700"
    if current > 0:
        return "#7f7f7f"
    return "#bfbfbf"


def node_fill(n, anchored):
    if anchored:
        return "#ffd400"
    if n["kind"] == "J":
        return "#c8a2ff"
    return "#ff3b3b" if n["power"] else "#2d6cdf"


def render(graph, pos, out, label=True, all_edges=False):
    nodes = {n["id"]: n for n in graph["nodes"]}
    b = graph["board"]
    placed = {r: p for r, p in pos.items() if r in nodes}
    PX = 8.0
    W, H = (b["w"] + 6) * PX, (b["h"] + 6) * PX
    L = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" '
         f'height="{H:.0f}" viewBox="-3 -3 {b["w"] + 6} {b["h"] + 6}">',
         '<rect x="0" y="0" width="%.1f" height="%.1f" fill="#0f3d1a"/>'
         % (b["w"], b["h"])]
    for rt in pos.get("__routes__", []):     # orthogonal routes (ELK)
        L.append('<polyline fill="none" stroke="#00e5ff" stroke-width="0.18" '
                 'stroke-opacity="0.5" points="%s"/>'
                 % " ".join("%.1f,%.1f" % (p[0], p[1]) for p in rt["points"]))
    for e in graph["edges"]:
        if not all_edges and not e.get("draw", True):
            continue                      # clique is for the solver, not the eye
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
    for r, p in placed.items():
        n = nodes[r]
        pts = " ".join("%.2f,%.2f" % q for q in
                       corners(n, p["x"], p["y"], p.get("angle", 0)))
        L.append('<polygon points="%s" fill="%s" fill-opacity="%.2f" '
                 'stroke="#000" stroke-width="0.15" stroke-opacity="0.8"/>'
                 % (pts, node_fill(n, n.get("anchor")),
                    0.55 if n["power"] else 0.7))
    if label:
        for r, p in placed.items():
            n = nodes[r]
            fs = max(1.5, min(n["w"], n["h"]) * 0.5)
            L.append('<text x="%.1f" y="%.1f" font-size="%.1f" '
                     'text-anchor="middle" dominant-baseline="central" '
                     'fill="#fff" font-family="monospace">%s</text>'
                     % (p["x"], p["y"], fs, n.get("label", r)))
    L.append("</svg>")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write("\n".join(L))


def render_png(graph, pos, out, label=True, scale=2.0, all_edges=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch, Polygon as MPoly, Rectangle as MRect

    nodes = {n["id"]: n for n in graph["nodes"]}
    b = graph["board"]
    placed = {r: p for r, p in pos.items() if r in nodes}
    dpi = int(140 * scale)
    fig, ax = plt.subplots(figsize=(b["w"] / 12, b["h"] / 12), dpi=dpi)
    ax.set_facecolor("#0f3d1a")
    ax.add_patch(MRect((0, 0), b["w"], b["h"], fill=False, ec="#7fffa0", lw=1))
    for rt in pos.get("__routes__", []):
        xs = [p[0] for p in rt["points"]]
        ys = [p[1] for p in rt["points"]]
        ax.plot(xs, ys, color="#00e5ff", lw=0.3, alpha=0.5)
    for e in graph["edges"]:
        if not all_edges and not e.get("draw", True):
            continue
        if e["source"] not in placed or e["target"] not in placed:
            continue
        a, t = placed[e["source"]], placed[e["target"]]
        w = e["width"]
        ax.plot([a["x"], t["x"]], [a["y"], t["y"]], color=color(e["current"]),
                lw=0.3 + 3.5 * (w / 18.71) ** 0.6,
                alpha=0.25 + 0.75 * (w / 18.71) ** 0.5, solid_capstyle="round")
    for r, p in placed.items():
        n = nodes[r]
        ax.add_patch(MPoly(corners(n, p["x"], p["y"], p.get("angle", 0)),
                           closed=True, fc=node_fill(n, n.get("anchor")),
                           alpha=0.75, ec="black", lw=0.4, zorder=3))
        if label:
            ax.text(p["x"], p["y"], n.get("label", r), ha="center", va="center",
                    fontsize=2.9, color="white", family="monospace", zorder=4)
    # legend: part fills vs. trace colours are two different scales
    fills = [Patch(fc="#ff3b3b", alpha=0.75, ec="black", lw=0.4,
                   label="power-handling part"),
             Patch(fc="#2d6cdf", alpha=0.75, ec="black", lw=0.4,
                   label="signal part"),
             Patch(fc="#c8a2ff", alpha=0.75, ec="black", lw=0.4,
                   label="connector (free)"),
             Patch(fc="#ffd400", alpha=0.75, ec="black", lw=0.4,
                   label="pinned terminal")]
    trails = [Line2D([0], [0], color=color(c), lw=0.4 + 3.5 * (w / 18.71) ** 0.6,
                     alpha=0.6, label=f"{c:g} A")
              for c, w in ((0.0, 0.25), (1.0, 1.0), (5.0, 5.0), (17.0, 17.0))]
    leg = ax.legend(handles=fills + trails, loc="lower left", fontsize=6.5,
                    ncol=4, framealpha=0.85, facecolor="#101010",
                    edgecolor="#555", labelcolor="white", borderpad=0.5,
                    handlelength=1.4, columnspacing=1.0,
                    title="fill = part type     trace colour/width = net current",
                    title_fontsize=6.5)
    leg.get_title().set_color("#9fe8b0")
    leg.set_zorder(10)
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
    ae = "--all-edges" in sys.argv
    if out.endswith(".png"):
        render_png(graph, pos, out, label="--label" in sys.argv, all_edges=ae)
    else:
        render(graph, pos, out, label="--label" in sys.argv, all_edges=ae)
    print(f"  {data.get('engine','?'):22} n={m['n']:3} "
          f"HPWL {m['hpwl']:6.0f} (w {m['hpwl_w']:7.0f}) "
          f"wire {m['wire']:6.0f}  ovl {m['overlap']:3} out {m['outside']:2}  "
          f"path {m['path']:6.0f} axisR {m['axis_r']:5.2f}  "
          f"in {m['d_in']:5.0f} out {m['d_out']:5.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
