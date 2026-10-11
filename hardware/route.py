#!/usr/bin/env python3
"""Route the PCB with freerouting (KiCad has no built-in autorouter).

Flow: export Specctra DSN -> relax the design rules to JLCPCB minimums ->
route with freerouting -> import the session -> refill zones.

Why relax the rules: the default 0.2 mm track/clearance cannot escape the
0.4 mm-pitch QFN parts (RP2040, BQ25720, LM5176), so the autorouter strands
those nets. 0.13 mm (= 5 mil, the JLCPCB minimum) fits between the pads.

Requires Java + the freerouting jar (``FREEROUTING_JAR``). Example:

    FREEROUTING_JAR=/opt/freerouting/freerouting.jar \\
        /opt/eda/venv/bin/python hardware/route.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "tinyups.kicad_pcb")
RULE_NM = os.environ.get("ROUTE_RULE_UM", "130")   # DSN units are um


def main() -> int:
    jar = os.environ.get("FREEROUTING_JAR") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not jar or not os.path.exists(jar):
        print("error: set FREEROUTING_JAR to the freerouting jar", file=sys.stderr)
        return 1

    d = tempfile.mkdtemp(prefix="tinyups-route-")
    dsn, ses = os.path.join(d, "t.dsn"), os.path.join(d, "t.ses")

    board = pcbnew.LoadBoard(PCB)
    pcbnew.ExportSpecctraDSN(board, dsn)

    # relax default class width/clearance to the manufacturable minimum
    text = open(dsn).read()
    text = re.sub(r"\(width \d+\)", f"(width {RULE_NM})", text)
    text = re.sub(r"\(clearance \d+\)", f"(clearance {RULE_NM})", text)
    open(dsn, "w").write(text)

    with open(os.path.join(d, "freerouting.json"), "w") as f:
        f.write('{ "gui": { "enabled": false } }')
    passes = os.environ.get("FREEROUTING_PASSES", "15")
    subprocess.run(["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", passes],
                   check=True, cwd=d)

    board = pcbnew.LoadBoard(PCB)
    pcbnew.ImportSpecctraSES(board, ses)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print(f"routed -> {PCB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
