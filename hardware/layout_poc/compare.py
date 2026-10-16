#!/usr/bin/env python3
"""Score every engine's raw and legalised placement and print a table.

Usage: compare.py            # all engines found in build/layout/
"""
from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "build", "layout")
sys.path.insert(0, HERE)
import render  # noqa: E402

GRAPH = os.path.join(OUT, "graph.json")


def score(path):
    data = json.load(open(path))
    pos = dict(data["positions"])
    pos["__routes__"] = data.get("routes", [])
    m = render.metrics(json.load(open(GRAPH)), pos)
    return data.get("engine", os.path.basename(path)), m


def main() -> int:
    graph = json.load(open(GRAPH))
    rows = []
    for eng in ("gv-sfdp", "gv-neato", "d3force", "d3force-incr",
                "elk", "dagre", "gv-dot"):
        raw = os.path.join(OUT, f"pos-{eng}.json")
        leg = os.path.join(OUT, f"leg-{eng}.json")
        if os.path.exists(raw):
            rows.append(("raw", *score(raw)))
        if os.path.exists(leg):
            rows.append(("legal", *score(leg)))
    print(f"{'stage':6} {'engine':22} {'HPWL':>7} {'wHPWL':>8} {'wire':>7} "
          f"{'ovl':>4} {'out':>4} {'path':>6} {'axisR':>6} {'in':>5} {'out':>5}")
    print("-" * 92)
    for stage, name, m in rows:
        print(f"{stage:6} {name:22} {m['hpwl']:7.0f} {m['hpwl_w']:8.0f} "
              f"{m['wire']:7.0f} {m['overlap']:4} {m['outside']:4} "
              f"{m['path']:6.0f} {m['axis_r']:6.2f} "
              f"{m['d_in']:5.0f} {m['d_out']:5.0f}")
    print("-" * 92)
    print("path   = Σ consecutive distance along the power order (chain length)")
    print("axisR  = corr(flow position, position along the input->output axis)")
    print("         1.0 = the power parts walk input->output in order; ~0 = unrelated")
    print("in/out = first power part -> input, last power part -> output (mm)")
    print("hand floorplan (RESUME.md): HPWL 8304, weighted 15476  "
          "(board 150x140, 124 parts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
