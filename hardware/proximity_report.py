#!/usr/bin/env python3
"""Placement proximity: what should be close, and how far apart is it?

The placement UI's **belongs-to** force puts each small passive on a ring
around the IC or power switch it serves.  This is that relationship as a
number: every part gets a host from the netlist (the most *specific* shared
net, ties broken by distance, then the nearest IC/switch in its own block),
and the distance to that host is compared with a target.

Targets are deliberately simple and physical:

* **6 mm** for a signal part — a bypass cap, a gate/bias resistor, a boot or
  feedback part.  These are high-frequency or high-impedance nodes; length is
  loop area and pickup.
* **15 mm** for a power-path part — a 470 uF hold-up, a shunt, a power
  inductor.  Bulk/current parts tolerate more length; the sense gate
  (`sense_report.py`) has its own stricter Kelvin budget.

The report is sorted by ``distance - target``, so the first rows are the ones
worth moving.  It is a metric, not a gate: an over-target pair is printed as
``OVER`` but the exit code stays 0 (add ``--strict`` to make it fail).

Usage:  proximity_report.py [board.kicad_pcb] [--strict] [--all]
"""
from __future__ import annotations

import json
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
SIGNAL_MM = 6.0
POWER_MM = 15.0


def _members(graph) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        s = edge["source"] if isinstance(edge["source"], str) else edge["source"]["id"]
        t = edge["target"] if isinstance(edge["target"], str) else edge["target"]["id"]
        out.setdefault(edge["net"], set()).update((s, t))
    return out


def _centre(node, pos) -> tuple[float, float]:
    bx, by, bw, bh = node["bbox"]
    return pos[0] + bx + bw / 2, pos[1] + by + bh / 2


def _critical(node) -> bool:
    """Caps, inductors, power resistors/shunts and gate resistors."""
    if node.get("kind") in ("C", "L") or node.get("power"):
        return True
    if node.get("kind") != "R":
        return False
    return any((p.get("net") or "").startswith("N_G") or p.get("net") == "N_PGATE"
               for p in node.get("pads", []))


def _target(node) -> float:
    power = bool(node.get("power"))
    return POWER_MM if power else SIGNAL_MM


def assign_hosts(graph, positions) -> list[dict]:
    nodes = {n["id"]: n for n in graph["nodes"]}
    members = _members(graph)
    out = []
    for ref, node in nodes.items():
        if node.get("kind") not in tuple("RCDL") or not _critical(node):
            continue
        if ref not in positions:
            continue
        non_gnd = {p.get("net") for p in node.get("pads", [])
                   if p.get("net") and p.get("net") != "GND"}
        rail_bypass = (node.get("kind") == "C" and len(non_gnd) == 1
                       and ((graph.get("nets", {}).get(next(iter(non_gnd)), {})
                             .get("current", 0)) >= 1))
        host_kinds = ("Q", "J") if rail_bypass else ("U", "Q")
        score: dict[str, float] = {}
        for pad in node.get("pads", []):
            net = pad.get("net")
            mem = members.get(net)
            if not net or not mem or len(mem) < 2:
                continue
            for other in mem:
                host = nodes.get(other)
                if other == ref or not host or host.get("kind") not in host_kinds:
                    continue
                score[other] = score.get(other, 0.0) + 1.0 / (len(mem) - 1)
        best = None
        best_score = 0.0
        best_d = float("inf")
        here = _centre(node, positions[ref])
        for other, sc in score.items():
            there = _centre(nodes[other], positions[other])
            d = math.dist(here, there)
            if sc > best_score + 1e-9 or (abs(sc - best_score) < 1e-9 and d < best_d):
                best, best_score, best_d = other, sc, d
        if best is None:
            # Nothing specific: the nearest IC/switch in the same block.
            for other, host in nodes.items():
                if other == ref or host.get("kind") not in ("U", "Q"):
                    continue
                if host.get("block") != node.get("block") or other not in positions:
                    continue
                d = math.dist(here, _centre(host, positions[other]))
                if d < best_d:
                    best, best_d = other, d
        if best is None:
            continue
        out.append({
            "part": ref, "host": best, "score": best_score,
            "d": best_d, "target": _target(node),
            "over": best_d > _target(node),
        })
    out.sort(key=lambda r: (r["d"] - r["target"], r["d"]), reverse=True)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv[1:]
    show_all = "--all" in sys.argv[1:]
    path = args[0] if args else DEFAULT
    board = pcbnew.LoadBoard(path)
    graph = json.load(open(GRAPH))
    positions = {}
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        positions[fp.GetReference()] = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))

    rows = assign_hosts(graph, positions)
    over = [r for r in rows if r["over"]]
    print(f"board: {path}")
    print(f"  {'part':6} {'host':6} {'d':>6} {'target':>7}  verdict")
    shown = rows if show_all or strict else rows[:25]
    for r in shown:
        flag = "OVER" if r["over"] else "ok"
        print(f"  {r['part']:6} {r['host']:6} {r['d']:6.1f} {r['target']:7.0f}  {flag}")
    if not show_all and not strict and len(rows) > len(shown):
        print(f"  ... {len(rows) - len(shown)} more (use --all)")
    mean = sum(r["d"] for r in rows) / len(rows) if rows else 0.0
    worst = rows[0] if rows else None
    print(f"  proximity: {len(rows)} pair(s), {len(over)} over target, "
          f"mean {mean:.1f} mm"
          + (f"; worst {worst['part']} -> {worst['host']} "
             f"{worst['d']:.1f} / {worst['target']:.0f} mm" if worst else ""))
    return 1 if strict and over else 0


if __name__ == "__main__":
    raise SystemExit(main())
