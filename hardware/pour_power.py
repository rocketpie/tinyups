#!/usr/bin/env python3
"""Pour the high-current nets on F.Cu (ADR-0008).

The rails cannot be traces: 20 A needs 9.4 mm of 2 oz copper (IPC-2221,
dT = 10 °C), which is a pour by any other name.  Each net gets a copper corridor
of its required width through its own pads, with **solid** pad connections — a
thermal relief is ~0.7 A per pad and would make the pour's bottleneck the
spokes, not the plane (docs/history/0012).

The corridor is a **trunk with branches**, not a chain through every pad:

* One footprint is one terminal.  Its pads of the net are bridged as one land,
  and the corridor leaves through the middle of that land (the area-weighted
  pad centre), not through whichever pin the chain happened to visit last.
* A part is a branch when the net ends there (a cap or connector to GND), or
  when its other side carries much less current (the charger tap `2R1` on the
  20 A `VIN_SYS` trunk).  Branches attach to the nearest point on the trunk,
  so a decoupling cap does not pull the trunk through it.
* The trunk is ordered by greedy nearest neighbour from the input, with foreign
  pads in the corridor priced in (`PENALTY`).  The fixed board leaves a clear
  `1Q1 -> 3Q1 -> 5Q1` corridor; measuring it is what stops the pour from
  wandering to the caps or through a shunt.

The corridor keeps its **full half-width** at a pad: it is a straight body that
lands on the pad group, not a cone tapering to the pad's inscribed radius.  A
wide round join is added only at a real bend.  The filler then trims the copper
against the neighbouring net's pads, so a Power56 source gets all the space
beside its drain tab, and 1J1/1F1 are not necked to half a pad.

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
from power_report import DESIGN_CURRENT, series_edges, width_for  # noqa: E402
from power_spec import POUR_MARGIN  # noqa: E402

DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
MARGIN = POUR_MARGIN  # mm each side beyond the half width, for the filler to carve
BRIDGE = 0.10        # mm a part's series-pad bridge extends past its pads
OVERSHOOT = 0.35     # mm the corridor body runs into its pad land, so the two overlap
CLEAR = 0.20         # mm pad-clearance padding used for the corridor estimate
PENALTY = 25.0       # mm of detour worth accepting to keep one part out of a corridor
BRANCH_RATIO = 0.75  # a part whose other side carries < this share is a branch


def _part_current(edges, ref) -> float:
    return max((cur for pair, cur in edges.items() if ref in pair), default=0.0)


def _terminals(board, net, edges) -> list[dict]:
    """One terminal per footprint: its pads of `net` as a single land."""
    refs = set()
    for pair in edges:
        refs.update(pair)
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref not in refs:
            continue
        pads = [p for p in fp.Pads()
                if p.GetNetname().lstrip("/") == net]
        if not pads:
            continue
        boxes = []
        for pad in pads:
            bb = pad.GetBoundingBox()
            boxes.append((pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY()),
                          pcbnew.ToMM(bb.GetX() + bb.GetWidth()),
                          pcbnew.ToMM(bb.GetY() + bb.GetHeight())))
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
               max(b[2] for b in boxes), max(b[3] for b in boxes))
        # Area-weighted pad centre: a Power56 drain tab dominates its four
        # pins, while a pure three-pin source group lands on the middle pin.
        sx = sy = area = 0.0
        for pad, b in zip(pads, boxes):
            a = (b[2] - b[0]) * (b[3] - b[1])
            p = pad.GetPosition()
            sx += pcbnew.ToMM(p.x) * a
            sy += pcbnew.ToMM(p.y) * a
            area += a
        port = (sx / area, sy / area)

        nets = {p.GetNetname().lstrip("/") for p in fp.Pads()
                if p.GetNetname().lstrip("/")}
        other = nets - {net, "GND"}
        other_current = max((DESIGN_CURRENT[n] for n in other
                             if n in DESIGN_CURRENT), default=0.0)
        current = _part_current(edges, ref)
        out.append({
            "ref": ref, "box": box, "port": port, "current": current,
            "other": other,
            # A cap/connector ends the net; a shunt to GND is a branch.  A
            # pass FET between two 20 A nets stays on the trunk.  The charger
            # shunt (10 A on N_ACN) is a branch off the 20 A VIN_SYS trunk.
            "branch": not other or other_current < BRANCH_RATIO * current,
        })
    return out


def _obstacles(board, net, own_refs) -> list[tuple]:
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in own_refs:
            continue
        for pad in fp.Pads():
            name = pad.GetNetname().lstrip("/")
            if not name or name == net:
                continue
            bb = pad.GetBoundingBox()
            out.append((ref,
                        pcbnew.ToMM(bb.GetX()) - CLEAR,
                        pcbnew.ToMM(bb.GetY()) - CLEAR,
                        pcbnew.ToMM(bb.GetX() + bb.GetWidth()) + CLEAR,
                        pcbnew.ToMM(bb.GetY() + bb.GetHeight()) + CLEAR))
    return out


def _point_segment(px, py, a, b):
    """Distance from a point to a segment, the closest point, and t."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if not length else max(
        0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy), (qx, qy), t


