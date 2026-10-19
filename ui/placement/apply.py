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
import shutil
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")
RULES = os.path.join(ROOT, "hardware", "tinyups.kicad_dru")


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

    # The pours were swept through the *old* pad positions; leaving them means
    # the DRC (and the UI feedback read from it) reports every moved pad as a
    # clearance/mask violation.  Regenerate exactly the set the board carried,
    # then fill, so the DRC sees this placement.
    hw = os.path.join(ROOT, "hardware")
    sys.path.insert(0, hw)
    from pour_power import add_power_pours
    for z in list(board.Zones()):
        if z.GetZoneName().startswith(("power pour", "power keepout")):
            # Delete(), not Remove(): Remove() hands ownership to Python and the
            # zone proxies are freed while pcbnew still holds the board lists,
            # which corrupts the next GetFootprints() walk (segfault).
            board.Delete(z)
    # Every net whose copper does not fit a trace, not only the set the source
    # board happened to carry (the old board predates several 17-20 A nets).
    add_power_pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    pcbnew.SaveBoard(out, board)
    # The UI overlay: the filled pours of *this* board, not the main board.
    from pours import write_pours
    write_pours(out, os.path.join(ROOT, "build", "layout", "pours.json"))
    print(f"applied {placed} placements -> {out}")

    # KiCad finds the custom rules (the JLCPCB 5 mil floor) in a sidecar named
    # after the board, so the derived board needs its own copy — without it DRC
    # falls back to the netclass clearance and reports phantom violations (5U1's
    # 0.15 mm QFN pads against the 0.2 mm default).
    if os.path.exists(RULES):
        shutil.copyfile(RULES, os.path.splitext(out)[0] + ".kicad_dru")

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

    # Turn the DRC into placement feedback (unrouted/clearance markers and the
    # measured power-channel shortfalls).  Optional: an install without the
    # power-channel dependencies still gets the board + DRC.
    fb = os.path.join(ROOT, "build", "layout", "route-feedback.json")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "hardware",
                                                      "route_feedback.py"),
                        out, rpt, "-o", fb],
                       capture_output=True, text=True, env=dict(os.environ))
    if r.returncode == 0:
        print((r.stdout or "").rstrip())
    else:
        print("  route feedback skipped: " + (r.stderr or "").strip()[-300:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
