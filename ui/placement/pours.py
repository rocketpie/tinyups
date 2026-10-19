#!/usr/bin/env python3
"""Write the filled F.Cu power pours of a board as JSON for the placement UI.

The UI's graph is the *placement*; this overlay is the copper the last
`Apply to board + DRC` produced.  It is intentionally a separate file: the
pours belong to the applied board (`build/layout/board.kicad_pcb`), not to the
seed and not to the main board.

Usage:  pours.py [board.kicad_pcb] [pours.json]
"""
from __future__ import annotations

import json
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BOARD = os.path.join(ROOT, "build", "layout", "board.kicad_pcb")
OUT = os.path.join(ROOT, "build", "layout", "pours.json")


def _chain(chain) -> list[list[float]]:
    return [[round(pcbnew.ToMM(chain.CPoint(k).x), 3),
             round(pcbnew.ToMM(chain.CPoint(k).y), 3)]
            for k in range(chain.PointCount())]


def write_pours(board_path: str = BOARD, out_path: str = OUT) -> int:
    board = pcbnew.LoadBoard(board_path)
    pours = []
    for z in board.Zones():
        if z.GetLayer() != pcbnew.F_Cu:
            continue
        net = z.GetNetname().lstrip("/")
        if not net or net == "GND":
            continue
        filled = z.GetFilledPolysList(pcbnew.F_Cu)
        if filled.OutlineCount() == 0:
            continue
        polys = []
        for i in range(filled.OutlineCount()):
            holes = [_chain(filled.Hole(i, h))
                     for h in range(filled.HoleCount(i))]
            polys.append({"outer": _chain(filled.Outline(i)), "holes": holes})
        pours.append({"net": net, "polys": polys})
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"board": os.path.relpath(board_path, ROOT),
                   "pours": pours}, f, separators=(",", ":"))
    print(f"wrote {len(pours)} pour(s) -> {out_path}")
    return 0


def main() -> int:
    board = sys.argv[1] if len(sys.argv) > 1 else BOARD
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    return write_pours(board, out)


if __name__ == "__main__":
    raise SystemExit(main())