def _hits(a, b, half, obstacles) -> set[str]:
    """Parts whose pads a corridor of `2 * half` between a and b would touch."""
    out: set[str] = set()
    for ref, x0, y0, x1, y1 in obstacles:
        points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for px, py in (a, b):
            points.append((min(max(px, x0), x1), min(max(py, y0), y1)))
        if min(_point_segment(px, py, a, b)[0] for px, py in points) <= half:
            out.add(ref)
    return out


def _capsule(ps, a, b, half) -> None:
    """The straight body of a corridor; the pad lands close its ends.

    The body runs `OVERSHOOT` past each port so it overlaps the pad-group
    bridge.  Without that overlap a 0.7 mm terminal (a Power56 source pin)
    lands on the very end of the body and the filler drops the joint below its
    minimum thickness.
    """
    if math.dist(a, b) < 1e-6:
        return
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1e-9
    ux, uy = dx / length, dy / length
    ax, ay = a[0] - ux * OVERSHOOT, a[1] - uy * OVERSHOOT
    bx, by = b[0] + ux * OVERSHOOT, b[1] + uy * OVERSHOOT
    nx, ny = -uy * half, ux * half
    part = pcbnew.SHAPE_POLY_SET()
    i = part.NewOutline()
    for px, py in ((ax + nx, ay + ny), (bx + nx, by + ny),
                   (bx - nx, by - ny), (ax - nx, ay - ny)):
        part.Append(pcbnew.FromMM(px), pcbnew.FromMM(py), i)
    ps.BooleanAdd(part)


def _disc(ps, centre, half, steps=24) -> None:
    part = pcbnew.SHAPE_POLY_SET()
    i = part.NewOutline()
    for k in range(steps):
        angle = 2 * math.pi * k / steps
        part.Append(pcbnew.FromMM(centre[0] + half * math.cos(angle)),
                    pcbnew.FromMM(centre[1] + half * math.sin(angle)), i)
    ps.BooleanAdd(part)


