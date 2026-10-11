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

MARGIN = 5.0          # mm board margin around placement
GAP = 2.5             # mm gap between footprints
MAX_W, MAX_H = 135.0, 138.0   # ATX-bay cap (150 x 140)


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
        loaded.append([ref, fp, bb.GetWidth(), bb.GetHeight()])

    # shelf-pack: tall first, wrap at MAX_W
    loaded.sort(key=lambda t: -t[3])
    x = y = 0.0
    row_h = 0.0
    used_w = used_h = 0.0
    for ref, fp, w, h in loaded:
        wmm, hmm = pcbnew.ToMM(w), pcbnew.ToMM(h)
        if x > 0 and x + wmm > MAX_W:
            y += row_h + GAP
            x = 0.0
            row_h = 0.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + wmm / 2),
                                       pcbnew.FromMM(y + hmm / 2)))
        x += wmm + GAP
        row_h = max(row_h, hmm)
        used_w = max(used_w, x)
        used_h = max(used_h, y + row_h)
        board.Add(fp)

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

    # outline
    bw, bh = used_w + 2 * MARGIN, used_h + 2 * MARGIN
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(0), pcbnew.FromMM(0)))
    r.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(bw), pcbnew.FromMM(bh)))
    r.SetLayer(pcbnew.Edge_Cuts)
    r.SetWidth(pcbnew.FromMM(0.1))
    board.Add(r)

    pcbnew.SaveBoard(OUT, board)
    print(f"wrote {OUT}")
    print(f"  {len(loaded)} footprints, {len(netcache)} nets, board {bw:.1f} x {bh:.1f} mm")
    if bw > MAX_W + 1 or bh > MAX_H + 1:
        print(f"  WARNING: board exceeds ATX cap {MAX_W}x{MAX_H} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
