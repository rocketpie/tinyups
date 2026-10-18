#!/usr/bin/env python3
"""Legalise an engine's placement into a real board placement.

Every layout engine returns *structure* (who sits near whom), not a legal PCB
placement: parts overlap, sit outside the outline and have no orientation.  This
step turns any engine's raw coordinates into a legal placement:

  1. rotate    — pick the 0/90/180/270 orientation whose pads point at the
                 weighted centroid of the net's other pads (wide nets dominate
                 because they are weighted by required trace width).  A rotation
                 that would collide two *fixed* parts is not applied: the hard
                 pass cannot repair it, and the seed angle is the safer default.
  2. relax     — vectorised de-overlap (push apart along the axis of least
                 penetration) with a soft spring back to the engine position,
                 so the engine's structure survives.
  3. hard pass — Gauss-Seidel fixed point, worst overlap first, that guarantees
                 no courtyard overlap (residual overlap after this is reported).
                 Its clearance is kept above the grid step, so the final snap
                 cannot re-create an overlap.
  4. snap      — to a 0.5 mm placement grid.

The two power terminals (and any part an engine explicitly pinned, e.g. the ends
of the incremental power chain) never move.  `anchor` only *fixes* a part — it
never relocates one: the source file says where, and an engine output already
carries the anchored coordinates (`fitpos.py` snaps them there).  That is the
same rule the interactive UI follows ([history
0004](../../docs/history/0004-anchored-terminals-snap-back-on-load.md)); the
legaliser overriding it is what broke `placements/try5.json`.

There is deliberately no power-corridor keep-out: that belongs to the hand
floorplan, not to a graph-derived placement (see layout_poc/README.md).

Usage: legalize.py <positions.json> <out.json> [--iterations N]
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")
GRID = 0.5
CLEAR = float(os.environ.get("CLEAR", "0.6"))     # relaxation clearance
SPRING = float(os.environ.get("SPRING", "0.02"))  # pull to the engine position


def rot(p, a):
    """Rotate a local offset by `a` degrees in KiCad's Y-DOWN board frame.

    A PCB's y axis grows downward, so a rotation by a is
    (x, y) -> (x cos a + y sin a, -x sin a + y cos a).  Using the textbook
    Y-up form instead is its inverse: identical for a symmetric courtyard,
    mirrored for an asymmetric one (e.g. TO-252-2, whose courtyard sits
    0.84 mm off-centre) — which is how two courtyard overlaps slipped past the
    legaliser while KiCad's DRC found them.
    """
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return (p[0] * c + p[1] * s, -p[0] * s + p[1] * c)


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

    ids = [r for r in raw if r in nodes]
    x = {r: raw[r]["x"] for r in ids}
    y = {r: raw[r]["y"] for r in ids}
    # fixed = anything the source pinned + the graph anchors.  An anchor only
    # *fixes* a part, it does not move it: the source says where (history 0004).
    # Engine outputs already carry the anchored coordinates, so dropping the
    # override changes nothing for them — but it stops the legaliser from
    # dragging an interactive placement's terminals back to the hand floorplan.
    fixed = {r for r in ids if nodes[r].get("anchor") or raw[r].get("pin")}
    tx, ty = dict(x), dict(y)
    bb = {r: local_bbox(nodes[r], 0) for r in ids}

    # ---- rotation: minimise weighted pad -> net-centroid distance ----------
    net_w = {n: graph["nets"][n]["width"] for n in graph["nets"]}
    angle = {r: 0 for r in ids}
    seed_angle = {r: raw[r].get("angle", 0) for r in ids}
    for _round in range(3):
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

    # A rotation that makes two *fixed* parts collide is unrecoverable: the hard
    # pass below never moves a fixed part, so the collision would survive into
    # the board.  The rotation is a proposal, not an order — keep the seed angle
    # for whichever part of the pair was the one turned.

    def world_bbox(r, a):
        lo = local_bbox(nodes[r], a)
        return (lo[0] + x[r], lo[1] + y[r], lo[2] + x[r], lo[3] + y[r])

    fb = {r: world_bbox(r, angle[r]) for r in fixed}

    def hits(a, b):
        return not (fb[a][2] < fb[b][0] or fb[b][2] < fb[a][0]
                    or fb[a][3] < fb[b][1] or fb[b][3] < fb[a][1])

    for _ in range(2 * len(fixed) + 2):
        bad = next(((a, b) for a in sorted(fixed) for b in sorted(fixed)
                    if a < b and hits(a, b)), None)
        if bad is None:
            break
        r = next((q for q in bad if angle[q] != seed_angle[q]), None)
        if r is None:
            print(f"    fixed parts {bad} overlap at their seed angles")
            break
        angle[r] = seed_angle[r]
        fb[r] = world_bbox(r, angle[r])

    # ---- vectorised setup --------------------------------------------------
    n = len(ids)
    X = np.array([x[r] for r in ids])
    Y = np.array([y[r] for r in ids])
    TX = np.array([tx[r] for r in ids])
    TY = np.array([ty[r] for r in ids])
    boxes = [local_bbox(nodes[r], angle[r]) for r in ids]
    HX = np.array([(b[2] - b[0]) / 2 for b in boxes])
    CY = np.array([(b[3] - b[1]) / 2 for b in boxes])
    CX = np.array([(b[0] + b[2]) / 2 for b in boxes])
    CYO = np.array([(b[1] + b[3]) / 2 for b in boxes])
    FIX = np.array([r in fixed for r in ids])

    def fields(eff):
        dx = (X + CX)[:, None] - (X + CX)[None, :]
        dy = (Y + CYO)[:, None] - (Y + CYO)[None, :]
        ox = HX[:, None] + HX[None, :] + eff - np.abs(dx)
        oy = CY[:, None] + CY[None, :] + eff - np.abs(dy)
        m = (ox > 0) & (oy > 0)
        np.fill_diagonal(m, False)
        return m, dx, dy, ox, oy

    # 2. relaxation: de-overlap + soft spring (structure survives)
    for _ in range(iters):
        m, dx, dy, ox, oy = fields(CLEAR)
        np.fill_diagonal(m, False)
        sx = np.where(dx >= 0, 1.0, -1.0)
        sy = np.where(dy >= 0, 1.0, -1.0)
        px = np.where(m & (ox <= oy), 0.5 * ox * sx, 0.0)
        py = np.where(m & (ox > oy), 0.5 * oy * sy, 0.0)
        px[FIX, :] = 0.0
        py[FIX, :] = 0.0
        X = X + np.where(FIX, 0.0, np.clip(px.sum(axis=1) + SPRING * (TX - X),
                                           -3.0, 3.0))
        Y = Y + np.where(FIX, 0.0, np.clip(py.sum(axis=1) + SPRING * (TY - Y),
                                           -3.0, 3.0))
        X = np.clip(X, 1.0 - (CX - HX), BW - 1.0 - (CX + HX))
        Y = np.clip(Y, 1.0 - (CYO - CY), BH - 1.0 - (CYO + CY))
        X[FIX], Y[FIX] = TX[FIX], TY[FIX]

    # 3. hard pass: Gauss-Seidel, worst overlap first.  EFF > GRID so the snap
    #    below cannot reintroduce an overlap.
    EFF = GRID + 0.1
    cxa, cya = X + CX, Y + CYO
    broke = -1
    for rnd in range(20000):
        dx = cxa[:, None] - cxa[None, :]
        dy = cya[:, None] - cya[None, :]
        ox = HX[:, None] + HX[None, :] + EFF - np.abs(dx)
        oy = CY[:, None] + CY[None, :] + EFF - np.abs(dy)
        mask = (ox > 0) & (oy > 0)
        np.fill_diagonal(mask, False)
        pairs = np.argwhere(mask)
        if len(pairs) == 0:
            broke = rnd
            break
        sev = np.minimum(ox[pairs[:, 0], pairs[:, 1]], oy[pairs[:, 0], pairs[:, 1]])
        pairs = pairs[np.argsort(-sev)]
        for i, j in pairs:
            if FIX[i] and FIX[j]:
                continue
            k = i if (FIX[j] or (not FIX[i] and HX[i] * CY[i] <= HX[j] * CY[j])) else j
            if ox[i, j] < oy[i, j]:
                s = 1.0 if dx[i, j] >= 0 else -1.0
                cxa[k] += (s if k == i else -s) * (ox[i, j] + 0.02)
            else:
                s = 1.0 if dy[i, j] >= 0 else -1.0
                cya[k] += (s if k == i else -s) * (oy[i, j] + 0.02)
            if k < n:                              # keep the part on the board
                cxa[k] = min(max(cxa[k], 1.0 + HX[k]), BW - 1.0 - HX[k])
                cya[k] = min(max(cya[k], 1.0 + CY[k]), BH - 1.0 - CY[k])
        for i in np.argwhere(FIX).ravel():
            cxa[i], cya[i] = TX[i] + CX[i], TY[i] + CYO[i]
    X, Y = cxa - CX, cya - CYO
    if os.environ.get("DBG"):
        left = 0
        for i in range(n):
            for j in range(i + 1, n):
                if (min(X[i] + CX[i] + HX[i], X[j] + CX[j] + HX[j])
                        - max(X[i] + CX[i] - HX[i], X[j] + CX[j] - HX[j]) > 0
                        and min(Y[i] + CYO[i] + CY[i], Y[j] + CYO[j] + CY[j])
                        - max(Y[i] + CYO[i] - CY[i], Y[j] + CYO[j] - CY[j]) > 0):
                    left += 1
        print(f"    hard pass broke at rnd {broke}, {left} residual overlaps")

    out = {}
    for i, r in enumerate(ids):
        if FIX[i]:
            px, py = TX[i], TY[i]          # pinned/anchored: keep its seed
        else:
            px, py = float(X[i]), float(Y[i])
        out[r] = {"x": round(px / GRID) * GRID, "y": round(py / GRID) * GRID,
                  "angle": angle[r]}
    json.dump({"engine": data.get("engine", "?") + "+legal",
               "positions": out}, open(dst, "w"), indent=1)
    print(f"legalize {data.get('engine','?'):22} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
