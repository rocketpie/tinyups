#!/usr/bin/env python3
"""Routing-quality report for the PCB.

Complements place_metrics.py (which measures placement) by measuring the
*route* and whether it meets a fab rule set:

* trace counts / vias / per-layer usage
* minimum trace width used vs the fab rule  -> "manufacturable at standard?"
* routing completion (unconnected nets)
* inter-block vs internal net count and wirelength (how big the "interface"
  between functional blocks is)

Run:  /opt/eda/venv/bin/python hardware/routing_report.py [board.kicad_pcb]
      FAB_MIN_MM=0.127 ... (default 0.127 mm = 5 mil, JLCPCB standard)
"""
from __future__ import annotations

import os
import statistics
import sys
from collections import Counter

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
FAB_MIN_MM = float(os.environ.get("FAB_MIN_MM", "0.127"))

# mirrors the block map in gen_pcb.py (schematic split A-F)
BLOCKS = {
    "A": {"J1", "F1", "D1", "R1", "R2", "R3", "R4", "R5", "C1", "R6", "R7", "Q1", "U1"},
    "B": {"U2", "Q2", "C2", "C3", "C4", "R8"},
    "C": {"U3", "Q3", "Q4", "Q5", "Q6", "L2", "R9", "R10", "C5", "C6", "C7",
          "C8", "R11", "R12", "R13", "R14", "R15", "R40", "C29", "C30",
          "C31", "R41", "C32", "R42", "C33", "R43", "R44"},
    "D": {"U4", "Q7", "Q8", "Q9", "Q10", "L3", "R16", "R17", "R18", "R19",
          "R20", "R21", "R22", "R23", "R24", "C9", "C10", "C11", "C12",
          "C13", "C14", "C15", "C16", "C17", "C18", "J2"},
    "E": {"U5", "Q11", "Q12", "R25", "Rf0", "Rf1", "Rf2", "Rf3", "Rf4",
          "Cf0", "Cf1", "Cf2", "Cf3", "Cf4", "C19", "C20", "C21", "C22",
          "C23", "R26", "R27", "R28", "R29", "R30", "R45", "R46",
          "J6", "J7"},
    "F": {"U6", "U7", "U8", "J3", "J4", "J5", "Y1", "R31", "R36", "R37",
          "R38", "R32", "R33", "R34", "R35", "D2", "D3", "D4", "D5",
          "C24", "C25", "C26", "C27", "C28"},
}
REF_BLOCK = {r: b for b, refs in BLOCKS.items() for r in refs}


def mm(v):
    return pcbnew.ToMM(v)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    b = pcbnew.LoadBoard(path)

    print(f"board: {path}")
    print(f"  copper layers: {b.GetCopperLayerCount()}   footprints: {len(b.GetFootprints())}")

    # ---- tracks / vias / widths ------------------------------------------ #
    widths, per_layer = [], Counter()
    vias = 0
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
            continue
        widths.append(mm(t.GetWidth()))
        per_layer[b.GetLayerName(t.GetLayer())] += 1
    total = len(widths) + vias
    print(f"  tracks: {len(widths)}   vias: {vias}   (total {total})")
    print("  tracks per layer:", dict(per_layer))
    if widths:
        print(f"  trace width: min {min(widths):.3f}  median "
              f"{statistics.median(widths):.3f}  max {max(widths):.3f} mm")

    # ---- fab compliance --------------------------------------------------- #
    thin = [w for w in widths if w < FAB_MIN_MM - 1e-6]
    verdict = "PASS" if not thin else "FAIL"
    print(f"  fab min trace {FAB_MIN_MM:.3f} mm -> {verdict}"
          f"  ({len(thin)}/{len(widths)} tracks below)")

    # ---- completion ------------------------------------------------------- #
    try:
        conn = b.GetConnectivity()
        conn.RecalculateRatsnest()
        unconnected = conn.GetUnconnectedCount(False)
        print(f"  unconnected items: {unconnected}")
    except Exception as e:
        print("  unconnected: (n/a:", e, ")")

    # ---- inter-block vs internal ----------------------------------------- #
    net_pads: dict[str, list[tuple[str, float, float]]] = {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            nm = pad.GetNetname()
            if not nm:
                continue
            p = pad.GetPosition()
            net_pads.setdefault(nm.lstrip("/"), []).append((ref, mm(p.x), mm(p.y)))

    inter_n = intra_n = 0
    inter_hpwl = intra_hpwl = 0.0
    for nm, pads in net_pads.items():
        xs = [p[1] for p in pads]
        ys = [p[2] for p in pads]
        hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
        blocks = {REF_BLOCK.get(p[0], "?") for p in pads}
        if len(blocks) > 1:
            inter_n += 1
            inter_hpwl += hpwl
        else:
            intra_n += 1
            intra_hpwl += hpwl
    print(f"  nets: {inter_n + intra_n}  "
          f"(inter-block {inter_n}, internal {intra_n})")
    print(f"  inter-block HPWL: {inter_hpwl:8.1f} mm   "
          f"internal HPWL: {intra_hpwl:8.1f} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
