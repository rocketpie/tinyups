#!/usr/bin/env python3
"""Build one contact sheet PNG with every engine's legalised placement.

Usage: contact_sheet.py <out.png>
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "build", "layout")
ORDER = [
    ("gv-sfdp", "graphviz sfdp   (force)"),
    ("gv-neato", "graphviz neato  (stress)"),
    ("d3force", "d3-force        (force)"),
    ("d3force-incr", "d3-force-incr   (power order)"),
    ("elk", "ELK layered     (orthogonal)"),
    ("dagre", "dagre           (mermaid)"),
    ("gv-dot", "graphviz dot    (layered)"),
]


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(OUT, "contact-sheet.png")
    cols = 3
    cell = 780
    rows = (len(ORDER) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 22)), "#101010")
    d = ImageDraw.Draw(sheet)
    for i, (eng, title) in enumerate(ORDER):
        p = os.path.join(OUT, f"{eng}.png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell - 8, cell - 8))
        cx, cy = (i % cols) * cell, (i // cols) * (cell + 22)
        sheet.paste(im, (cx + 4, cy + 20))
        d.text((cx + 8, cy + 6), title, fill="#00ff7f")
    sheet.save(out)
    print("wrote", out, sheet.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
