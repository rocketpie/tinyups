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
from blocks import PREFIXED_BLOCKS as BLOCKS
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
