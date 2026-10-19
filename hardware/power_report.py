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

from power_spec import DESIGN_CURRENT

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")

# Allowed temperature rise for the sizing (deg C).
DT = float(os.environ.get("POWER_DT", "10"))
# Copper weights (oz). ADR-0008: 2 oz outer to make the power pours fit;
# inner-layer weight is a fab question (JLCPCB 4-layer default is 0.5 oz).
OZ_OUTER = float(os.environ.get("POWER_OZ_OUTER", "2.0"))
OZ_INNER = float(os.environ.get("POWER_OZ_INNER", "0.5"))
OZ_MIL = 1.378  # mils of copper per oz/ft^2

# DESIGN_CURRENT is the single source of truth in power_spec.py (the old copy
# here had drifted: VSYS/SW1/SW2 at 8 A and PACK+ missing entirely).


def ampacity(width_mm: float, inner: bool) -> float:
    """IPC-2221 current for a trace of width_mm on an inner/outer layer."""
    k = 0.024 if inner else 0.048
    t = (OZ_INNER if inner else OZ_OUTER) * OZ_MIL          # mils
    area = (width_mm / 0.0254) * t                          # mil^2
    return k * DT ** 0.44 * area ** 0.725                   # A


def width_for(current: float, inner: bool = False) -> float:
    """Minimum copper width (mm) for a current: the inverse of ampacity().

    One model, one place: `pour_power.py` sizes its power pours with this, the
    report sizes traces and pours with `ampacity()`, so a pour and the gate that
    checks it can never disagree.
    """
    k = 0.024 if inner else 0.048
    t = (OZ_INNER if inner else OZ_OUTER) * OZ_MIL
    area = (current / (k * DT ** 0.44)) ** (1 / 0.725)      # mil^2
    return area / t * 0.0254                                # mm


CS = pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS
GRAPH = os.path.join(os.path.dirname(HERE), "build", "layout", "graph.json")
SERIES_A = 1.0     # a graph edge carries power if its current is >= this


def series_parts() -> dict:
    """net -> {parts} that carry the current on it, from the graph's edge weights.

    The width requirement belongs to the **series** path.  A clamp diode or a
    divider tap sits on a 20 A net but carries milliamps — `extract.py`'s
    `conducted()` says so (`STUB_A = 0.1 A`), and the graph records it in the
    edge weights: for `+12V_IN`/`N_AF` only `1F1->1J1`, `1F1->1R1`, `1Q1->1R1`
    are thick; `1R7` and `1D1` sit on thin edges.  Sizing a pour (or asking a
    placement for room) across a tap measures the wrong thing.
    """
    import json
    try:
        g = json.load(open(GRAPH))
    except OSError:
        return {}
    out: dict[str, set] = {}
    for e in g["edges"]:
        if e.get("current", 0) >= SERIES_A:
            out.setdefault(e["net"], set()).update((e["source"], e["target"]))
    return out


