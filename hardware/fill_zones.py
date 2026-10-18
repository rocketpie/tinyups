#!/usr/bin/env python3
"""Fill the copper zones (planes) on the PCB.

Kept separate from the board build because ZONE_FILLER crashes when called on the
freshly-built in-memory board in the pcbnew bindings; on a loaded board it is
fine.

Run:  /opt/eda/venv/bin/python hardware/fill_zones.py
"""
import os
import pcbnew

PCB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tinyups.kicad_pcb")

board = pcbnew.LoadBoard(PCB)
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
pcbnew.SaveBoard(PCB, board)
print(f"filled {len(board.Zones())} zone(s) in {PCB}")
