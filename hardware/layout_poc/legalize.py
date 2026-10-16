#!/usr/bin/env python3
"""Legalise an engine's placement into a real board placement.

Every layout engine returns *structure* (who sits near whom), not a legal PCB
placement: parts overlap, sit outside the outline, intrude into the reserved
power corridor and have no orientation.  This step turns any engine's raw
coordinates into a legal placement:

  1. rotate   — pick the 0/90/180/270 orientation whose pads point at the
                weighted centroid of the net's other pads (pads get closer to
                where they are going; wide nets dominate because they are
                weighted by required trace width).
  2. de-overlap — push overlapping courtyards apart along the axis of least
                penetration (spiral / relaxation), keeping a soft spring to the
                engine's proposed position so the structure survives.
  3. constrain — clamp inside the 150x140 outline, keep parts out of the power
                corridor, pin the connectors to their anchors.
  4. snap     — to a 0.5 mm placement grid.

Usage: legalize.py <positions.json> <out.json> [--iterations N]
"""
from __future__ import annotations

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")
GRID = 0.5
CLEAR = 0.6          # mm courtyard clearance
SPRING = float(os.environ.get("SPRING", "0.02"))   # pull to the engine position
CORRIDOR_PUSH = 0.5


def rot(p, a):
    c, s = round(math.cos(math.radians(a))), round(math.sin(math.radians(a)))
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def local_bbox(node, angle):
    bx, by, bw, bh = node["bbox"]
    xs = [rot(p, angle) for p in
          ((bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh))]
    return (min(p[0] for p in xs), min(p[1] for p in xs),
            max(p[0] for p in xs), max(p[1] for p in xs))


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    iters = 4000
    if "--iterations" in sys.argv:
        iters = int(sys.argv[sys.argv.index("--iterations") + 1])
    graph = json.load(open(GRAPH))
    data = json.load(open(src))
    raw = data["positions"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    board = graph["board"]
    BW, BH = board["w"], board["h"]
    cx0, cx1, cy0, cy1 = board["corridor"]

    ids = [r for r in raw if r in nodes]
    x = {r: raw[r]["x"] for r in ids}
    y = {r: raw[r]["y"] for r in ids}
    fixed = {r for r in ids if nodes[r].get("anchor")}
    for r in fixed:
        x[r], y[r] = nodes[r]["anchor"]
    tx, ty = dict(x), dict(y)
    bb = {r: local_bbox(nodes[r], 0) for r in ids}

    # ---- rotation: minimise weighted pad -> net-centroid distance ----------
    net_w = {n: graph["nets"][n]["width"] for n in graph["nets"]}
    angle = {r: 0 for r in ids}
    for _round in range(3):
        # centroid of every net's pads at the current angles
        acc: dict[str, list] = {}
        for r in ids:
            for p in nodes[r]["pads"]:
                if not p["net"]:
                    continue
                rx, ry = rot((p["dx"], p["dy"]), angle[r])
                acc.setdefault(p["net"], []).append((x[r] + rx, y[r] + ry))
        cen = {n: (sum(q[0] for q in v) / len(v), sum(q[1] for q in v) / len(v))
               for n, v in acc.items()}
        for r in ids:
            if len(nodes[r]["pads"]) < 2:
                continue
            best, best_cost = angle[r], None
            for a in (0, 90, 180, 270):
                cost = 0.0
                for p in nodes[r]["pads"]:
                    if not p["net"] or p["net"] not in cen:
                        continue
                    rx, ry = rot((p["dx"], p["dy"]), a)
                    cxx, cyy = cen[p["net"]]
                    cost += net_w.get(p["net"], 0.25) * math.dist(
                        (x[r] + rx, y[r] + ry), (cxx, cyy))
                if best_cost is None or cost < best_cost - 1e-9:
                    best, best_cost = a, cost
            angle[r] = best
        bb = {r: local_bbox(nodes[r], angle[r]) for r in ids}

    def box(r, px=None, py=None):
        px = x[r] if px is None else px
        py = y[r] if py is None else py
        b = bb[r]
        return (px + b[0], py + b[1], px + b[2], py + b[3])

    # ---- relaxation: de-overlap + soft spring + constraints ----------------
    # vectorised: ~5k iterations over 124 parts is cheap with numpy.
    import numpy as np
    idx = {r: i for i, r in enumerate(ids)}
    n = len(ids)
    X = np.array([x[r] for r in ids])
    Y = np.array([y[r] for r in ids])
    TX = np.array([tx[r] for r in ids])
    TY = np.array([ty[r] for r in ids])
    HX = np.array([(lambda r: (r[2] - r[0]) / 2)(local_bbox(nodes[r], angle[r]))
                   for r in ids])
    CY = np.array([(lambda r: (r[3] - r[1]) / 2)(local_bbox(nodes[r], angle[r]))
                   for r in ids])
    CX = np.array([(lambda r: (r[0] + r[2]) / 2)(local_bbox(nodes[r], angle[r]))
                   for r in ids])
    CYO = np.array([(lambda r: (r[1] + r[3]) / 2)(local_bbox(nodes[r], angle[r]))
                    for r in ids])
    fixedmask = np.array([r in fixed for r in ids])
    inboard = np.ones(n, bool)
    b = np.array([1.0] * n)
    for i, r in enumerate(ids):
        if nodes[r]["kind"] == "J":
            inboard[i] = False

    for it in range(iters):
        dx = X[:, None] - X[None, :]
        dy = Y[:, None] - Y[None, :]
        # centre offsets of the bbox relative to the footprint origin
        cx = CX[:, None] - CX[None, :] + dx
        cy = CYO[:, None] - CYO[None, :] + dy
        ox = HX[:, None] + HX[None, :] + CLEAR - np.abs(cx)
        oy = CY[:, None] + CY[None, :] + CLEAR - np.abs(cy)
        mask = (ox > 0) & (oy > 0)
        np.fill_diagonal(mask, False)
        sx = np.where(cx >= 0, 1.0, -1.0)
        sy = np.where(cy >= 0, 1.0, -1.0)
        alongx = mask & (ox < oy)
        alongy = mask & ~(ox < oy)
        px = np.where(alongx, 0.5 * ox * sx, 0.0)
        py = np.where(alongy, 0.5 * oy * sy, 0.0)
        px[fixedmask, :] = 0.0          # fixed parts do not move
        py[fixedmask, :] = 0.0
        disp_x = px.sum(axis=1)
        disp_y = py.sum(axis=1)
        disp_x += SPRING * (TX - X)
        disp_y += SPRING * (TY - Y)
        # corridor keep-out
        lo, hi = X + (CX - HX), X + (CX + HX)
        ylo = Y + (CYO - CY)
        yhi = Y + (CYO + CY)
        inband = (lo < cx1) & (hi > cx0) & (ylo < cy1) & (yhi > cy0) & inboard
        mid = (cx0 + cx1) / 2
        disp_x = np.where(inband, disp_x + CORRIDOR_PUSH * (cx1 - cx0) / 2
                          * np.where(X >= mid, 1.0, -1.0), disp_x)
        disp_x = np.clip(disp_x, -3.0, 3.0)
        disp_y = np.clip(disp_y, -3.0, 3.0)
        X = X + np.where(fixedmask, 0.0, disp_x)
        Y = Y + np.where(fixedmask, 0.0, disp_y)
        X = np.clip(X, 1.0 - (CX - HX), BW - 1.0 - (CX + HX))
        Y = np.clip(Y, 1.0 - (CYO - CY), BH - 1.0 - (CYO + CY))
        X[fixedmask] = TX[fixedmask]
        Y[fixedmask] = TY[fixedmask]
        if os.environ.get("DBG") and it % 1000 == 0:
            print(f"    it {it:5} overlaps {int(mask.sum())//2:4} "
                  f"maxpx {np.abs(disp_x).max():.2f}")

    for i, r in enumerate(ids):
        x[r], y[r] = float(X[i]), float(Y[i])

    # ---- hard pass: guarantee no courtyard overlap and no corridor intrude --
    # The corridor is injected as one extra *fixed* obstacle node so the overlap
    # solver and the keep-out share a single fixed point (two separate passes
    # just oscillate against each other).  Gauss-Seidel: shove the movable part
    # out of its worst overlap by the full penetration.
    EFF = GRID + 0.1      # must exceed the grid step so snapping cannot overlap
    midx, midy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
    CXe = np.append(CX, midx)
    CYOe = np.append(CYO, midy)
    HXe = np.append(HX, (cx1 - cx0) / 2)
    CYe = np.append(CY, (cy1 - cy0) / 2)
    fixede = np.append(fixedmask, True)
    ignore = np.zeros((n + 1, n + 1), bool)
    for i in np.argwhere(~inboard).ravel():      # connectors may sit in it
        ignore[i, n] = ignore[n, i] = True
    cxa = np.append(X + CX, midx)
    cya = np.append(Y + CYO, midy)
    for rnd in range(4000):
        dx = cxa[:, None] - cxa[None, :]
        dy = cya[:, None] - cya[None, :]
        ox = HXe[:, None] + HXe[None, :] + EFF - np.abs(dx)
        oy = CYe[:, None] + CYe[None, :] + EFF - np.abs(dy)
        mask = (ox > 0) & (oy > 0) & ~ignore
        np.fill_diagonal(mask, False)
        pairs = np.argwhere(mask)
        if len(pairs) == 0:
            break
        for i, j in pairs:
            if fixede[i] and fixede[j]:
                continue
            # move the movable one; if both free, move the smaller (lighter)
            if fixede[j] or (not fixede[i] and
                             HXe[i] * CYe[i] <= HXe[j] * CYe[j]):
                k = i
            else:
                k = j
            if ox[i, j] < oy[i, j]:
                s = 1.0 if dx[i, j] >= 0 else -1.0
                cxa[k] += (s if k == i else -s) * (ox[i, j] + 0.02)
            else:
                s = 1.0 if dy[i, j] >= 0 else -1.0
                cya[k] += (s if k == i else -s) * (oy[i, j] + 0.02)
            if k < n:                              # keep the part on the board
                cxa[k] = min(max(cxa[k], 1.0 + HXe[k]), BW - 1.0 - HXe[k])
                cya[k] = min(max(cya[k], 1.0 + CYe[k]), BH - 1.0 - CYe[k])
        cxa[n], cya[n] = midx, midy
        for i in np.argwhere(fixedmask).ravel():
            cxa[i], cya[i] = TX[i] + CX[i], TY[i] + CYO[i]
    X, Y = cxa[:n] - CX, cya[:n] - CYO
    for i, r in enumerate(ids):
        x[r], y[r] = float(X[i]), float(Y[i])
        if fixedmask[i]:
            x[r], y[r] = nodes[r]["anchor"]

    out = {}
    for r in ids:
        out[r] = {"x": round(x[r] / GRID) * GRID, "y": round(y[r] / GRID) * GRID,
                  "angle": angle[r]}
    json.dump({"engine": data.get("engine", "?") + "+legal",
               "positions": out}, open(dst, "w"), indent=1)
    print(f"legalize {data.get('engine','?'):16} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