def pour_width(poly: "pcbnew.SHAPE_POLY_SET", pads: list) -> float:
    """Bottleneck width of a pour: the widest w at which every pad of the net
    is still connected through one region at least w wide.

    Erosion by w/2 leaves exactly the points that a disk of diameter w can
    reach; if all the pads then sit in *one* outline, the copper between them
    is everywhere >= w.  That is the pour's current-carrying width, and it is
    the pad connections and necks that set it, not the pour's area.
    """
    def ok(w):
        p = pcbnew.SHAPE_POLY_SET(poly)
        p.Deflate(pcbnew.FromMM(w / 2), CS, pcbnew.FromMM(0.005))
        if p.OutlineCount() == 0:
            return False
        islands = set()
        for pt in pads:
            for i in range(p.OutlineCount()):
                if p.Contains(pt, i):
                    islands.add(i)
                    break
            else:
                return False                       # a pad fell outside
        return len(islands) == 1

    lo, hi = 0.0, 60.0
    if not ok(0.05):
        return 0.0
    while hi - lo > 0.05:
        mid = (lo + hi) / 2
        if ok(mid):
            lo = mid
        else:
            hi = mid
    return lo


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

    # pads per net, with the owning ref (a pour's connection points), every zone
    series = series_parts()
    pads: dict[str, list] = {}
    pad_widths: dict[str, list] = {}
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            nm = pad.GetNetname().lstrip("/")
            if nm:
                pads.setdefault(nm, []).append((fp.GetReference(),
                                                pad.GetPosition()))
                if fp.GetReference() in series.get(nm, ()):
                    sz = pad.GetSize()
                    pad_widths.setdefault(nm, []).append(
                        min(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)))
    pours: dict[str, list] = {}
    for z in b.Zones():
        net = z.GetNetname().lstrip("/")
        lay = z.GetLayer()
        fp = z.GetFilledPolysList(lay)
        filled = fp.OutlineCount() > 0
        solid = z.GetPadConnection() != pcbnew.ZONE_CONNECTION_THERMAL
        pours.setdefault(net, []).append((lay, fp, filled, solid))

    print()
    print(f"  {'net':10} {'need(A)':>7} {'kind':>5} {'width(mm)':>9} {'layer':>7} "
          f"{'cap(A)':>7}  verdict")
    n_fail = 0
    for net, need in DESIGN_CURRENT.items():
        cands: list[tuple[float, str, float, str]] = []
        if net in worst:
            w, layer = worst[net]
            cands.append((ampacity(w, layer not in outer), "trace", w, layer))
        has_zone = False
        for lay, fp, filled, solid in pours.get(net, []):
            has_zone = True
            layer = b.GetLayerName(lay)
            if not filled:
                print(f"  {net:10} {need:>7.1f} {'pour':>5} {'-':>9} {layer:>7} "
                      f"{'-':>7}  ZONE NOT FILLED (run hardware/fill_zones.py)")
                continue
            # only the parts that carry the net's current owe it the width;
            # a tap (clamp, sense pin, cap) just has to be reachable, which the
            # filler/necks do.  Fall back to every pad if the graph is absent.
            own = pads.get(net, [])
            core = [pt for ref, pt in own if ref in series.get(net, ())] or \
                [pt for _, pt in own]
            # the copper is only as good as the *pad* it flows through: a
            # TO-252 lead or a 1206 fuse pad is ~1.2 mm, i.e. ~4.5 A at 2 oz,
            # however wide the pour around it is
            w_pour = pour_width(fp, core)
            w_pad = min([w for w in pad_widths.get(net, [])] or [w_pour])
            w = min(w_pour, w_pad)
            cands.append((ampacity(w, layer not in outer),
                          "pour" if solid else "therm", w, layer))
        if not cands:
            if not has_zone:
                print(f"  {net:10} {need:>7.1f} {'-':>5} {'-':>9} {'-':>7} {'-':>7}  "
                      f"NO COPPER (no trace, no pour)")
            n_fail += 1
            continue
        # a net with a pour is meant to be carried by it; a trace is the fallback
        pick = next((c for c in cands if c[1] == "pour"), max(cands))
        cap, kind, w, layer = pick
        ok = cap >= need
        n_fail += not ok
        note = "PASS" if ok else f"FAIL  (~{need / cap:.0f}x short)" if cap else "FAIL  (open)"
        print(f"  {net:10} {need:>7.1f} {kind:>5} {w:>9.3f} {layer:>7} "
              f"{cap:>7.2f}  {note}")
        for c_cap, c_kind, c_w, c_layer in cands:
            if c_kind == kind:
                continue
            why = ("thermal pad connections - the bottleneck is the spokes, "
                   "not the plane" if c_kind == "therm" else "trace")
            print(f"  {'':10} {'':>7} {c_kind:>5} {c_w:>9.3f} {c_layer:>7} "
                  f"{c_cap:>7.2f}  ({why})")

    print()
    total = len(DESIGN_CURRENT)
    print(f"  power nets: {n_fail}/{total} FAIL "
          f"(a FAIL means the narrowest segment cannot carry the design current)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
