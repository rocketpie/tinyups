#!/usr/bin/env python3
"""Current-sense (Kelvin) report.

A current-sense shunt is only as good as its tap.  The controller's sense pins
must leave the shunt **at the pad**, not at the far end of the power pour: the
power copper's IR drop is then added to the shunt voltage.  This report finds
every shunt with a controller sense pair (ACP/ACN, SRP/SRN, CS/CSG,
SENSE/VIN), measures the shunt-to-IC distance, and checks whether a dedicated
track joins the sense pin to the shunt pad.

The error budget is 1 % of the shunt drop:

    V_sense = I * R_shunt
    R_budget = 0.01 * R_shunt
    L_budget = R_budget / R_per_mm     (2 oz outer copper)

Numbers for 2R1 (5 mΩ, 10 A): 50 mV sense, 0.05 mΩ budget; a 9.4 mm pour is
0.026 mΩ/mm (1.9 mm allowed), a 3.6 mm pour 0.068 mΩ/mm (0.73 mm), a 0.2 mm
trace 1.23 mΩ/mm (0.04 mm).  A shared sense path is therefore not viable — the
tap has to be at the pad.

A **dedicated** Kelvin track is different: it carries only the ACP/ACN input
bias (µA), so its own resistance does not add DC error even when it is long.
Length is still a noise/EMI/loop-area concern (`PASS (long)` above LONG_MM),
not a DC gain error.  The `err` column is the **shared power-copper** upper
bound, used when no dedicated track exists (or the board is unrouted).

The report also prints the **total routed sense-trace length** (both sides of
every pair, lower is better).  That number is a metric only; it does not change
the pass/fail, which is about the Kelvin tap.

Usage:  sense_report.py [board.kicad_pcb] [schematic.kicad_sch]
        make sense SENSE_BOARD=build/layout/board-routed.kicad_pcb
"""
from __future__ import annotations

import heapq
import math
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

from power_spec import DESIGN_CURRENT
from power_report import width_for

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")
SCH = os.path.join(ROOT, "hardware", "tinyups.kicad_sch")

RHO = 1.72e-8              # copper, ohm*m
T_2OZ = 70e-6              # 2 oz outer copper, m
BUDGET = 0.01              # 1 % of the shunt drop
LONG_MM = 10.0             # a Kelvin pair should still be short

# Shunt -> design current that actually flows through it (docs/bom.md).
SENSE_CURRENT = {
    "1R1": 25.0,           # LM5069 input current limit
    "2R1": 10.0,           # BQ25720 charger input (RAC)
    "2R2": 8.0,            # BQ25720 charge current (RSR)
    "4R1": 17.0,           # BQ76942 pack current
    "5R3": 17.0,           # LM5176 output current
}

SENSE_FUNCS = {"ACP", "ACN", "SRP", "SRN", "CS", "CSG",
               "SENSE", "SENSE+", "SENSE-", "VIN"}


