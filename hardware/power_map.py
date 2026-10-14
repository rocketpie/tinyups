#!/usr/bin/env python3
"""Per-component power map: estimate the power each part dissipates / handles.

For every footprint it looks at the nets on its pads, takes the net's design
current and rail voltage (power_spec.py), and applies a simple loss model:

    resistor (shunt, R<1ohm)  P = I^2 * R          (I = net current)
    resistor (1ohm..1kohm)    series / sense filter, bias only
    resistor (divider/pullup) P = V^2 / R
    FET                       P = I^2 * Rds(on)
    inductor                  P = I^2 * DCR
    capacitor                 ripple: I_rms = V_ripple / |Z|,  P = I_rms^2 * ESR
    fuse                      P = I^2 * R_fuse
    connector                 P = I^2 * R_contact
    IC / crystal / LED        small fixed estimate

A component is **power-handling** if it is a series element carrying
>= MARK_A amps, a capacitor carrying >= MARK_A amps of ripple, or if it
dissipates >= MARK_W.

Writes build/power-map.csv and prints the biggest parts.

Run:  /opt/eda/venv/bin/python hardware/power_map.py [board.kicad_pcb]
"""
from __future__ import annotations

import csv
import math
import os
import re
import sys
from collections import defaultdict

import pcbnew

from power_spec import (CAP_ESR, CONNECTOR_R, DESIGN_CURRENT, FUSE_R,
                        IC_POWER, INDUCTOR_DCR, RAIL_V, RDS_ON,
                        RIPPLE_V_RMS, SW_FREQ)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
OUT = os.path.join(os.path.dirname(HERE), "build", "power-map.csv")

MARK_W = float(os.environ.get("POWER_MARK_W", "1.0"))   # dissipation (W)
MARK_A = float(os.environ.get("POWER_MARK_A", "1.0"))   # current (A)
SERIES = {"shunt", "fet", "inductor", "fuse", "connector"}

# branch consumers that do NOT carry the rail's full current
OVERRIDES = {
    "J5": 0.2,     # fan header (~0.2 A), not the 17 A on VOUT12
    "J7": 0.01,    # cell-sense header (~uA), not the 17 A on CELL0
}


def _num(s: str):
    """Leading number with an optional m/k/M suffix -> float (e.g. 2.2m, 7k15)."""
    m = re.match(r"^([0-9.]+)([mkKM]?)([0-9]*)", s.strip())
    if not m:
        return None
    base, suf, frac = m.group(1), m.group(2), m.group(3)
    mult = {"": 1.0, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6}[suf]
    return float(base + ("." + frac if frac and "." not in base else frac or "")) * mult


def _cap(s: str):
    m = re.match(r"^([0-9.]+)([pnum]?)([0-9]*)", s.strip())
    if not m:
        return None
    base, suf, frac = m.group(1), m.group(2), m.group(3)
    mult = {"": 1.0, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}[suf]
    return float(base + ("." + frac if frac and "." not in base else frac or "")) * mult


