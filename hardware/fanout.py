#!/usr/bin/env python3
"""Pre-place a radial fanout for the fine-pitch packages.

QFN/TQFP pads are on the package perimeter, so each pad can escape *radially*
on the top layer. Adjacent escapes are one pitch apart (0.4 mm for the QFNs),
which fits a 5 mil trace + 5 mil clearance — so the autorouter no longer has to
squeeze sub-standard traces between pads.

Run:  /opt/eda/venv/bin/python hardware/fanout.py
"""
from __future__ import annotations

import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "tinyups.kicad_pcb")

FINE_PITCH = {"U3", "U4", "U5", "U6"}   # BQ25720, LM5176, BQ76942, RP2040
ESCAPE_MM = 1.6
WIDTH_MM = 0.127


def main() -> int:
    board = pcbnew.LoadBoard(PCB)
    n = 0
    for fp in board.GetFootprints():
        if fp.GetReference() not in FINE_PITCH:
            continue
        c = fp.GetPosition()
        for pad in fp.Pads():
            if pad.GetNetCode() == 0:          # mechanical / exposed pad
                continue
            p = pad.GetPosition()
            dx = pcbnew.ToMM(p.x - c.x)
            dy = pcbnew.ToMM(p.y - c.y)
            d = (dx * dx + dy * dy) ** 0.5
            if d < 0.5:                       # centre thermal pad
                continue
            end = pcbnew.VECTOR2I(
                p.x + pcbnew.FromMM(dx / d * ESCAPE_MM),
                p.y + pcbnew.FromMM(dy / d * ESCAPE_MM))
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(p)
            t.SetEnd(end)
            t.SetWidth(pcbnew.FromMM(WIDTH_MM))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNetCode(pad.GetNetCode())
            board.Add(t)
            n += 1
    pcbnew.SaveBoard(PCB, board)
    print(f"added {n} radial escape stubs ({WIDTH_MM} mm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
