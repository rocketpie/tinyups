#!/usr/bin/env python3
"""Power-path / ampacity report for the PCB.

`routing_report.py` only checks a trace against the *fab minimum width*.  It
cannot see that a 0.127 mm (5 mil) trace is fine for a signal but grossly
undersized for 20 A.  This report closes that gap: for every power net it finds
the **narrowest segment** (the current bottleneck) and compares its ampacity
against the **design current** for that net.

Ampacity model: IPC-2221,  I = k * dT^0.44 * A^0.725  (A in mil^2).
  k = 0.048 (outer layer) / 0.024 (inner layer)
  dT = allowed temperature rise (default 10 C)
  copper: JLCPCB 4-layer default -> 1 oz outer, 0.5 oz inner

Design currents come from docs/requirements.md and docs/bom.md (see
DESIGN_CURRENT).  Where a value is an engineering estimate it is marked.

Run:  /opt/eda/venv/bin/python hardware/power_report.py [board.kicad_pcb]
Exit code is non-zero if any net fails (CI gate).
"""
from __future__ import annotations

import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")

# Allowed temperature rise for the sizing (deg C).
DT = float(os.environ.get("POWER_DT", "10"))
# Copper weights (oz). JLCPCB 4-layer default: 1 oz outer / 0.5 oz inner.
OZ_OUTER = float(os.environ.get("POWER_OZ_OUTER", "1.0"))
OZ_INNER = float(os.environ.get("POWER_OZ_INNER", "0.5"))
OZ_MIL = 1.378  # mils of copper per oz/ft^2

# Design current per net (A).  Source: requirements.md / bom.md.
#   +12V_IN  20 A  12 V/20 A adapter, load + charge (requirements.md §3)
#   N_AF     20 A  same current, downstream of the fuse
#   VIN_SYS  20 A  system input rail (load + charge)
#   VBAT     17 A  pack peak (bom.md: 15 A cont / 17 A peak)
#   VSYS     10 A  charger system node (estimate)
#   VOUT12   17 A  output peak (bom.md: 13 A cont / 17 A peak)
#   SW*      16 A  charger switch nodes (bom.md RSR ~16 A)
#   SW*_OUT  17 A  LM5176 switch nodes (~output peak)
DESIGN_CURRENT = {
    "+12V_IN": 20.0,
    "N_AF": 20.0,
    "VIN_SYS": 20.0,
    "VBAT": 17.0,
    "VSYS": 10.0,
    "VOUT12": 17.0,
    "SW1": 16.0,
    "SW2": 16.0,
    "SW1_OUT": 17.0,
    "SW2_OUT": 17.0,
}


def ampacity(width_mm: float, inner: bool) -> float:
    """IPC-2221 current for a trace of width_mm on an inner/outer layer."""
    k = 0.024 if inner else 0.048
    t = (OZ_INNER if inner else OZ_OUTER) * OZ_MIL          # mils
    area = (width_mm / 0.0254) * t                          # mil^2
    return k * DT ** 0.44 * area ** 0.725                   # A


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    b = pcbnew.LoadBoard(path)

    print(f"board: {path}")
    print(f"  sizing: IPC-2221, dT={DT:.0f} C, copper {OZ_OUTER} oz outer / "
          f"{OZ_INNER} oz inner")

    # per net: narrowest trace, its layer, track count, via count
    worst: dict[str, tuple[float, str]] = {}
    counts: dict[str, int] = {}
    vias: dict[str, int] = {}
    for t in b.GetTracks():
        net = t.GetNetname().lstrip("/")
        if isinstance(t, pcbnew.PCB_VIA):
            vias[net] = vias.get(net, 0) + 1
            continue
        w = pcbnew.ToMM(t.GetWidth())
        layer = b.GetLayerName(t.GetLayer())
        counts[net] = counts.get(net, 0) + 1
        if net not in worst or w < worst[net][0]:
            worst[net] = (w, layer)

    outer = {b.GetLayerName(pcbnew.F_Cu), b.GetLayerName(pcbnew.B_Cu)}

    print()
    print(f"  {'net':10} {'need(A)':>7} {'min(mm)':>7} {'layer':>7} "
          f"{'cap(A)':>7}  verdict")
    n_fail = 0
    for net, need in DESIGN_CURRENT.items():
        if net not in worst:
            print(f"  {net:10} {need:>7.1f} {'-':>7} {'-':>7} {'-':>7}  "
                  f"NO TRACKS (plane/pour?)")
            continue
        w, layer = worst[net]
        cap = ampacity(w, layer not in outer)
        ok = cap >= need
        n_fail += not ok
        note = "PASS" if ok else f"FAIL  (~{need / cap:.0f}x short)"
        print(f"  {net:10} {need:>7.1f} {w:>7.3f} {layer:>7} {cap:>7.2f}  {note}")

    print()
    total = len(DESIGN_CURRENT)
    print(f"  power nets: {n_fail}/{total} FAIL "
          f"(a FAIL means the narrowest segment cannot carry the design current)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
