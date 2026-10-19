#!/usr/bin/env python3
"""Sync board footprints to the schematic's footprint assignment.

KiCad's GUI has "Update PCB from Schematic"; headless there is no CLI for it.
This performs the footprint half: for every board footprint whose library
footprint differs from the schematic netlist, load the library footprint, keep
the pose / schematic path / reference / value, remap the pads to the old nets by
pad number, and replace it.  The BOM/DNP flags are taken from the schematic.

Usage:  sync_footprints.py [board.kicad_pcb] [schematic.kicad_sch]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOARD = os.path.join(ROOT, "hardware", "tinyups.kicad_pcb")
SCH = os.path.join(ROOT, "hardware", "tinyups.kicad_sch")
FP_ROOT = os.environ.get("KICAD9_FOOTPRINT_DIR", "/usr/share/kicad/footprints")

# Physical pad number -> symbol pin function.  A footprint swap is only safe
# when the land uses the same pin numbers as the symbol; the TO-252 board was
# built with GSD symbols on a GDS land, which reverses drain and source
# (history 0020).  Refuse that swap instead of shorting the gate to the source.
PAD_FUNCTION = {
    "Package_TO_SOT_SMD:TO-252-2": {"1": "G", "2": "D", "3": "S"},
    "Package_TO_SOT_SMD:TO-252-3_TabPin2": {"1": "G", "2": "D", "3": "S"},
    "Package_SON:VSONP-8-1EP_5x6_P1.27mm": {"1": "S", "2": "G", "3": "D"},
}


def netlist(sch: str) -> tuple[
        dict[str, str], dict[str, str],
        dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """(ref -> footprint, ref -> value, ref -> {pin: fn}, ref -> {pin: net})."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "t.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist",
                        "--format", "kicadsexpr", "-o", out, sch],
                       check=True, capture_output=True, text=True)
        txt = open(out).read()
    feet: dict[str, str] = {}
    values: dict[str, str] = {}
    for m in re.finditer(
            r'\(comp \(ref "([^"]+)"\)\s*\(value "([^"]*)"\)\s*'
            r'\(footprint "([^"]*)"\)', txt):
        values[m.group(1)] = m.group(2)
        feet[m.group(1)] = m.group(3)
    pins: dict[str, dict[str, str]] = {}
    for m in re.finditer(
            r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)'
            r'(?: \(pinfunction "([^"]*)"\))?', txt):
        ref, pin, fn = m.groups()
        pins.setdefault(ref, {})[pin] = fn or ""
    pin_nets: dict[str, dict[str, str]] = {}
    for block in re.split(r"(?=\(net \(code)", txt):
        nm = re.search(r'\(net \(code "\d+"\) \(name "([^"]+)"\)', block)
        if not nm:
            continue
        for m in re.finditer(
                r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', block):
            pin_nets.setdefault(m.group(1), {})[m.group(2)] = nm.group(1)
    return feet, values, pins, pin_nets


def schematic_flags(sch: str) -> dict[str, tuple[bool, bool]]:
    """ref -> (in_bom, dnp) from the placed symbol blocks."""
    s = open(sch).read()
    out: dict[str, tuple[bool, bool]] = {}
    for m in re.finditer(r'\(property "Reference" "([^"#]+)"', s):
        ref = m.group(1)
        start = s.rfind("(symbol (lib_id", 0, m.start())
        block = s[start:m.start()]
        in_bom = re.search(r"\(in_bom (yes|no)\)", block)
        dnp = re.search(r"\(dnp (yes|no)\)", block)
        out[ref] = (not in_bom or in_bom.group(1) == "yes",
                    bool(dnp and dnp.group(1) == "yes"))
    return out


def main() -> int:
    board_path = sys.argv[1] if len(sys.argv) > 1 else BOARD
    sch_path = sys.argv[2] if len(sys.argv) > 2 else SCH

    want, values, pins, pin_nets = netlist(sch_path)
    flags = schematic_flags(sch_path)
    board = pcbnew.LoadBoard(board_path)

    replaced = aligned = 0
    for fp in list(board.GetFootprints()):
        ref = fp.GetReference()
        fpid = fp.GetFPIDAsString()
        target = want.get(ref)
        if target and target != fpid:
            lib, name = target.split(":", 1)
            new = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib + ".pretty"),
                                       name)
            if not new:
                print(f"warning: {ref}: {target} not found in {FP_ROOT}")
                continue
            land = PAD_FUNCTION.get(target)
            sym = pins.get(ref, {})
            bad = [(p, land[p], sym[p]) for p in (land or {})
                   if sym.get(p) and land[p] != sym[p]]
            if bad:
                print(f"  REFUSED {ref}: {target} land {bad} != symbol {sym}")
                continue

            # FootprintLoad only knows the footprint name; the board stores the
            # full library id, and schematic parity compares that string.
            new.SetFPIDAsString(target)
            new.SetPosition(fp.GetPosition())
            new.SetOrientation(fp.GetOrientation())
            new.SetLayer(fp.GetLayer())
            new.SetReference(ref)
            new.SetValue(values.get(ref) or fp.GetValue())
            new.SetPath(fp.GetPath())
            new.SetSheetname(fp.GetSheetname())
            new.SetSheetfile(fp.GetSheetfile())
            new.SetLocked(fp.IsLocked())

            in_bom, dnp = flags.get(ref, (True, False))
            # The library owns the SMD/THT flag (the ATO fuse is a THT part);
            # only the BOM / pos / DNP flags come from the schematic.
            attrs = new.GetAttributes() & ~(pcbnew.FP_EXCLUDE_FROM_BOM |
                                            pcbnew.FP_EXCLUDE_FROM_POS_FILES |
                                            pcbnew.FP_DNP)
            attrs |= 0 if in_bom else pcbnew.FP_EXCLUDE_FROM_BOM
            attrs |= pcbnew.FP_DNP if dnp else 0
            new.SetAttributes(attrs)

            # Nets come from the netlist pin numbers, not from the old pads:
            # when the package changes, pad 1 of the new land is not
            # necessarily pad 1 of the old one.
            net_by_pin = pin_nets.get(ref, {})
            missing = [p.GetNumber() for p in new.Pads()
                       if p.GetNumber() and p.GetNumber() not in net_by_pin]
            board.Delete(fp)
            board.Add(new)
            # The net list belongs to the board, so assign after Add().
            for p in new.Pads():
                name = net_by_pin.get(p.GetNumber()) or ""
                net = board.FindNet(name) if name else None
                if net:
                    p.SetNet(net)
            if missing:
                print(f"  warning: {ref}: no netlist net for pad(s) {missing}")

            print(f"  {ref:5} {fpid} -> {target}")
            replaced += 1
        elif ref in flags:
            in_bom, dnp = flags[ref]
            attrs = fp.GetAttributes()
            fixed = attrs & ~(pcbnew.FP_EXCLUDE_FROM_BOM |
                              pcbnew.FP_EXCLUDE_FROM_POS_FILES |
                              pcbnew.FP_DNP)
            fixed |= 0 if in_bom else pcbnew.FP_EXCLUDE_FROM_BOM
            fixed |= pcbnew.FP_DNP if dnp else 0
            if fixed != attrs:
                fp.SetAttributes(fixed)
                print(f"  {ref:5} attributes -> {fixed}")
                aligned += 1

    pcbnew.SaveBoard(board_path, board)
    print(f"replaced {replaced} footprint(s), aligned {aligned} attribute(s)"
          f" -> {board_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
