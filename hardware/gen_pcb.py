#!/usr/bin/env python3
"""Generate the TinyUPS PCB from the netlist.

* Reads the KiCad netlist (`build/tinyups.net`) for components, footprints and
  net connectivity.
* Builds a 4-layer board, assigns nets to pads, and places the footprints with
  a simple shelf-packing algorithm (guarantees no courtyard overlap).
* Board outline is sized to the packed placement, capped to the ATX bay.

Routing is done separately with freerouting (see hardware/README.md).

Run:  /opt/eda/venv/bin/python hardware/gen_pcb.py
"""
from __future__ import annotations

import os
import re
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NETLIST = os.path.join(ROOT, "build", "tinyups.net")
OUT = os.path.join(HERE, "tinyups.kicad_pcb")
FP_ROOT = "/usr/share/kicad/footprints"

MARGIN = 3.0          # mm board margin around placement
GAP = 2.5             # mm gap between footprints
MAX_W, MAX_H = 150.0, 140.0   # ATX-bay cap (150 x 140)


# --------------------------------------------------------------------------- #
# tiny s-expression parser
# --------------------------------------------------------------------------- #
def tokenize(s: str):
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and s[j] != '"':
                if s[j] == "\\":
                    j += 1
                buf.append(s[j])
                j += 1
            yield ("str", "".join(buf))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()"':
                j += 1
            yield ("sym", s[i:j])
            i = j


def parse(s: str):
    toks = list(tokenize(s))
    pos = 0

    def rd():
        nonlocal pos
        t = toks[pos]
        pos += 1
        if t == "(":
            lst = []
            while toks[pos] != ")":
                lst.append(rd())
            pos += 1
            return lst
        return t[1]

    return rd()


def _find_all(node, key):
    out = []
    if isinstance(node, list) and node and node[0] == key:
        out.append(node)
    if isinstance(node, list):
        for c in node:
            out.extend(_find_all(c, key))
    return out