def netlist(sch: str):
    """(comps, nets, pins) from the schematic netlist."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "t.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist",
                        "--format", "kicadsexpr", "-o", out, sch],
                       check=True, capture_output=True, text=True)
        txt = open(out).read()
    comps: dict[str, dict[str, str]] = {}
    for m in re.finditer(
            r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*'
            r'\(footprint "([^"]*)"\)', txt):
        comps[m.group(1)] = {"value": m.group(2), "footprint": m.group(3)}
    nets: dict[str, list[tuple[str, str, str]]] = {}
    for block in re.split(r"(?=\(net \(code)", txt):
        nm = re.search(r'\(net \(code "\d+"\) \(name "([^"]+)"\)', block)
        if not nm:
            continue
        nets[nm.group(1)] = [
            (m.group(1), m.group(2), m.group(3) or "")
            for m in re.finditer(
                r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)'
                r'(?: \(pinfunction "([^"]*)"\))?', block)]
    pins: dict[str, dict[str, str]] = {}
    for net_nodes in nets.values():
        for ref, pin, fn in net_nodes:
            pins.setdefault(ref, {})[pin] = fn
    return comps, nets, pins


def ohms(value: str) -> float | None:
    m = re.fullmatch(r"([0-9.]+)m", value or "")
    return float(m.group(1)) / 1000.0 if m else None


def board_pad(board, ref: str, pin: str):
    fp = board.FindFootprintByReference(ref)
    if not fp:
        return None
    for p in fp.Pads():
        if p.GetNumber() == pin:
            return p
    return None


def track_path(board, net: str, a, b, tol: float = 0.08) -> float | None:
    """Shortest track/via path length from pad a to pad b, or None.

    Nodes are layer-qualified, so two tracks that merely end at the same x/y
    on different layers are not connected without a via.  The pad attachment
    edges have zero length: the tap is at the pad.
    """
    def pos(pt):
        return (round(pcbnew.ToMM(pt.x) * 20), round(pcbnew.ToMM(pt.y) * 20))

    def key(pt, layer):
        return (layer, *pos(pt))

    tracks = [t for t in board.GetTracks()
              if t.GetNetname().lstrip("/") == net and
              not isinstance(t, pcbnew.PCB_VIA)]
    vias = [t for t in board.GetTracks()
            if t.GetNetname().lstrip("/") == net and
            isinstance(t, pcbnew.PCB_VIA)]
    if not tracks:
        return None

    adj: dict[tuple[int, int, int], list[tuple[tuple[int, int, int], float]]] = {}

    def add(p, q, w):
        adj.setdefault(p, []).append((q, w))
        adj.setdefault(q, []).append((p, w))

    for t in tracks:
        p, q = key(t.GetStart(), t.GetLayer()), key(t.GetEnd(), t.GetLayer())
        w = math.dist((pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)),
                      (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)))
        add(p, q, w)

    # A via joins every track node at its position, across layers.
    at: dict[tuple[int, int], set] = {}
    for t in tracks:
        at.setdefault(pos(t.GetStart()), set()).add(
            key(t.GetStart(), t.GetLayer()))
        at.setdefault(pos(t.GetEnd()), set()).add(
            key(t.GetEnd(), t.GetLayer()))
    for v in vias:
        nodes = list(at.get(pos(v.GetStart()), set()))
        for i in range(1, len(nodes)):
            add(nodes[0], nodes[i], 0.0)

    # Attach each pad to track endpoints in/at it, on the pad's layer (or any
    # layer for a through-hole pad).
    for pad in (a, b):
        node = key(pad.GetPosition(), pad.GetLayer())
        adj.setdefault(node, [])
        r = pad.GetBoundingBox()
        pth = (pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH)
        for t in tracks:
            if not pth and t.GetLayer() != pad.GetLayer():
                continue
            for end in (t.GetStart(), t.GetEnd()):
                if (r.Contains(end) or
                        math.dist((pcbnew.ToMM(end.x), pcbnew.ToMM(end.y)),
                                  (pcbnew.ToMM(pad.GetPosition().x),
                                   pcbnew.ToMM(pad.GetPosition().y))) <= tol):
                    add(key(end, t.GetLayer()), node, 0.0)

    start = key(a.GetPosition(), a.GetLayer())
    goal = key(b.GetPosition(), b.GetLayer())
    if start not in adj or goal not in adj:
        return None
    dist = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        d, n = heapq.heappop(heap)
        if n == goal:
            return d
        if d > dist.get(n, math.inf):
            continue
        for m, w in adj.get(n, ()):
            nd = d + w
            if nd < dist.get(m, math.inf):
                dist[m] = nd
                heapq.heappush(heap, (nd, m))
    return None


def main() -> int:
    board_path = sys.argv[1] if len(sys.argv) > 1 else BOARD
    sch_path = sys.argv[2] if len(sys.argv) > 2 else SCH
    comps, nets, pins = netlist(sch_path)
    board = pcbnew.LoadBoard(board_path)
    routed = len(list(board.GetTracks())) > 0

    # ref -> nets carrying it
    ref_nets: dict[str, list[str]] = {}
    for net, nodes in nets.items():
        for ref, _, _ in nodes:
            ref_nets.setdefault(ref, []).append(net)
    ic_sense: dict[str, dict[str, str]] = {}   # net -> ref -> function
    for net, nodes in nets.items():
        for ref, _, fn in nodes:
            if fn in SENSE_FUNCS:
                ic_sense.setdefault(net, {})[ref] = fn

    print(f"board: {board_path}")
    print(f"  sense current from docs/bom.md; budget {BUDGET:.0%} of the "
          f"shunt drop; 2 oz outer copper")
    print(f"  {'shunt':5} {'IC/pins':16} {'I(A)':>5} {'R(mOhm)':>8} "
          f"{'Vs(mV)':>7} {'dist':>6} {'tap':>9} {'len':>6} {'shared':>7} "
          f"{'sh.err':>6}  verdict")
    fails = 0
    sense_total = 0.0
    span_total = 0.0
    for ref, comp in sorted(comps.items()):
        r_shunt = ohms(comp["value"])
        if not r_shunt or r_shunt >= 1.0:
            continue
        shunt_nets = ref_nets.get(ref, [])
        if len(shunt_nets) != 2:
            continue
        pair = None
        for net_a in shunt_nets:
            for net_b in shunt_nets:
                if net_a >= net_b:
                    continue
                for ic in ic_sense.get(net_a, {}):
                    if ic in ic_sense.get(net_b, {}) and ic != ref:
                        pair = (ic, net_a, net_b,
                                ic_sense[net_a][ic], ic_sense[net_b][ic])
                        break
                if pair:
                    break
            if pair:
                break
        if not pair:
            continue
        ic, net_a, net_b, fn_a, fn_b = pair
        current = SENSE_CURRENT.get(ref, 0.0)
        v_sense = current * r_shunt
        # Narrowest power-side net sets the shared-copper resistance.
        widths = []
        for net in (net_a, net_b):
            c = DESIGN_CURRENT.get(net.lstrip("/"))
            if c:
                widths.append(width_for(c))
        w_mm = min(widths) if widths else 9.4
        r_per_mm = RHO / (w_mm * T_2OZ) * 1e3       # mOhm/mm
        budget_mm = BUDGET * r_shunt / (r_per_mm / 1000.0)

        pad_a = board_pad(board, ref, "1")
        pad_b = board_pad(board, ref, "2")
        ic_a = board_pad(board, ic, [p for p, f in pins.get(ic, {}).items()
                                     if f == fn_a][0]) if fn_a else None
        ic_b = board_pad(board, ic, [p for p, f in pins.get(ic, {}).items()
                                     if f == fn_b][0]) if fn_b else None
        if not (pad_a and pad_b and ic_a and ic_b):
            print(f"  {ref:5} {ic:5} {fn_a}/{fn_b:6}  (pads not found)")
            fails += 1
            continue
        # Pair the shunt pad to the sense pin on the same net.
        if pad_a.GetNetname().lstrip("/") == net_a:
            shunt_a, shunt_b = pad_a, pad_b
        else:
            shunt_a, shunt_b = pad_b, pad_a
        dist = math.dist(
            (pcbnew.ToMM(shunt_a.GetPosition().x),
             pcbnew.ToMM(shunt_a.GetPosition().y)),
            (pcbnew.ToMM(ic_a.GetPosition().x),
             pcbnew.ToMM(ic_a.GetPosition().y)))
        len_a = track_path(board, net_a, shunt_a, ic_a)
        len_b = track_path(board, net_b, shunt_b, ic_b)
        kelvin = len_a is not None and len_b is not None
        sense_len = (len_a + len_b) if kelvin else None
        sense_total += sense_len or 0.0
        span_total += dist
        if not routed:
            tap, shared, err = "unrouted", dist, (r_per_mm / 1000.0) * dist / r_shunt * 100
            verdict = "FAIL  unrouted"
        elif kelvin:
            tap, shared, err = "track", 0.0, 0.0
            verdict = "PASS" if dist <= LONG_MM else "PASS (long)"
        else:
            tap, shared, err = "pour/zone", dist, (r_per_mm / 1000.0) * dist / r_shunt * 100
            verdict = f"FAIL  no Kelvin ({err:.1f}%)"
        fails += not verdict.startswith("PASS")
        len_s = "—" if sense_len is None else f"{sense_len:.1f}"
        print(f"  {ref:5} {ic + ' ' + fn_a + '/' + fn_b:16} "
              f"{current:5.1f} {r_shunt * 1000:8.1f} {v_sense * 1000:7.1f} "
              f"{dist:6.1f} {tap:>9} {len_s:>6} {shared:7.1f} "
              f"{err:5.1f}%  {verdict}")
        if not kelvin:
            print(f"        budget {budget_mm:.2f} mm at {w_mm:.1f} mm / "
                  f"{r_per_mm:.3f} mOhm/mm; tap the sense trace at the "
                  f"{ref} pad")

    print()
    if routed:
        print(f"  sense trace total: {sense_total:.1f} mm (Kelvin paths, both "
              f"sides; lower is better)")
    else:
        print("  sense trace total: — (unrouted; lower is better)")
    print(f"  shunt-to-IC span:  {span_total:.1f} mm (placement context)")
    print(f"  {fails} sense loop(s) not verified")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
