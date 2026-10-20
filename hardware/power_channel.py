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
# The endpoints are the **series** parts (`power_report.series_parts()`, the
# graph's >= 1 A edges): a clamp diode or a divider tap sits on a 20 A net but
# carries milliamps (extract.py's `conducted()`: IC / diode / bias pins are
# STUB_A = 0.1 A), so its pin is not a channel endpoint.  An IC pin is also
# boxed in by its own footprint's other pads and can never clear w/2 — counting
# every pad made the gate drop such pads silently and read the remaining ones.
# Per-*edge* channels (source pads <-> target pads per graph edge) would be
# sharper still; per-series-part is the same shape at one part's granularity.
SERIES_A = 1.0       # an edge carries power if its current is >= this


def widths(board) -> dict:
    """net -> (required mm, achieved channel mm, where it pinches)."""
    from power_report import DESIGN_CURRENT, series_parts, width_for

    series = series_parts()

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
        # Only the series terminals owe the width: an IC sense pin or a clamp
        # tap on the same net carries milliamps and is not a channel endpoint.
        refs = series.get(net)
        core = [p for p in own if p[0] in refs] if refs else own
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
            ids = set()
            half = w / 2
            # A pad is copper, not a point: the channel only has to come within
            # w/2 of its land.  Requiring the pad *centre* to clear every
            # obstacle by w/2 fails at every FET, whose source pins sit 0.6 mm
            # from their own drain tab (and made N_PACKMID read 1.5 mm however
            # far the two sources were moved apart).
            for _, _, px0, py0, px1, py1 in core:
                i0 = max(0, int((px0 - half - x0) / GRID))
                i1 = min(nx - 1, int((px1 + half - x0) / GRID) + 1)
                j0 = max(0, int((py0 - half - y0) / GRID))
                j1 = min(ny - 1, int((py1 + half - y0) / GRID) + 1)
                near = set(lab[j0:j1 + 1, i0:i1 + 1].ravel())
                near.discard(0)
                if not near:
                    return False
                ids |= near
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
