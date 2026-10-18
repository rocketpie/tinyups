#!/usr/bin/env python3
"""Route a PCB with freerouting (KiCad has no built-in autorouter).

Flow: export Specctra DSN -> relax only the **trace width** to the JLCPCB
standard 5 mil (0.127 mm) floor -> route with freerouting -> import the session
into the board -> raise any necked trace back to the floor -> refill zones ->
save.

Why relax the width and nothing else: 0.127 mm (= 5 mil, the JLCPCB
**standard** tier minimum) is the trace floor, so letting the router use it buys
completion without going below what the fab can make.  The **clearance** is
*not* relaxed: the board's own `Default` netclass asks 0.2 mm, which is the
design's rule and stricter than the fab floor, so a route handed 0.127 mm would
come back violating the board (503 clearance DRVs that mean "route tighter than
the design allows", not "the fab cannot make this").  The advanced 3.5 mil tier
is only for a documented geometry that cannot meet 5 mil (NFR-9).

The route is written to a **separate** board, never back into the source: the
source may be the tracked board and a route is an experiment (ADR-0009 §6).

Requires Java + the freerouting jar (``FREEROUTING_JAR``, defaulting to
``/opt/freerouting/freerouting.jar``).  Env:

    ROUTE_RULE_UM          trace width handed to the router (default 127 = 5 mil;
                           empty = leave the board's own width alone)
    ROUTE_MIN_WIDTH_UM     post-route floor; 0 disables the raise (default 127)
    ROUTE_PLANE_AS_OBSTACLE also treat the plane as a router obstacle
                           (default off: it blocks every via)
    ROUTE_PLANE_LAYER_TYPE  declare the plane layer (type power) instead —
                           kills vias, see docs/history/0013
    FREEROUTING_EXTRA_ARGS  extra freerouting --flags

    route.py [board.kicad_pcb] [out.kicad_pcb]
    ROUTE_BOARD=build/layout/try5.kicad_pcb make route
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PCB = os.path.join(HERE, "tinyups.kicad_pcb")
DEFAULT_JAR = "/opt/freerouting/freerouting.jar"
# DSN units are um: 127 = 0.127 mm = 5 mil = the JLCPCB standard floor.
RULE_NM = os.environ.get("ROUTE_RULE_UM", "127")    # width handed to the router
FLOOR_NM = os.environ.get("ROUTE_MIN_WIDTH_UM", "127")  # post-route floor
PLANE_FRACTION = float(os.environ.get("ROUTE_PLANE_FRACTION", "0.3"))
# off by default: the rule area already exports as (wire_keepout ...),
# and this flag also blocks the through-via padstack (history 0013)
PLANE_AS_OBSTACLE = os.environ.get("ROUTE_PLANE_AS_OBSTACLE", "0") != "0"
PLANE_LAYER_TYPE = os.environ.get("ROUTE_PLANE_LAYER_TYPE", "0") != "0"
PLANE_KEEPOUT = os.environ.get("ROUTE_PLANE_KEEPOUT", "0") != "0"


def plane_layers(board) -> list:
    """Layers carrying a board-sized zone: those are planes, not signal layers.

    Same ≥30 % heuristic freerouting itself uses to notice a plane; here it is
    used to *declare* the layer so the router stops treating it as routing
    space.  ROUTE_PLANE_FRACTION=0 disables the declaration.
    """
    edges = board.GetBoardEdgesBoundingBox()
    board_area = pcbnew.ToMM(edges.GetWidth()) * pcbnew.ToMM(edges.GetHeight())
    if board_area <= 0 or PLANE_FRACTION <= 0:
        return []
    out = []
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        sh = z.Outline()
        area = abs(sh.Area()) / 1e12 if hasattr(sh, "Area") else 0.0
        if area >= PLANE_FRACTION * board_area:
            name = board.GetLayerName(z.GetLayer())
            if name not in out:
                out.append(name)
    return out


def main() -> int:
    board_in = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PCB
    board_out = sys.argv[2] if len(sys.argv) > 2 else board_in
    if not os.path.exists(board_in):
        print(f"error: no such board: {board_in}", file=sys.stderr)
        return 1

    jar = os.environ.get("FREEROUTING_JAR", DEFAULT_JAR)
    if not os.path.exists(jar):
        print("error: set FREEROUTING_JAR to the freerouting jar", file=sys.stderr)
        return 1
    if os.path.abspath(board_in) == os.path.abspath(board_out):
        print(f"warning: routing {board_in} in place", file=sys.stderr)

    d = tempfile.mkdtemp(prefix="tinyups-route-")
    dsn, ses = os.path.join(d, "t.dsn"), os.path.join(d, "t.ses")

    board = pcbnew.LoadBoard(board_in)
    pcbnew.ExportSpecctraDSN(board, dsn)

    # Hand the router the trace floor.  Only the *width*: the clearance stays at
    # the board's own rule (0.2 mm netclass), otherwise the route comes back
    # violating the board it was made for (see docs/history/0009).
    text = open(dsn).read()
    if RULE_NM:
        text = re.sub(r"\(width \d+\)", f"(width {RULE_NM})", text)

    # Keep signals off the plane layers.  Two ways, and the obvious one is a
    # trap: rewriting the *layer type* to (type power) does stop signal tracks,
    # but freerouting then drops the through-via padstack entirely — 0 vias and
    # 97 unconnected (docs/history/0013).  The supported way is the router's own
    # plane handling: KiCad already exports the zone as `(plane /GND ...)`, and
    # plane_as_obstacle makes the router route *around* it while still using
    # vias.  ROUTE_PLANE_LAYER_TYPE=1 brings the layer rewrite back for
    # experiments; ROUTE_PLANE_AS_OBSTACLE=0 turns the setting off.
    if PLANE_LAYER_TYPE:
        for name in plane_layers(board):
            idx = text.find(f"(layer {name}")
            if idx < 0:
                print(f"warning: layer {name} not found in the DSN",
                      file=sys.stderr)
                continue
            end = text.find("(type signal)", idx)
            if end < 0:
                continue
            text = text[:end] + "(type power)" + text[end + len("(type signal)"):]
            print(f"plane layer {name}: signalled as (type power) in the DSN",
                  flush=True)

    # Fallback for a board with no rule area on the plane: inject a *wire*
    # keepout.  Normally this is not needed — KiCad already exports the rule area
    # from gen_pcb.py as `(wire_keepout "" (polygon In1.Cu …))`, which the router
    # understands.  Freerouting also has `via_keepout` and `place_keepout` scopes,
    # which is why a wire keepout should leave vias alone where the layer type and
    # plane_as_obstacle both do not (docs/history/0013).
    if PLANE_KEEPOUT:
        for name in plane_layers(board):
            m = re.search(rf"^\s*\(plane \S+ \(polygon {re.escape(name)} .*\)\)$",
                          text, re.M)
            if not m:
                print(f"warning: no (plane …) entry on {name} to anchor the "
                      f"keepout", file=sys.stderr)
                continue
            poly = re.search(rf"\(polygon {re.escape(name)}\s+([^)]*)\)",
                             m.group(0))
            text = text.replace(
                m.group(0),
                f"{m.group(0)}\n    (keepout\n"
                f"      (polygon {name} {poly.group(1)})\n    )")
            print(f"plane layer {name}: wire keepout injected into the DSN",
                  flush=True)

    open(dsn, "w").write(text)

    # NOTE: freerouting does *not* read a freerouting.json from the working
    # directory (it was never applied — the "disable the GUI" warning appeared on
    # every run).  Its settings come from ~/.config/freerouting/freerouting.json,
    # FREEROUTING__ROUTER__* env vars, or --router.* flags (docs/history/0009).
    passes = os.environ.get("FREEROUTING_PASSES", "15")
    args = ["java", "-jar", jar, "-de", dsn, "-do", ses,
            f"--router.autorouter.max_passes={passes}", "--gui.enabled=false"]
    if PLANE_AS_OBSTACLE:
        args.append("--router.plane_as_obstacle=true")
    args += shlex.split(os.environ.get("FREEROUTING_EXTRA_ARGS", ""))
    subprocess.run(args, check=True, cwd=d)

    board = pcbnew.LoadBoard(board_in)
    pcbnew.ImportSpecctraSES(board, ses)

    # freerouting can come back below the width it was handed: it necks a trace
    # to a fraction of the class width (0.0952 / 0.0762 / 0.0634 mm for a 0.127
    # board) rather than leaving the connection unrouted.  Raise them back to the
    # floor — a neck is a local fit problem, and the DRC right after this says
    # whether it really could not be wider.  ROUTE_MIN_WIDTH_UM=0 disables it.
    floor = int(os.environ.get("ROUTE_MIN_WIDTH_UM", FLOOR_NM))
    raised = 0
    if floor > 0:
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                continue
            if t.GetWidth() < pcbnew.FromMM(floor / 1000.0):
                t.SetWidth(pcbnew.FromMM(floor / 1000.0))
                raised += 1
        if raised:
            print(f"raised {raised} necked tracks to the {floor / 1000.0:g} mm floor",
                  flush=True)

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(board_out, board)
    print(f"routed {board_in} -> {board_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