def _join(ps, centre, half, directions) -> None:
    """A round join on the side the corridor actually occupies.

    A full disc of the pour half-width at an intermediate terminal reaches
    around the part and takes the space of the pads on the far side (3Q1's
    VIN_SYS tab covers the VBAT pins).  Subtracting the intersection of the
    half-planes opposite each edge keeps the outside of the bend and leaves the
    far side to the neighbouring net.
    """
    if not _needs_join(directions):
        return
    disc = pcbnew.SHAPE_POLY_SET()
    _disc(disc, centre, half)
    clip = None
    for ux, uy in directions:
        px, py = centre
        nx, ny = -uy, ux
        length = half + 2.0
        width = 2.0 * half + 4.0
        part = pcbnew.SHAPE_POLY_SET()
        i = part.NewOutline()
        for qx, qy in ((px + nx * width / 2, py + ny * width / 2),
                       (px + nx * width / 2 - ux * length,
                        py + ny * width / 2 - uy * length),
                       (px - nx * width / 2 - ux * length,
                        py - ny * width / 2 - uy * length),
                       (px - nx * width / 2, py - ny * width / 2)):
            part.Append(pcbnew.FromMM(qx), pcbnew.FromMM(qy), i)
        if clip is None:
            clip = part
        else:
            clip.BooleanIntersection(part)
    if clip is not None and clip.OutlineCount():
        disc.BooleanSubtract(clip)
    if disc.OutlineCount():
        ps.BooleanAdd(disc)


def _needs_join(directions) -> bool:
    """A round join only where the corridor actually bends."""
    if len(directions) >= 3:
        return True
    if len(directions) == 2:
        dot = (directions[0][0] * directions[1][0]
               + directions[0][1] * directions[1][1])
        return dot > math.cos(math.radians(150))
    return False


def _rectangle(ps, box, pad=0.0) -> None:
    x0, y0, x1, y1 = box
    part = pcbnew.SHAPE_POLY_SET()
    i = part.NewOutline()
    for px, py in ((x0 - pad, y0 - pad), (x1 + pad, y0 - pad),
                   (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)):
        part.Append(pcbnew.FromMM(px), pcbnew.FromMM(py), i)
    ps.BooleanAdd(part)


def _foreign_pads(board, net) -> pcbnew.SHAPE_POLY_SET:
    """Copper keepout of every pad on another net, at the board clearance.

    The corridor is sized from the pour half-width, so a wide landing on a
    Power56 drain tab would reach over the source pins on the other side of the
    package (and 1F1's N_AF pad beside +12V_IN).  Letting the filler trim that
    after the fact leaves the *other* net a pad-sized island: the wide zone got
    there first.  Subtracting the foreign pads from the outline gives the gap
    to the smaller pad instead of taking its space.
    """
    keep = pcbnew.SHAPE_POLY_SET()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = pad.GetNetname().lstrip("/")
            if not name or name == net:
                continue
            bb = pad.GetBoundingBox()
            _rectangle(keep, (pcbnew.ToMM(bb.GetX()),
                              pcbnew.ToMM(bb.GetY()),
                              pcbnew.ToMM(bb.GetX() + bb.GetWidth()),
                              pcbnew.ToMM(bb.GetY() + bb.GetHeight())),
                       CLEAR)
    return keep


def _nearest_chain(items, anchor, obstacles, half):
    """Greedy nearest-neighbour order from the input, part-hits priced in."""
    current = min(items, key=lambda t: math.dist(t["port"], anchor))
    order = [current]
    left = [t for t in items if t is not current]
    while left:
        def score(term):
            hits = _hits(current["port"], term["port"], half, obstacles)
            return (math.dist(current["port"], term["port"])
                    + PENALTY * len(hits), hits)
        best = min(left, key=lambda t: score(t)[0])
        order.append(best)
        left.remove(best)
        current = best
    return order


def _trunk(terminals, anchor, obstacles, half):
    """The through-path (trunk) and everything that attaches to it."""
    through = [t for t in terminals if not t["branch"]]
    if len(through) >= 2:
        trunk = _nearest_chain(through, anchor, obstacles, half)
        return trunk, [t for t in terminals if t not in through]
    # A net that ends at both terminals (CELL0) or has one pass part and a
    # connector (PACK+, VOUT12): its two farthest terminals are the trunk.
    best = max(((a, b) for i, a in enumerate(terminals)
                for b in terminals[i + 1:]),
               key=lambda pair: math.dist(pair[0]["port"], pair[1]["port"]))
    return list(best), [t for t in terminals if t not in best]


