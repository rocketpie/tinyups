#!/usr/bin/env python3
"""Apply a saved placement to the main board and DRC it.

Loads `hardware/tinyups.kicad_pcb` (the design's board, hand-tuned in this UI),
moves every footprint to the placement's coordinates/orientation, writes a copy
under `build/` (the tracked board is never modified), then runs `kicad-cli pcb
drc` and reports the *placement* violations (courtyard overlaps, off-board).

Unconnected-pad errors are expected (the board is unrouted) and are ignored here.

Usage: apply.py <positions.json> [out.kicad_pcb]
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
BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")


def main() -> int:
    posfile = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        ROOT, "build", "layout", "board.kicad_pcb")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    board = pcbnew.LoadBoard(BOARD)
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