def component_power(ref: str, value: str, nets: set[str]):
    """Return (category, I_dc, I_rms, V, param, P_diss, P_thru)."""
    cur = [DESIGN_CURRENT.get(n, 0.0) for n in nets]
    volt = [RAIL_V.get(n, 0.0) for n in nets]
    I = OVERRIDES.get(ref, max(cur) if cur else 0.0)
    V = max(volt) if volt else 0.0
    kind = ref[0]

    if kind == "R":
        R = _num(value)
        if R is None:
            return "resistor?", 0.0, 0.0, V, None, 0.0, 0.0
        if R < 1.0:                       # shunt / current sense
            return "shunt", I, 0.0, V, R, I * I * R, I * V
        if R < 1000.0:                    # series / sense filter (bias only)
            i = 0.001
            return "series", i, 0.0, V, R, i * i * R, i * V
        i = V / R if R else 0.0           # divider / pull-up
        return "divider", i, 0.0, V, R, i * i * R, i * V
    if kind == "C":
        C = _cap(value)
        if not C:
            return "cap", 0.0, 0.0, V, C, 0.0, 0.0
        z = CAP_ESR + 1.0 / (2 * math.pi * SW_FREQ * C)   # |Z| at fsw
        irms = RIPPLE_V_RMS / z
        return "cap", 0.0, irms, V, C, irms * irms * CAP_ESR, V * irms
    if kind == "L":
        return "inductor", I, 0.0, V, INDUCTOR_DCR, I * I * INDUCTOR_DCR, I * V
    if kind == "Q":
        rds = RDS_ON.get(value, 0.003)
        return "fet", I, 0.0, V, rds, I * I * rds, I * V
    if kind == "F":
        return "fuse", I, 0.0, V, FUSE_R, I * I * FUSE_R, I * V
    if kind == "J":
        return "connector", I, 0.0, V, CONNECTOR_R, I * I * CONNECTOR_R, I * V
    if kind == "D":
        p = 0.01 if "LED" in value else 0.0
        return "diode", 0.0, 0.0, V, None, p, 0.0
    if kind == "U":
        return "ic", 0.0, 0.0, V, None, IC_POWER, 0.0
    return "other", I, 0.0, V, None, 0.0, 0.0


def _handles(r) -> bool:
    if r["P_diss_W"] >= MARK_W:
        return True
    if r["category"] in SERIES or r["category"] == "cap":
        return max(r["I_dc_A"], r["I_rms_A"]) >= MARK_A
    return False


def component_is_power(ref: str, value: str, nets: set[str],
                       mark_w: float = MARK_W, mark_a: float = MARK_A) -> bool:
    """True if this component is power-handling (usable without a board)."""
    cat, idc, irms, _v, _p, pdiss, _pt = component_power(ref, value, nets)
    if pdiss >= mark_w:
        return True
    if cat in SERIES or cat == "cap":
        return max(idc, irms) >= mark_a
    return False


def marked_refs(board, mark_w: float = MARK_W, mark_a: float = MARK_A) -> set[str]:
    """Refs of components that are power-handling (used by power_silk.py)."""
    nets: dict[str, set] = defaultdict(set)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname():
                nets[fp.GetReference()].add(pad.GetNetname().lstrip("/"))
    out = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        cat, idc, irms, _v, _p, pdiss, _pt = component_power(
            ref, str(fp.GetValue()), nets.get(ref, set()))
        if pdiss >= mark_w or max(idc, irms) >= mark_a:
            out.add(ref)
    return out


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    b = pcbnew.LoadBoard(path)

    nets: dict[str, set] = defaultdict(set)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname():
                nets[fp.GetReference()].add(pad.GetNetname().lstrip("/"))

    rows = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        cat, idc, irms, V, param, p, pthru = component_power(
            ref, str(fp.GetValue()), nets.get(ref, set()))
        rows.append({"ref": ref, "value": str(fp.GetValue()), "category": cat,
                     "I_dc_A": round(idc, 3), "I_rms_A": round(irms, 3),
                     "V_nom": round(V, 1),
                     "param": "" if param is None else f"{param:.6g}",
                     "P_diss_W": round(p, 3), "P_app_VA": round(pthru, 1),
                     "nets": " ".join(sorted(nets.get(ref, set())))})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    rows.sort(key=lambda r: -max(r["P_diss_W"], r["I_rms_A"], r["I_dc_A"]))
    print(f"wrote {OUT}")
    print(f"\n  {'ref':5} {'cat':9} {'value':9} {'I_dc':>6} {'I_rms':>6} "
          f"{'P_diss':>7} {'P_app':>7}")
    for r in rows[:24]:
        print(f"  {r['ref']:5} {r['category']:9} {r['value']:9} "
              f"{r['I_dc_A']:>6.1f} {r['I_rms_A']:>6.1f} {r['P_diss_W']:>7.2f} "
              f"{r['P_app_VA']:>7.1f}")

    marked = [r for r in rows if _handles(r)]
    print(f"\n  power-handling (diss >= {MARK_W} W, or current >= {MARK_A} A): "
          f"{len(marked)}")
    print("  " + " ".join(sorted(r["ref"] for r in marked)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