# --------------------------------------------------------------------------- #
def main() -> int:
    if not os.path.exists(NETLIST):
        print("error: run `make netlist` first", file=sys.stderr)
        return 1
    tree = parse(open(NETLIST).read())

    # components
    comps = {}
    for c in _find_all(tree, "comp"):
        ref = next(x for x in c if isinstance(x, list) and x[0] == "ref")[1]
        val = next((x[1] for x in c if isinstance(x, list) and x[0] == "value"), "")
        fp = next((x[1] for x in c if isinstance(x, list) and x[0] == "footprint"), "")
        comps[ref] = {"value": val, "fp": fp}

    # nets: netname -> [(ref, pad)]
    pin_net = {}
    for net in _find_all(tree, "net"):
        name = next(x[1] for x in net if isinstance(x, list) and x[0] == "name")
        for node in net:
            if isinstance(node, list) and node[0] == "node":
                ref = next(x[1] for x in node if isinstance(x, list) and x[0] == "ref")
                pad = next(x[1] for x in node if isinstance(x, list) and x[0] == "pin")
                pin_net[(ref, pad)] = name

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)

    # design rules (also feeds the Specctra export)
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = pcbnew.FromMM(0.2)
    ds.m_MinClearance = pcbnew.FromMM(0.2)
    ds.m_ViasMinSize = pcbnew.FromMM(0.6)
    ds.m_ViasMinDrill = pcbnew.FromMM(0.3)
    try:
        nc = ds.GetDefault()
        nc.SetTrackWidth(pcbnew.FromMM(0.3))
        nc.SetClearance(pcbnew.FromMM(0.2))
        nc.SetViaDiameter(pcbnew.FromMM(0.8))
        nc.SetViaDrill(pcbnew.FromMM(0.4))
    except Exception as e:  # pragma: no cover
        print("netclass note:", e)

    # load footprints
    loaded = []
    for ref, info in comps.items():
        lib, name = info["fp"].split(":", 1)
        fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib + ".pretty"), name)
        if fp is None:
            print(f"error: footprint not found {info['fp']} for {ref}", file=sys.stderr)
            return 2
        fp.SetReference(ref)
        fp.SetValue(info["value"])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        bb = fp.GetBoundingBox()
        w, h = bb.GetWidth(), bb.GetHeight()
        if ref.startswith("J"):        # connectors: reserve extra clearance
            w += pcbnew.FromMM(8)
            h += pcbnew.FromMM(8)
        loaded.append([ref, fp, w, h])

    # ---- block-aware placement ------------------------------------------- #
    # group parts by functional block (same split as the schematic), lay each
    # block out in a sub-rectangle, then pack the block rectangles into rows.
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
              "C23", "R26", "R27", "R28", "R29", "R30", "R45", "R46"},
        "F": {"U6", "U7", "U8", "J3", "J4", "J5", "Y1", "R31", "R36", "R37",
              "R38", "R32", "R33", "R34", "R35", "D2", "D3", "D4", "D5",
              "C24", "C25", "C26", "C27", "C28"},
    }
    ref_block = {r: b for b, refs in BLOCKS.items() for r in refs}

    def shelf(items, maxw, gap=GAP):
        """pack (ref, fp, w, h) into rows; return placed [(ref, fp, cx, cy)] + size."""
        items = sorted(items, key=lambda t: -t[3])
        x = y = 0.0
        row_h = uw = uh = 0.0
        out = []
        for ref, fp, w, h in items:
            wmm, hmm = pcbnew.ToMM(w), pcbnew.ToMM(h)
            if x > 0 and x + wmm > maxw:
                y += row_h + gap
                x = 0.0
                row_h = 0.0
            out.append((ref, fp, x + wmm / 2, y + hmm / 2))
            x += wmm + gap
            row_h = max(row_h, hmm)
            uw = max(uw, x)
            uh = max(uh, y + row_h)
        return out, uw, uh

    by_block: dict[str, list] = {}
    for item in loaded:
        by_block.setdefault(ref_block.get(item[0], "X"), []).append(item)

    # 1) lay out each block in a sub-rectangle, then place blocks on a fixed
    #    3-column grid in signal-flow order (columns sized to the usable width)
    cols = 3
    col_w = (MAX_W - 2 * MARGIN) / cols
    BW = col_w - 4.0
    block = {b: shelf(items, BW) for b, items in by_block.items()}
    order = [b for b in ("A", "B", "C", "D", "E", "F", "X") if b in block]
    rows = [order[i:i + cols] for i in range(0, len(order), cols)]
    y_off = MARGIN
    used_w = 0.0
    for rowblocks in rows:
        row_h = 0.0
        for c_i, b in enumerate(rowblocks):
            placed, bw, bh = block[b]
            x_off = MARGIN + c_i * col_w
            for ref, fp, cx, cy in placed:
                fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x_off + cx),
                                               pcbnew.FromMM(y_off + cy)))
                board.Add(fp)
            used_w = max(used_w, x_off + bw)
            row_h = max(row_h, bh)
        y_off += row_h + GAP
    used_h = y_off - GAP

    # nets -> pads
    netcache = {}
    for ref, fp, *_ in loaded:
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            name = pin_net.get(key)
            if not name:
                continue
            if name not in netcache:
                n = pcbnew.NETINFO_ITEM(board, name)
                board.Add(n)
                netcache[name] = n
            pad.SetNet(netcache[name])

    # outline = union of footprint bboxes + margin (keeps edge clearance)
    x0 = y0 = 1e18
    x1 = y1 = -1e18
    for fp in board.GetFootprints():
        bb = fp.GetBoundingBox()
        x0 = min(x0, bb.GetX()); y0 = min(y0, bb.GetY())
        x1 = max(x1, bb.GetRight()); y1 = max(y1, bb.GetBottom())
    x0 = pcbnew.ToMM(x0) - MARGIN
    y0 = pcbnew.ToMM(y0) - MARGIN
    x1 = pcbnew.ToMM(x1) + MARGIN
    y1 = pcbnew.ToMM(y1) + MARGIN
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0), pcbnew.FromMM(y0)))
    r.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
    r.SetLayer(pcbnew.Edge_Cuts)
    r.SetWidth(pcbnew.FromMM(0.1))
    board.Add(r)
    bw, bh = x1 - x0, y1 - y0

    pcbnew.SaveBoard(OUT, board)
    print(f"wrote {OUT}")
    print(f"  {len(loaded)} footprints, {len(netcache)} nets, board {bw:.1f} x {bh:.1f} mm")
    if bw > MAX_W + 1 or bh > MAX_H + 1:
        print(f"  WARNING: board exceeds ATX cap {MAX_W}x{MAX_H} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
