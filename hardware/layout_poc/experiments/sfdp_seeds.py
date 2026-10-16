#!/usr/bin/env python3
"""Experiment: is sfdp's negative power-path correlation a seeding artefact?

Hypothesis: `axisR` (corr of flow position with position along the input->output
axis) is negative for sfdp not because the layout is wrong but because a
force-directed engine has no idea which end is the input — its orientation is an
arbitrary choice.  If so:

  * `|axisR|` should stay roughly constant across seeds while the *sign* flips;
  * mirroring the placement about the horizontal middle should flip the sign
    exactly (u -> 1-u  =>  corr -> -corr).

Runs N passes with a randomised seed *and* a shuffled node/edge order, then
reports axisR for each pass and for its mirror.

Usage: experiments/sfdp_seeds.py [passes]
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POC = os.path.dirname(HERE)              # hardware/layout_poc
ROOT = os.path.dirname(os.path.dirname(POC))   # repo root
OUT = os.path.join(ROOT, "build", "layout")
sys.path.insert(0, POC)
import render  # noqa: E402

PY = "/opt/eda/venv/bin/python"
GRAPH = os.path.join(OUT, "graph.json")


def run(cmd, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    subprocess.run(cmd, check=True, env=e, capture_output=True)


def mirror(pos, height):
    return {k: {"x": v["x"], "y": round(height - v["y"], 3),
                "angle": v.get("angle", 0)} for k, v in pos.items()}


def main() -> int:
    passes = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    graph = json.load(open(GRAPH))
    H = graph["board"]["h"]
    print(f"{'pass':5} {'seed':>6} {'HPWL':>7} {'axisR':>7} {'axisR(mirror)':>14} "
          f"{'|axisR|':>8}")
    print("-" * 56)
    for i in range(passes):
        seed = random.randrange(1, 10**6)
        raw = os.path.join(OUT, f"exp-sfdp-{i}.json")
        pos = os.path.join(OUT, f"pos-exp-sfdp-{i}.json")
        leg = os.path.join(OUT, f"leg-exp-sfdp-{i}.json")
        run([PY, os.path.join(POC, "engines", "graphviz.py"),
             GRAPH, raw, "sfdp"], {"GV_SEED": str(seed), "GV_SHUFFLE": "1"})
        run([PY, os.path.join(POC, "fitpos.py"), raw, pos])
        run([PY, os.path.join(POC, "legalize.py"), pos, leg])
        data = json.load(open(leg))
        m = render.metrics(graph, dict(data["positions"]))
        mm = render.metrics(graph, mirror(data["positions"], H))
        print(f"{i:5} {seed:6} {m['hpwl']:7.0f} {m['axis_r']:7.2f} "
              f"{mm['axis_r']:14.2f} {abs(m['axis_r']):8.2f}")
        subprocess.run([PY, os.path.join(POC, "render.py"), leg,
                        os.path.join(OUT, f"exp-sfdp-{i}.png"), "--label"],
                       check=True, capture_output=True)
    print("-" * 56)
    print("sign flipping across seeds while |axisR| stays put => seeding artefact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
