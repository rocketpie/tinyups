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

DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
MARGIN = 0.6          # mm each side beyond the half width, for the filler to carve


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
    carried); the default is every net in `DESIGN_CURRENT` except GND.
    """
    nets = [n for n in (nets or DESIGN_CURRENT) if n != "GND"]  # GND = In1 plane
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
                own.append(xy)
                if fp.GetReference() in series.get(net, ()):
                    core.append(xy)
        pts = core if len(core) >= 2 else own
        if len(pts) < 2:
            continue
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
        chain = [pts[i] for i in order]

        half = width_for(DESIGN_CURRENT[net]) / 2.0 + MARGIN
        ps = pcbnew.SHAPE_POLY_SET()
        for (ax, ay), (bx, by) in zip(chain, chain[1:]):
            dx, dy = bx - ax, by - ay
            ln = math.hypot(dx, dy) or 1e-9
            nx, ny = -dy / ln * half, dx / ln * half
            part = pcbnew.SHAPE_POLY_SET()
            i = part.NewOutline()
            for px, py in ((ax + nx, ay + ny), (bx + nx, by + ny),
                           (bx - nx, by - ny), (ax - nx, ay - ny)):
                part.Append(pcbnew.FromMM(px), pcbnew.FromMM(py), i)
            ps.BooleanAdd(part)
        for px, py in chain:                              # round caps
            part = pcbnew.SHAPE_POLY_SET()
            i = part.NewOutline()
            for k in range(16):
                a = 2 * math.pi * k / 16
                part.Append(pcbnew.FromMM(px + half * math.cos(a)),
                            pcbnew.FromMM(py + half * math.sin(a)), i)
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