def _branch_current(term) -> float:
    current = term["current"]
    for net in term["other"]:
        if net in DESIGN_CURRENT and net != "GND":
            current = min(current, DESIGN_CURRENT[net])
    return current


def add_power_pours(board, nets=None) -> None:
    """One F.Cu pour per high-current net, as a trunk with short branches.

    `nets` limits the pour to a set of net names (e.g. the set a board already
    carried); the default is every net in `DESIGN_CURRENT` except GND.  Nets
    whose required width is below 0.5 mm are left to the router: a 0.1 A rail
    does not need a pour, and its fragment would only confuse the filler and
    freerouting.
    """
    nets = [n for n in (nets or DESIGN_CURRENT)
            if n != "GND" and width_for(DESIGN_CURRENT[n]) >= 0.5]
    edges_by_net = series_edges()
    anchor = None
    for fp in board.GetFootprints():
        if fp.GetReference() == "1J1":                   # input = start
            p = fp.GetPosition()
            anchor = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

    for net in nets:
        edges = edges_by_net.get(net, {})
        terminals = _terminals(board, net, edges)
        # A net with no >= 1 A series edge is a sense/tap net: pouring its pads
        # would connect an IC pin to a shunt and call it power. Leave it to the router.
        if len(terminals) < 2:
            print(f"  {net}: no >=1 A series path; left to the router")
            continue
        own_refs = {t["ref"] for t in terminals}
        obstacles = _obstacles(board, net, own_refs)
        half = width_for(DESIGN_CURRENT[net]) / 2.0 + MARGIN
        trunk, branches = _trunk(terminals, anchor or (0, 0), obstacles, half)

        ps = pcbnew.SHAPE_POLY_SET()
        directions: dict[str, list[tuple[float, float]]] = {}
        by_port = {t["port"]: t["ref"] for t in terminals}

        def add_direction(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length > 1e-6:
                directions.setdefault(by_port[a], []).append(
                    (dx / length, dy / length))

        for a, b in zip(trunk, trunk[1:]):
            _capsule(ps, a["port"], b["port"], half)
            add_direction(a["port"], b["port"])
            add_direction(b["port"], a["port"])
        for term in branches:
            current = _branch_current(term)
            branch_half = width_for(current) / 2.0 + MARGIN
            attach = None
            for a, b in zip(trunk, trunk[1:]):
                d, q, t = _point_segment(term["port"][0], term["port"][1],
                                         a["port"], b["port"])
                if 0.0 <= t <= 1.0 and (attach is None or d < attach[0]):
                    attach = (d, q)
            if attach is None:
                q = min((t["port"] for t in trunk),
                        key=lambda p: math.dist(p, term["port"]))
            else:
                q = attach[1]
            _capsule(ps, term["port"], q, branch_half)
            add_direction(term["port"], q)

        for term in terminals:
            _join(ps, term["port"], half, directions.get(term["ref"], []))

        # A multi-pin terminal is one land, not N separate lobes: bridge the
        # pads of each part with their group's bbox.
        for term in terminals:
            _rectangle(ps, term["box"], BRIDGE)

        keepout = _foreign_pads(board, net)
        if keepout.OutlineCount():
            ps.BooleanSubtract(keepout)

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

        route = " -> ".join(t["ref"] for t in trunk)
        print(f"  pour {net:9} {DESIGN_CURRENT[net]:4.0f} A -> "
              f"{2 * half:5.1f} mm corridor, trunk {route}")
        for a, b in zip(trunk, trunk[1:]):
            hits = _hits(a["port"], b["port"], half, obstacles)
            print(f"      {a['ref']:>4} -> {b['ref']:<4} "
                  f"{math.dist(a['port'], b['port']):5.1f} mm, "
                  f"{len(hits)} part(s) in the way"
                  + (f" ({', '.join(sorted(hits))})" if hits else ""))
        for term in branches:
            current = _branch_current(term)
            print(f"      + {term['ref']:>4} branch {current:4.1f} A -> "
                  f"{width_for(current):4.1f} mm")


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
