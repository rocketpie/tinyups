#!/usr/bin/env python3
"""Power-chain clearance: can each high-current net be poured at its width?

A pour is ~10 mm of copper for 20 A on 2 oz (IPC-2221, `power_report.width_for`),
so the *placement* has to leave a channel of that width between each power net's
pads.  This measures it: rasterise the board, take every pad of another net
(plus the clearance) and the board edge as obstacles, then find the widest
channel that joins one net's pads — a disk of width w fits iff the distance to
the nearest obstacle is >= w/2, and every pad must land in **one** connected
component of that free set.

Exit code is non-zero if any net is short, so it can gate a placement.

Why the placement and not the pour: this measurement on ~100 parts is cheap, and
it is the honest form of the "power corridor" the PoC dropped.  A corridor was a
*constraint* and did not fit; a channel width is a *metric* and the placer (or a
human in `make place`) can trade against it.

Usage:  power_channel.py [board.kicad_pcb ...]
"""
from __future__ import annotations

import sys

import numpy as np
import pcbnew
from scipy import ndimage

GRID = 0.25          # mm per cell
CLEAR = 0.2          # mm, the board's netclass clearance
EDGE = 0.5           # mm copper-to-edge
# NOTE: this measures the channel between *all* pads of a net, which is
# conservative — it is stricter than the physics.  A clamp diode or a divider tap
# sits on a 20 A net but carries milliamps (extract.py's `conducted()`: IC /
# diode / bias pins are STUB_A = 0.1 A), and the graph says so in its edge
# weights: for `+12V_IN`/`N_AF` only `1F1->1J1`, `1F1->1R1`, `1Q1->1R1` are
# thick (20 A); `1R7` and `1D1` are on thin edges.  So the width requirement
# belongs to the **series** path only, and a tap merely has to be reachable.
# Refining that needs per-*edge* channels (source pads <-> target pads for every
# graph edge with current >= SERIES_A), not a per-net pad set: selecting a pad
# subset per net is the wrong shape for it.  Until then, over-requiring is the
# safe direction — it can only ask for more room than the copper needs.
SERIES_A = 1.0       # an edge carries power if its current is >= this


def widths(board) -> dict:
    """net -> (required mm, achieved channel mm, where it pinches)."""
    from power_report import DESIGN_CURRENT, width_for

    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
    nx = int(pcbnew.ToMM(bb.GetWidth()) / GRID) + 1
    ny = int(pcbnew.ToMM(bb.GetHeight()) / GRID) + 1

    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            r = p.GetBoundingBox()
            pads.append((fp.GetReference(), p.GetNetname().lstrip("/"),
                         pcbnew.ToMM(r.GetX()), pcbnew.ToMM(r.GetY()),
                         pcbnew.ToMM(r.GetX() + r.GetWidth()),
                         pcbnew.ToMM(r.GetY() + r.GetHeight())))

    out = {}
    for net, need in DESIGN_CURRENT.items():
        # The channel is a pour metric.  A net that fits in a trace (say < 2 A,
        # < 0.5 mm at 2 oz) is not asked to leave a corridor; its pour, if any,
        # is the router's business.
        if width_for(need) < 0.5:
            continue
        own = [p for p in pads if p[1] == net]
        if not own:
            continue
        core = own            # conservative: every pad owes the width (see NOTE)
        free = np.ones((ny, nx), bool)
        edge = max(1, int(EDGE / GRID))
        free[:edge, :] = free[-edge:, :] = False
        free[:, :edge] = free[:, -edge:] = False
        for _, n, ax0, ay0, ax1, ay1 in pads:
            # A pad with no net is not "another net".  TO-252's four
            # unnumbered thermal pads sit under (and are the same copper as)
            # the tab pad 2; counting them as obstacles pinched N_PACKMID from
            # 11.0 mm to 2.0 mm between two FETs.
            if n == net or not n:
                continue
            i0 = max(0, int((ax0 - CLEAR - x0) / GRID))
            i1 = min(nx - 1, int((ax1 + CLEAR - x0) / GRID) + 1)
            j0 = max(0, int((ay0 - CLEAR - y0) / GRID))
            j1 = min(ny - 1, int((ay1 + CLEAR - y0) / GRID) + 1)
            free[j0:j1 + 1, i0:i1 + 1] = False
        dist = ndimage.distance_transform_edt(free) * GRID
        # (row, col) in the distance map — y first, x second.
        cells = [(int(((py0 + py1) / 2 - y0) / GRID),
                  int(((px0 + px1) / 2 - x0) / GRID))
                 for _, _, px0, py0, px1, py1 in core]

        def fits(w):
            lab, _ = ndimage.label(dist >= w / 2)
            ids = {lab[j, i] for j, i in cells if 0 <= j < ny and 0 <= i < nx}
            ids.discard(0)
            return len(ids) == 1

        lo, hi = (0.0, 30.0) if fits(0.3) else (0.0, 0.0)
        while hi - lo > 0.1:
            mid = (lo + hi) / 2
            if fits(mid):
                lo = mid
            else:
                hi = mid
        where = ""
        if lo > 0:
            lab, _ = ndimage.label(dist >= lo / 2)
            seed = next(((j, i) for j, i in cells
                         if 0 <= j < ny and 0 <= i < nx and lab[j, i]), None)
            if seed:
                watch = np.where(lab == lab[seed], dist, np.inf)
                j, i = np.unravel_index(np.argmin(watch), watch.shape)
                where = f"({x0 + i * GRID:.0f},{y0 + j * GRID:.0f})"
        out[net] = (width_for(need), lo, where)
    return out


def main() -> int:
    paths = sys.argv[1:] or ["hardware/tinyups.kicad_pcb"]
    bad = 0
    for path in paths:
        b = pcbnew.LoadBoard(path)
        print(f"board: {path}")
        print(f"  {'net':9} {'need':>6} {'channel':>8}  verdict")
        for net, (need, have, where) in widths(b).items():
            ok = have >= need
            bad += not ok
            note = "ok" if ok else f"SHORT {need / max(have, 1e-3):.1f}x at {where}"
            print(f"  {net:9} {need:6.1f} {have:8.1f}  {note}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
