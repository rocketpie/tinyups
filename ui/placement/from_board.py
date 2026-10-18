#!/usr/bin/env python3
"""Snapshot the main board's placement as a UI seed.

Reads `hardware/tinyups.kicad_pcb` and writes
`ui/placement/placements/main.json` — the UI's default start, exactly the board
as it is now (positions and rotations). No parts are pinned beyond the graph's
terminals (`1J1`, `5J2`); run `make place-seed` after changing the board.

Usage: from_board.py [board.kicad_pcb] [out.json]
"""
from __future__ import annotations

import json
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")
OUT = os.path.join(HERE, "placements", "main.json")


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else BOARD
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    board = pcbnew.LoadBoard(src)

    positions = {}
    for fp in board.GetFootprints():
        p = fp.GetPosition()
        positions[fp.GetReference()] = {
            "x": round(pcbnew.ToMM(p.x), 2),
            "y": round(pcbnew.ToMM(p.y), 2),
            "angle": round(fp.GetOrientationDegrees() % 360, 2),
        }

    doc = {
        "engine": "board",
        "seed": os.path.basename(src),
        "params": {},
        "pinned": [],
        "positions": dict(sorted(positions.items())),
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"wrote {out} ({len(positions)} placements from {src})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
