#!/usr/bin/env python3
"""Mark power-handling components with a silkscreen outline.

Draws a rectangle on F.Silkscreen around every footprint that has a pad on a
high-current net, so the power path is visible at a glance in the 2D and 3D
views (and in the render).  Run it after gen_pcb.py.

Run:  /opt/eda/venv/bin/python hardware/power_silk.py [board.kicad_pcb]
"""
from __future__ import annotations

import os
import sys

import pcbnew

from power_map import marked_refs

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")

WIDTH_MM = 0.3


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    b = pcbnew.LoadBoard(path)

    # clear any board-level drawings we added before (idempotent).  Keep the
    # removed wrappers alive: Remove() frees the C++ object and SWIG would
    # otherwise double-free it on GC (segfault).
    _keep = []
    for d in list(b.GetDrawings()):
        if d.GetLayer() == pcbnew.F_SilkS:
            _keep.append(d)
            b.Remove(d)

    refs = marked_refs(b)
    for fp in b.GetFootprints():
        if fp.GetReference() not in refs:
            continue
        bb = fp.GetBoundingBox(False, False)          # body, no text
        pad = pcbnew.FromMM(0.25)
        r = pcbnew.PCB_SHAPE(b)
        r.SetShape(pcbnew.SHAPE_T_RECT)
        r.SetStart(pcbnew.VECTOR2I(bb.GetX() - pad, bb.GetY() - pad))
        r.SetEnd(pcbnew.VECTOR2I(bb.GetRight() + pad, bb.GetBottom() + pad))
        r.SetLayer(pcbnew.F_SilkS)
        r.SetWidth(pcbnew.FromMM(WIDTH_MM))
        b.Add(r)

    pcbnew.SaveBoard(path, b)
    print(f"marked {len(refs)} power components on F.Silkscreen in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
