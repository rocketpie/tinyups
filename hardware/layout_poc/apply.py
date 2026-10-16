#!/usr/bin/env python3
"""Apply a layout engine's placement to a real KiCad board and DRC it.

Builds the full (stage-3) board into build/layout/, moves every footprint to
the engine+legalizer coordinates/orientation, saves it, then runs `kicad-cli
pcb drc` and reports the *placement* violations (courtyard overlaps, off-board).
Unconnected-pad errors are expected (nothing is routed) and are ignored here.

Usage: apply.py <legal-positions.json> [out.kicad_pcb]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
import gen_pcb  # noqa: E402


def main() -> int:
    posfile = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        ROOT, "build", "layout", "board.kicad_pcb")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 1. build the full board into our own path (do NOT touch the repo board)
    os.environ["PCB_STAGE"] = "3"
    gen_pcb.OUT = out
    rc = gen_pcb.main()
    if rc != 0:
        return rc

    # 2. move the footprints
    board = pcbnew.LoadBoard(out)
    pos = json.load(open(posfile))["positions"]
    placed = 0
    for fp in board.GetFootprints():
        r = fp.GetReference()
        if r not in pos:
            continue
        p = pos[r]
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p["x"]),
                                       pcbnew.FromMM(p["y"])))
        fp.SetOrientationDegrees(p.get("angle", 0))
        placed += 1
    pcbnew.SaveBoard(out, board)
    print(f"applied {placed} placements -> {out}")

    # 3. DRC and count placement violations
    rpt = os.path.join(ROOT, "build", "layout", "drc.rpt")
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all",
                    "--output", rpt, out], capture_output=True, text=True,
                   env=dict(os.environ))
    txt = open(rpt).read() if os.path.exists(rpt) else ""
    counts: dict[str, int] = {}
    for m in re.finditer(r"^\[(\w+)\]:", txt, re.M):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    print("  DRC violation types:")
    for k in sorted(counts, key=lambda k: -counts[k]):
        print(f"    {k:22} {counts[k]}")
    print(f"  courtyard overlaps: {counts.get('courtyards_overlap', 0)}")
    print(f"  board-edge issues : {counts.get('board_edge_clearance', 0)}"
          f" + {counts.get('copper_edge_clearance', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
