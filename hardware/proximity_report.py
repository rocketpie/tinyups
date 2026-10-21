#!/usr/bin/env python3
"""Placement proximity against the **design intent**.

`hardware/placement_spec.py` says what each part does, which host it belongs to
and how close/far it may be.  This report measures the board against that spec;
it does not infer a host from the netlist.  A cap that happens to sit on the
same rail as four blocks therefore cannot be "attributed" to whichever switch
is nearest: its role and host are written down.

Measures (defined in `placement_spec`):

* ``pad``  — copper-edge gap between the part pad and the host pad on the
  functional net (GND excluded unless named);
* ``edge`` — body/courtyard gap, for thermal and EMI keep-aways;
* ``board_edge`` — body gap to the board outline.

Limits with the same part/measure/min/max/net are grouped: the report shows the
worst host in the group (the smallest gap for a keep-away, the largest for a
reach), so one NTC does not produce ten identical rows.

Usage:  proximity_report.py [board.kicad_pcb] [--strict] [--all] [--part REF]
        make proximity PROX_BOARD=build/layout/board.kicad_pcb

Exit: 0 normally, 1 with ``--strict`` when any limit is violated, 2 when the
spec does not cover the board (a missing role is an error, not a free part).
"""
from __future__ import annotations

import math
import os
import sys

import pcbnew

import placement_spec as spec

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
def _box(item) -> tuple[float, float, float, float]:
    b = item.GetBoundingBox()
    return (pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
            pcbnew.ToMM(b.GetX() + b.GetWidth()),
            pcbnew.ToMM(b.GetY() + b.GetHeight()))


def _gap(a, b) -> float:
    """Shortest distance between two axis-aligned boxes (0 if they overlap)."""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _body(fp) -> tuple[float, float, float, float]:
    """Courtyard box if the footprint has one, else the body box."""
    poly = fp.GetCourtyard(pcbnew.F_CrtYd)
    if poly.OutlineCount() == 0:
        poly = fp.GetCourtyard(pcbnew.B_CrtYd)
    if poly.OutlineCount() > 0:
        xs, ys = [], []
        for i in range(poly.OutlineCount()):
            outline = poly.Outline(i)
            for j in range(outline.PointCount()):
                p = outline.CPoint(j)
                xs.append(pcbnew.ToMM(p.x))
                ys.append(pcbnew.ToMM(p.y))
        return (min(xs), min(ys), max(xs), max(ys))
    return _box(fp)


def _pads(fp, net: str | None):
    out = []
    for p in fp.Pads():
        n = p.GetNetname().lstrip("/")
        if net is not None:
            if n == net:
                out.append(p)
        elif n and n != "GND":
            out.append(p)
    return out


def pad_gap(part, host, net: str | None) -> float | None:
    """Copper-edge gap on the functional net (or the nearest non-GND net)."""
    if net is not None:
        nets = [net]
    else:
        shared = ({p.GetNetname().lstrip("/") for p in part.Pads()}
                  & {p.GetNetname().lstrip("/") for p in host.Pads()})
        nets = sorted(n for n in shared if n and n != "GND")
    best = None
    for n in nets:
        a = _pads(part, n)
        b = _pads(host, n)
        for pa in a:
            for pb in b:
                d = _gap(_box(pa), _box(pb))
                if best is None or d < best:
                    best = d
    return best


def board_edge_gap(fp, board) -> float:
    """Distance from the body to the nearest board outline edge (inside > 0)."""
    b = board.GetBoardEdgesBoundingBox()
    edge = (pcbnew.ToMM(b.GetX()), pcbnew.ToMM(b.GetY()),
            pcbnew.ToMM(b.GetX() + b.GetWidth()),
            pcbnew.ToMM(b.GetY() + b.GetHeight()))
    box = _body(fp)
    return min(box[0] - edge[0], edge[2] - box[2],
               box[1] - edge[1], edge[3] - box[3])


