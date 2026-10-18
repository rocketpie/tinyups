#!/usr/bin/env python3
"""Turn a routed board + its DRC report into *placement* feedback.

The router and the DRC know things the placement graph cannot: which
connections it could not finish, where two pads are closer than the design
clearance, which power rail has no room for its pour, and how wide the traces
really are.  This script writes those facts as one JSON file so the placement
UI can show them on the board instead of asking a human to read a report.

It is deliberately a reader, not a gate: `make route` and `make drc` still fail
the build.  This file only answers "where should I move parts?".

Data written (`build/layout/route-feedback.json`):

* `board` / `drc` — the inputs, so a stale panel is obvious
* `summary` — tracks, vias, routed length, min trace, violation counts
* `unrouted` — one entry per missing connection, with the two item positions,
  net, part/pad when the report names one
* `clearance` — one entry per clearance violation, with required/actual and
  both items
* `parts` / `nets` — the same facts counted per reference / net
* `power_channels` — `power_channel.py`'s measured pour channel per rail

Usage:
    route_feedback.py <routed.kicad_pcb> [drc.rpt] [-o build/layout/route-feedback.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from power_channel import widths as channel_widths          # noqa: E402
from power_report import DESIGN_CURRENT                     # noqa: E402

GRAPH = os.path.join(ROOT, "build", "layout", "graph.json")
DEFAULT_OUT = os.path.join(ROOT, "build", "layout", "route-feedback.json")

# A block starts with `[type]: description`; item lines start with `@(x, y)`.
BLOCK_RE = re.compile(r"^\[([a-z_]+)\]:\s*(.*)$", re.M)
ITEM_RE = re.compile(r"^\s*@\((-?[\d.]+) mm, (-?[\d.]+) mm\):\s*(.*)$", re.M)
NET_RE = re.compile(r"\[/([^\]]+)\]")
REF_RE = re.compile(r"\bof\s+([A-Za-z0-9_.-]+)\b")
PAD_RE = re.compile(r"(?:PTH\s+)?[Pp]ad\s+(\d+)")
LAYER_RE = re.compile(r"\bon\s+([A-Za-z0-9.]+)")
ACTUAL_RE = re.compile(r"actual\s+([\d.]+)\s*mm")
REQUIRED_RE = re.compile(r"clearance\s+([\d.]+)\s*mm")


def _item(desc: str, x: float, y: float) -> dict:
    """One DRC item line -> a placement-addressable record."""
    if "Track" in desc:
        kind = "track"
    elif "Via" in desc:
        kind = "via"
    elif "Zone" in desc:
        kind = "zone"
    elif re.search(r"\b[Pp]ad\b", desc):
        kind = "pad"
    elif "Silkscreen" in desc or "silk" in desc:
        kind = "silk"
    else:
        kind = "other"
    net = NET_RE.search(desc)
    ref = REF_RE.search(desc)
    pad = PAD_RE.search(desc)
    layer = LAYER_RE.search(desc)
    return {
        "x": round(x, 3), "y": round(y, 3),
        "kind": kind,
        "net": net.group(1) if net else None,
        "ref": ref.group(1) if ref else None,
        "pad": pad.group(1) if pad else None,
        "layer": layer.group(1) if layer else None,
        "desc": desc,
    }


def parse_drc(path: str) -> dict:
    """Parse kicad-cli's text DRC report into violations + counts."""
    if not path or not os.path.exists(path):
        return {"counts": {}, "violations": []}
    text = open(path, encoding="utf-8", errors="replace").read()
    starts = [m.start() for m in BLOCK_RE.finditer(text)]
    violations = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        head = BLOCK_RE.match(block)
        if not head:
            continue
        vtype, message = head.group(1), head.group(2).strip()
        items = [dict(zip(("x", "y", "desc"), m.groups()), kind=None)
                 for m in ITEM_RE.finditer(block)]
        items = [_item(it["desc"], float(it["x"]), float(it["y"]))
                 for it in items]
        actual = ACTUAL_RE.search(block)
        required = REQUIRED_RE.search(block)
        violations.append({
            "type": vtype,
            "message": message,
            "severity": "error" if re.search(r";\s*error", block) else
                        "warning" if re.search(r";\s*warning", block) else "?",
            "required_mm": float(required.group(1)) if required else None,
            "actual_mm": float(actual.group(1)) if actual else None,
            "items": items,
        })
    counts = dict(Counter(v["type"] for v in violations))
    return {"counts": counts, "violations": violations}


