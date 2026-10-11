#!/usr/bin/env python3
"""Route the PCB with freerouting (KiCad has no built-in autorouter).

Flow: export Specctra DSN -> route with freerouting -> import the session.

Requires Java + the freerouting jar, path via ``FREEROUTING_JAR`` (or the
first argument). Example:

    FREEROUTING_JAR=/tmp/freerouting.jar \\
        /opt/eda/venv/bin/python hardware/route.py

The GUI is disabled with a freerouting.json ``{"gui":{"enabled":false}}``.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "tinyups.kicad_pcb")


def main() -> int:
    jar = os.environ.get("FREEROUTING_JAR") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not jar or not os.path.exists(jar):
        print("error: set FREEROUTING_JAR to the freerouting jar", file=sys.stderr)
        return 1

    d = tempfile.mkdtemp(prefix="tinyups-route-")
    dsn, ses = os.path.join(d, "t.dsn"), os.path.join(d, "t.ses")

    board = pcbnew.LoadBoard(PCB)
    pcbnew.ExportSpecctraDSN(board, dsn)

    with open(os.path.join(d, "freerouting.json"), "w") as f:
        f.write('{ "gui": { "enabled": false } }')
    passes = os.environ.get("FREEROUTING_PASSES", "30")
    subprocess.run(["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", passes],
                   check=True, cwd=d)

    board = pcbnew.LoadBoard(PCB)
    pcbnew.ImportSpecctraSES(board, ses)
    pcbnew.SaveBoard(PCB, board)
    print(f"routed -> {PCB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
