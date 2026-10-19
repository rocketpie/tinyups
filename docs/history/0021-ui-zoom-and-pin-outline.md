# 0021 — placement UI: zoom anchor, pin outline, power-pour overlay

**What:** three view changes in `ui/placement/`: wheel zoom kept the board's
top-left corner fixed instead of the point under the cursor and stopped at 16×;
pinned parts always carried a yellow outline; and the filled power pours of the
applied board were invisible.

**Why:** the wheel handler measured the cursor in board coordinates, changed
`S.view.k`, measured again — but the new transform was only written to the SVG
by the final `applyView()`. The second `toMM()` therefore still read the old
scale, `after === before`, and the x/y correction was always zero, leaving the
viewport origin as the anchor. The pin outline was bound to the `.pinned` class
with no way to hide it. The pours existed only in the applied `.kicad_pcb`;
nothing exported them in board coordinates the UI could draw.

**Status:** fixed/added. The scale is applied before re-measuring, so the point
under the cursor stays put (zoom is centred on the cursor; at the view centre it
stays centred); the wheel cap is now 80× (was 16×). The outline is keyed to a
separate `pin-marked` class and the **mark pinned parts** checkbox hides it;
pinned state, saving and solver behaviour are unchanged.

**Power-pour overlay:** `ui/placement/pours.py` reads the zones of
`build/layout/board.kicad_pcb`, skips GND and unfilled zones, and writes the
filled polygons (outer rings + holes) to `build/layout/pours.json`. `apply.py`
regenerates it right after `ZONE_FILLER(board).Fill(...)`; the server serves it
at `/api/pours`, and the UI draws each net's polygons even-odd, tinted by net
current at 16% fill, under the graph. The **show power pours** checkbox toggles
it and is remembered like the other view switches. The overlay is copper, not
placement: it does not follow a drag; the next **Apply** refreshes it.
