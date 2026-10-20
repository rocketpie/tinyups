#!/usr/bin/env python3
"""Pour the high-current nets on F.Cu (ADR-0008).

The rails cannot be traces: 20 A needs 9.4 mm of 2 oz copper (IPC-2221,
dT = 10 °C), which is a pour by any other name.  Each net gets a copper corridor
of its required width through its own pads, in flow order (greedy nearest
neighbour from the input side), with **solid** pad connections — a thermal
relief is ~0.7 A per pad and would make the pour's bottleneck the spokes, not
the plane (docs/history/0012).

Why a separate step, like `fill_zones.py`: on the freshly-built in-memory board
`pad.GetPosition()` returns the pads' *pre-placement* positions, so the corridor
is swept through the wrong points.  Loaded from a file it is correct.  Sizing
comes from `power_report.py` (`width_for`), so a pour and the gate that checks
it can never disagree.

Usage:  pour_power.py [board.kicad_pcb]     # in place, then fills the zones
"""
from __future__ import annotations

import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from power_report import DESIGN_CURRENT, series_parts, width_for  # noqa: E402
from power_spec import POUR_MARGIN  # noqa: E402

DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
MARGIN = POUR_MARGIN  # mm each side beyond the half width, for the filler to carve
BRIDGE = 0.10        # mm a part's series-pad bridge extends past its pads


