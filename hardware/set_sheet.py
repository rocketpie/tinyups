#!/usr/bin/env python3
"""Place the board on the drawing sheet and set the title block.

* moves all board content so it sits inside the sheet border (KiCad's frame is
  inset ~10 mm from the page origin, so content at (0,0) renders outside it),
* sets the title block,
* sets the paper size (A3, which fits the 145 x 138 mm board).

Run:  /opt/eda/venv/bin/python hardware/set_sheet.py
"""
from __future__ import annotations

import os

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "tinyups.kicad_pcb")
ORIGIN_MM = 20.0          # where the board's top-left corner should sit
PAPER = "A4"


def main() -> int:
    board = pcbnew.LoadBoard(PCB)

    bb = board.GetBoardEdgesBoundingBox()
    dx = pcbnew.FromMM(ORIGIN_MM) - bb.GetX()
    dy = pcbnew.FromMM(ORIGIN_MM) - bb.GetY()
    board.Move(pcbnew.VECTOR2I(dx, dy))

    tb = board.GetTitleBlock()
    tb.SetTitle("TinyUPS")
    tb.SetDate("2026-10-12")
    tb.SetRevision("0.1")
    tb.SetCompany("TinyUPS")
    board.SetTitleBlock(tb)

    try:
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    except Exception:
        pass
    pcbnew.SaveBoard(PCB, board)

    # paper size is easiest to set in the file text
    text = open(PCB).read()
    for p in ("A4", "A3", "A2", "A1", "A0", "USLetter", "USLegal", "User"):
        text = text.replace(f'(paper "{p}")', f'(paper "{PAPER}")')
    open(PCB, "w").write(text)
    print(f"placed on sheet, paper {PAPER}, title block set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
