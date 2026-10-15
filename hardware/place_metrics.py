#!/usr/bin/env python3
"""Placement-quality metrics for the PCB.

Quantifies "good placement" the way EDA tools do, so two placements can be
compared numerically:

* HPWL        - half-perimeter wirelength: for every net, the width+height of
                the bounding box of its pads, summed. The classic placement
                cost; lower is better.
* weighted    - same, but high-current nets count more (IR drop / loop area).
* power HPWL  - HPWL of just the high-current nets (the ones that matter most).
* decap       - mean distance from each IC supply pin to its nearest decoupling
                capacitor on the same net (should be small).

Run:  /opt/eda/venv/bin/python hardware/place_metrics.py [board.kicad_pcb]
"""
from __future__ import annotations

import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(HERE, "tinyups.kicad_pcb")
sys.path.insert(0, HERE)
from power_map import marked_refs  # noqa: E402
from blocks import kind as _kind  # noqa: E402
from blocks import CORRIDOR_MM  # noqa: E402

# nets where copper length/loop area matters most (weight them)
POWER_NETS = {
    "GND", "PGND", "+12V_IN", "VIN_SYS", "VBAT", "VOUT12", "SW1", "SW2",
    "SW1_OUT", "SW2_OUT", "+3V3", "N_CS", "N_ACL", "N_ACN", "VSYS",
}
POWER_WEIGHT = 6.0


def mm(v) -> float:
    return pcbnew.ToMM(v)


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    board = pcbnew.LoadBoard(path)

    # collect pads per net
    nets: dict[str, list[tuple[float, float]]] = {}
    pad_ref: dict[str, list[str]] = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = pad.GetNetname()
            if not name:
                continue
            p = pad.GetPosition()
            nets.setdefault(name, []).append((mm(p.x), mm(p.y)))
            pad_ref.setdefault(name, []).append(f"{fp.GetReference()}.{pad.GetNumber()}")

    total = weighted = power = 0.0
    rows = []
    for name, pts in nets.items():
        key = name.lstrip("/")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
        total += hpwl
        w = POWER_WEIGHT if key in POWER_NETS else 1.0
        weighted += w * hpwl
        if key in POWER_NETS:
            power += hpwl
        rows.append((hpwl, key, len(pts)))

    print(f"board: {path}")
    print(f"  nets:              {len(nets)}")
    print(f"  total HPWL:        {total:9.1f} mm")
    print(f"  weighted HPWL:     {weighted:9.1f} mm  (power nets x{POWER_WEIGHT:g})")
    print(f"  power-net HPWL:    {power:9.1f} mm")
    print("  worst power nets:")
    for hpwl, name, n in sorted(rows, reverse=True):
        if name in POWER_NETS:
            print(f"    {hpwl:8.1f} mm  {name}  ({n} pads)")

    # decoupling: nearest capacitor pad on the same net for each IC supply pin
    ic_pins = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if _kind(ref) != "U":
            continue
        for pad in fp.Pads():
            nm = pad.GetNetname()
            if nm.lstrip("/") in (POWER_NETS | {"N_DVDD", "N_REG1"}):
                ic_pins.append((ref, pad.GetNumber(), nm, mm(pad.GetPosition().x),
                                mm(pad.GetPosition().y)))
    dists = []
    for ref, num, nm, x, y in ic_pins:
        best = None
        for fp in board.GetFootprints():
            if _kind(fp.GetReference()) != "C":
                continue
            for pad in fp.Pads():
                if pad.GetNetname() != nm:
                    continue
                d = ((mm(pad.GetPosition().x) - x) ** 2 +
                     (mm(pad.GetPosition().y) - y) ** 2) ** 0.5
                best = d if best is None else min(best, d)
        if best is not None:
            dists.append(best)
    if dists:
        print(f"  decap distance:    mean {sum(dists)/len(dists):5.1f} mm, "
              f"max {max(dists):5.1f} mm  ({len(dists)} supply pins)")

    # power-path score: are the power-handling parts on the centreline, and do
    # they run straight in the flow direction (back -> front = increasing y)?
    refs = marked_refs(board)
    pts = []
    for fp in board.GetFootprints():
        if fp.GetReference() in refs:
            p = fp.GetPosition()
            pts.append((mm(p.x), mm(p.y), fp.GetReference()))
    if pts:
        bb = board.GetBoardEdgesBoundingBox()
        cx = mm(bb.GetCenter().x)
        # distance to the *edge* of the reserved power corridor
        dx = [max(0.0, abs(x - cx) - CORRIDOR_MM / 2) for x, _y, _r in pts]
        flow_pts = sorted(pts, key=lambda t: t[1])
        flow = sum(((flow_pts[i][0] - flow_pts[i - 1][0]) ** 2 +
                    (flow_pts[i][1] - flow_pts[i - 1][1]) ** 2) ** 0.5
                   for i in range(1, len(flow_pts)))
        span = flow_pts[-1][1] - flow_pts[0][1]
        print(f"  power parts:       {len(pts)}  (centreline x={cx:.0f} mm)")
        print(f"  |dx| to centre:    mean {sum(dx)/len(dx):5.1f} mm, "
              f"max {max(dx):5.1f} mm   (lower = closer to the power path)")
        print(f"  flow length:       {flow:6.1f} mm over span {span:.0f} mm "
              f"-> straightness {flow/span:.2f}  (1.0 = dead straight)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