def add_power_pours(board, nets=None) -> None:
    """One F.Cu pour per high-current net, swept along its **series** pads.

    Only the parts that carry the net's current are waypoints: a clamp diode or
    a divider tap sits on a 20 A net but carries milliamps (`extract.py`'s
    `conducted()`), so sweeping the corridor through it — as the first version
    did — both demands room that is not needed and makes the corridor wander
    into a neighbour's region, where the filler severs it.  With the series pads
    the pours become local shapes between adjacent power parts, which is how
    high-current copper is actually drawn.

    `nets` limits the pour to a set of net names (e.g. the set a board already
    carried); the default is every net in `DESIGN_CURRENT` except GND.  Nets
    whose required width is below 0.5 mm are left to the router: a 0.1 A rail
    does not need a pour, and its fragment would only confuse the filler and
    freerouting.
    """
    nets = [n for n in (nets or DESIGN_CURRENT)
            if n != "GND" and width_for(DESIGN_CURRENT[n]) >= 0.5]
    series = series_parts()
    anchor = None
    for fp in board.GetFootprints():
        if fp.GetReference() == "1J1":                   # input = start
            p = fp.GetPosition()
            anchor = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

    for net in nets:
        own, core = [], []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetname().lstrip("/") != net:
                    continue
                p = pad.GetPosition()
                xy = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
                r = pad.GetBoundingBox()
                box = (pcbnew.ToMM(r.GetWidth()), pcbnew.ToMM(r.GetHeight()))
                own.append((xy, box))
                if fp.GetReference() in series.get(net, ()):
                    core.append((fp.GetReference(), xy, box))
        pad_box: dict[tuple[float, float], tuple[float, float]] = {}
        for xy, box in own:
            pad_box[xy] = (max(box[0], pad_box.get(xy, (0, 0))[0]),
                           max(box[1], pad_box.get(xy, (0, 0))[1]))
        # A net with no >= 1 A series edge is a sense/tap net: pouring its pads
        # would connect an IC pin to a shunt and call it power. Leave it to the router.
        if len(core) < 2:
            print(f"  {net}: no >=1 A series path; left to the router")
            continue
        pts = [xy for _, xy, _ in core]
        if len(core) >= 2 and len(core) != len(own):
            print(f"  {net}: {len(core)} series pad(s) of {len(own)} "
                  f"({'taps excluded' if len(core) < len(own) else 'all series'})")
        start = min(range(len(pts)),
                    key=lambda i: math.dist(pts[i], anchor) if anchor else 0)
        order, left = [start], set(range(len(pts))) - {start}
        while left:                                       # flow order
            k = min(left, key=lambda i: math.dist(pts[i], pts[order[-1]]))
            order.append(k)
            left.discard(k)
        chain = [(pts[i], pad_box[pts[i]]) for i in order]

        half = width_for(DESIGN_CURRENT[net]) / 2.0 + MARGIN
        ps = pcbnew.SHAPE_POLY_SET()

        def end_half(box, nx, ny):
            """Half-width where the corridor meets a pad: the pad's own
            projection onto the segment normal, so the wide corridor tapers
            into the terminal instead of overhanging the neighbouring net."""
            hp = 0.5 * (abs(nx) * box[0] + abs(ny) * box[1])
            return max(0.3, min(half, hp - 0.05))

        for (a, ba), (b, bb) in zip(chain, chain[1:]):
            ax, ay = a
            bx, by = b
            dx, dy = bx - ax, by - ay
            ln = math.hypot(dx, dy) or 1e-9
            nx, ny = -dy / ln, dx / ln
            hA, hB = end_half(ba, nx, ny), end_half(bb, nx, ny)
            t = min(0.25, 1.2 / ln) if ln > 0 else 0.25
            ax1, ay1 = ax + dx * t, ay + dy * t
            bx1, by1 = ax + dx * (1 - t), ay + dy * (1 - t)
            part = pcbnew.SHAPE_POLY_SET()
            i = part.NewOutline()
            for px, py in (
                    (ax + nx * hA, ay + ny * hA),
                    (ax1 + nx * half, ay1 + ny * half),
                    (bx1 + nx * half, by1 + ny * half),
                    (bx + nx * hB, by + ny * hB),
                    (bx - nx * hB, by - ny * hB),
                    (bx1 - nx * half, by1 - ny * half),
                    (ax1 - nx * half, ay1 - ny * half),
                    (ax - nx * hA, ay - ny * hA)):
                part.Append(pcbnew.FromMM(px), pcbnew.FromMM(py), i)
            ps.BooleanAdd(part)

        # Round the pad end with the pad's inscribed radius, not the corridor
        # half-width: the centre must be *inside* the copper, and a full-width
        # cap would overhang the neighbouring net at a shared part.
        for (px, py), (bw, bh) in chain:
            r = max(0.3, min(half, 0.5 * min(bw, bh) + 0.1))
            part = pcbnew.SHAPE_POLY_SET()
            i = part.NewOutline()
            for k in range(16):
                a = 2 * math.pi * k / 16
                part.Append(pcbnew.FromMM(px + r * math.cos(a)),
                            pcbnew.FromMM(py + r * math.sin(a)), i)
            ps.BooleanAdd(part)

        # A multi-pin terminal is one land, not N separate lobes: bridge the
        # series pads of each part with their group's bbox.  Without it the
        # corridor can clip a middle pin (5Q2.1 sat on the fill boundary and
        # `pour_width` read the whole N_CS pour as split).
        for _, (px, py), (bw, bh) in core:
            x0, y0 = px - bw / 2 - BRIDGE, py - bh / 2 - BRIDGE
            x1, y1 = px + bw / 2 + BRIDGE, py + bh / 2 + BRIDGE
            part = pcbnew.SHAPE_POLY_SET()
            i = part.NewOutline()
            for qx, qy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                part.Append(pcbnew.FromMM(qx), pcbnew.FromMM(qy), i)
            ps.BooleanAdd(part)

        found = board.FindNet(net) or board.FindNet("/" + net)
        if found is None:
            print(f"warn: pour net {net} not found on the board")
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(pcbnew.F_Cu)
        z.SetNetCode(found.GetNetCode())
        z.SetZoneName(f"power pour {net}")
        z.SetMinThickness(pcbnew.FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)   # solid, not thermal
        # NOTE: zone.SetOutline() segfaults in the bindings; fill the zone's own
        # poly set in place instead (verified with a two-rectangle union).
        z.Outline().BooleanAdd(ps)
        board.Add(z)

        # Power first, then signals: keep F.Cu *tracks* out of the corridor.
        # Vias stay allowed so a signal pad inside it can escape to In2/B.Cu;
        # copper pours are allowed (the corridor itself).  The DSN exporter
        # turns this into a wire_keepout, which is exactly what freerouting
        # honours without disabling its via padstack (history 0013).
        ra = pcbnew.ZONE(board)
        ra.SetIsRuleArea(True)
        ra.SetLayer(pcbnew.F_Cu)
        ra.SetZoneName(f"power keepout {net}")
        ra.SetDoNotAllowTracks(True)
        ra.SetDoNotAllowVias(False)
        ra.SetDoNotAllowPads(False)
        ra.SetDoNotAllowFootprints(False)
        ra.SetDoNotAllowCopperPour(False)
        # Keep the keepout at the *required* width, not the full corridor:
        # the margin stays free for signal tracks, so the router keeps its F.Cu
        # escape routes while the pour cannot be cut below its ampacity.
        keep = pcbnew.SHAPE_POLY_SET(ps)
        keep.Deflate(pcbnew.FromMM(max(0.05, MARGIN - 0.05)),
                     pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,
                     pcbnew.FromMM(0.005))
        ra.Outline().BooleanAdd(keep if keep.OutlineCount() else ps)
        board.Add(ra)

        print(f"  pour {net:9} {DESIGN_CURRENT[net]:4.0f} A -> "
              f"{width_for(DESIGN_CURRENT[net]):5.1f} mm corridor "
              f"({len(chain)} pads)")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    board = pcbnew.LoadBoard(path)
    add_power_pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)
    print(f"poured + filled -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