def board_metrics(board) -> dict:
    """Track/via counts and per-net minimum width from the routed board."""
    per_net: dict[str, dict] = {}
    widths, lengths = [], 0.0
    per_layer: Counter[str] = Counter()
    vias = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias += 1
            net = t.GetNetname().lstrip("/")
            per_net.setdefault(net, {"tracks": 0, "vias": 0,
                                     "min_mm": None, "length_mm": 0.0})["vias"] += 1
            continue
        w = pcbnew.ToMM(t.GetWidth())
        ln = pcbnew.ToMM(t.GetLength())
        widths.append(w)
        lengths += ln
        layer = board.GetLayerName(t.GetLayer())
        per_layer[layer] += 1
        net = t.GetNetname().lstrip("/")
        rec = per_net.setdefault(net, {"tracks": 0, "vias": 0,
                                       "min_mm": None, "length_mm": 0.0})
        rec["tracks"] += 1
        rec["length_mm"] += ln
        rec["min_mm"] = w if rec["min_mm"] is None else min(rec["min_mm"], w)

    graph = {}
    if os.path.exists(GRAPH):
        try:
            graph = json.load(open(GRAPH))
        except (OSError, ValueError):
            graph = {}
    for net, rec in per_net.items():
        g = (graph.get("nets") or {}).get(net) or {}
        rec["required_mm"] = g.get("width")
        rec["current_a"] = g.get("current", DESIGN_CURRENT.get(net))
        rec["min_mm"] = round(rec["min_mm"], 3) if rec["min_mm"] is not None else None
        rec["length_mm"] = round(rec["length_mm"], 2)
    return {
        "tracks": len(widths),
        "vias": vias,
        "routed_length_mm": round(lengths, 2),
        "min_track_mm": round(min(widths), 3) if widths else None,
        "median_track_mm": round(sorted(widths)[len(widths) // 2], 3) if widths else None,
        "tracks_per_layer": dict(per_layer.most_common()),
        "nets": per_net,
    }


def channel_feedback(board) -> list[dict]:
    """The measured pour channel per high-current rail, plus its pinch point."""
    try:
        measured = channel_widths(board)
    except Exception as e:                       # scipy missing / odd geometry
        print(f"warning: power channel measurement skipped: {e}", file=sys.stderr)
        return []
    out = []
    for net, (need, have, where) in measured.items():
        pinch = None
        if where:
            m = re.search(r"\((-?[\d.]+),(-?[\d.]+)\)", where)
            if m:
                pinch = {"x": float(m.group(1)), "y": float(m.group(2))}
        out.append({
            "net": net,
            "current_a": DESIGN_CURRENT.get(net),
            "required_mm": round(need, 2),
            "channel_mm": round(have, 2),
            "ok": have >= need,
            "pinch": pinch,
        })
    out.sort(key=lambda d: (d["ok"], d["channel_mm"] / max(d["required_mm"], 1e-3)))
    return out


def summarize(board_path: str, drc_path: str | None) -> dict:
    board = pcbnew.LoadBoard(board_path)
    bm = board_metrics(board)
    drc = parse_drc(drc_path) if drc_path else {"counts": {}, "violations": []}

    unrouted, clearance = [], []
    parts: dict[str, dict] = {}
    nets: dict[str, dict] = {}

    def part(ref):
        return parts.setdefault(ref, {"unrouted": 0, "clearance": 0,
                                      "min_clearance_mm": None, "nets": set()})

    for v in drc["violations"]:
        items = v["items"]
        for it in items:
            if it.get("ref"):
                part(it["ref"])["nets"].add(it.get("net") or "")
            if it.get("net"):
                n = nets.setdefault(it["net"], {"unrouted": 0, "clearance": 0,
                                                "min_clearance_mm": None})
        if v["type"] == "unconnected_items":
            unrouted.append({"net": next((i["net"] for i in items if i["net"]), None),
                             "a": items[0] if items else None,
                             "b": items[1] if len(items) > 1 else None})
            for it in items:
                if it.get("ref"):
                    part(it["ref"])["unrouted"] += 1
                if it.get("net"):
                    nets[it["net"]]["unrouted"] += 1
        elif v["type"] == "clearance":
            clearance.append({"required_mm": v["required_mm"],
                              "actual_mm": v["actual_mm"],
                              "a": items[0] if items else None,
                              "b": items[1] if len(items) > 1 else None})
            for it in items:
                if it.get("ref"):
                    p = part(it["ref"])
                    p["clearance"] += 1
                    if v["actual_mm"] is not None:
                        p["min_clearance_mm"] = v["actual_mm"] if p["min_clearance_mm"] is None \
                            else min(p["min_clearance_mm"], v["actual_mm"])
                if it.get("net"):
                    n = nets[it["net"]]
                    n["clearance"] += 1
                    if v["actual_mm"] is not None:
                        n["min_clearance_mm"] = v["actual_mm"] if n["min_clearance_mm"] is None \
                            else min(n["min_clearance_mm"], v["actual_mm"])

    for rec in parts.values():
        rec["nets"] = sorted(x for x in rec["nets"] if x)
    channels = channel_feedback(board)
    summary = {
        "board": os.path.relpath(board_path, ROOT),
        "drc": os.path.relpath(drc_path, ROOT) if drc_path else None,
        "summary": {
            **bm,
            "drc_counts": drc["counts"],
            "unrouted": len(unrouted),
            "clearance": len(clearance),
            "power_channels_short": sum(1 for c in channels if not c["ok"]),
        },
        "unrouted": unrouted,
        "clearance": clearance,
        "parts": dict(sorted(parts.items())),
        "nets": dict(sorted(nets.items())),
        "power_channels": channels,
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", help="routed .kicad_pcb")
    ap.add_argument("drc", nargs="?", help="kicad-cli DRC report")
    ap.add_argument("-o", "--out", default=DEFAULT_OUT, help="output JSON")
    args = ap.parse_args()

    data = summarize(args.board, args.drc)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")

    s = data["summary"]
    print(f"board: {data['board']}")
    print(f"  tracks {s['tracks']}  vias {s['vias']}  "
          f"min trace {s['min_track_mm']} mm  "
          f"routed {s['routed_length_mm']} mm")
    print(f"  unrouted {s['unrouted']}  clearance {s['clearance']}  "
          f"power channels short {s['power_channels_short']}")
    for c in data["power_channels"]:
        if not c["ok"]:
            print(f"    {c['net']:9} channel {c['channel_mm']:5.1f} / "
                  f"{c['required_mm']:5.1f} mm  SHORT")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