# --------------------------------------------------------------------------- #
# evaluation
# --------------------------------------------------------------------------- #
def evaluate(board) -> list[dict]:
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    rows = []
    for lim in spec.LIMITS:
        part = fps[lim.part]
        if lim.measure == "board_edge":
            d = board_edge_gap(part, board)
        else:
            host = fps[lim.host]
            d = _body_gap(part, host) if lim.measure == "edge" \
                else pad_gap(part, host, lim.net)
            if d is None:
                raise SystemExit(
                    f"{lim.part} -> {lim.host}: no shared non-GND pad net "
                    f"(spec net {lim.net!r}); fix the spec")
        short = lim.min_mm > 0 and d < lim.min_mm
        over = lim.max_mm is not None and d > lim.max_mm
        if short:
            margin = lim.min_mm - d
        elif over:
            margin = d - lim.max_mm
        else:
            slack = [v for v in (
                d - lim.min_mm if lim.min_mm else None,
                lim.max_mm - d if lim.max_mm is not None else None,
            ) if v is not None]
            margin = -min(slack) if slack else 0.0
        rows.append({
            "part": lim.part, "host": lim.host, "measure": lim.measure,
            "net": lim.net, "d": d, "min": lim.min_mm, "max": lim.max_mm,
            "short": short, "over": over,
            "verdict": "SHORT" if short else ("OVER" if over else "ok"),
            "margin": margin, "why": lim.why, "req": lim.req, "src": lim.src,
        })
    return rows


def _body_gap(a, b) -> float:
    return _gap(_body(a), _body(b))


def group(rows: list[dict]) -> list[dict]:
    """One row per (part, measure, min, max, net); worst host in the group."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r["part"], r["measure"], r["min"], r["max"], r["net"])
        groups.setdefault(key, []).append(r)
    out = []
    for members in groups.values():
        worst = max(members, key=lambda r: r["margin"])
        worst["hosts"] = len(members)
        out.append(worst)
    out.sort(key=lambda r: r["margin"], reverse=True)
    return out


def main() -> int:
    argv = sys.argv[1:]
    strict = "--strict" in argv
    show_all = "--all" in argv
    only = None
    positional = []
    i = 0
    while i < len(argv):
        if argv[i] == "--part":
            if i + 1 >= len(argv):
                print("--part needs a reference", file=sys.stderr)
                return 2
            only = argv[i + 1]
            i += 2
            continue
        if not argv[i].startswith("--"):
            positional.append(argv[i])
        i += 1
    path = positional[0] if positional else DEFAULT

    board = pcbnew.LoadBoard(path)
    refs = [fp.GetReference() for fp in board.GetFootprints()]
    problems = spec.validate(refs)
    if problems:
        print(f"spec: {len(problems)} problem(s)")
        for p in problems:
            print(f"  {p}")
        return 2

    rows = evaluate(board)
    groups = group(rows)
    if only:
        groups = [g for g in groups if g["part"] == only]

    bad = [g for g in groups if g["short"] or g["over"]]
    shown = groups if show_all or only else bad
    print(f"board: {path}")
    print(f"spec: {len(spec.ROLES)} parts, {len(spec.LIMITS)} limits, "
          f"{len(spec.FREE)} free, {len(spec.ANCHORS)} anchors")
    if only and only in spec.ROLES:
        print(f"  {only}: {spec.ROLES[only]}")
    print(f"  {'part':6} {'host':10} {'measure':10} {'net':14} {'d':>6} "
          f"{'min':>5} {'max':>5}  verdict  reason")
    for g in shown:
        rng = "-" if g["max"] is None else f"{g['max']:.0f}"
        mn = "-" if not g["min"] else f"{g['min']:.0f}"
        more = f" (+{g['hosts'] - 1})" if g.get("hosts", 1) > 1 else ""
        net = g["net"] or "-"
        print(f"  {g['part']:6} {g['host'] + more:10} {g['measure']:10} "
              f"{net:14} {g['d']:6.1f} {mn:>5} {rng:>5}  "
              f"{g['verdict']:6}  {g['why']}")
    n_short = sum(1 for g in groups if g["short"])
    n_over = sum(1 for g in groups if g["over"])
    print(f"  proximity: {len(groups)} rule group(s), {n_short} too close, "
          f"{n_over} too far, {len(bad)} violated")
    if bad:
        worst = bad[0]
        print(f"  worst: {worst['part']} -> {worst['host']} "
              f"{worst['d']:.1f} mm ({worst['verdict']} by "
              f"{worst['margin']:.1f} mm)")
    return 1 if strict and bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
