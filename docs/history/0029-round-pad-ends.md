# 0029 – power pours are full Voronoi cells

**What:** the trunk/branch version clipped a round end only when it cleared the
neighbouring pad, and kept a flat landing for unequal Power56 pads.  That left
`5L1` pads stopping abruptly and, after the first Voronoi attempt, put the
bisector on the **gate** side of a Power56: the nearest single pad was the gate,
not the neighbouring power tab.

**What changed:** every terminal now gets the same geometry: a straight corridor
between pad centres, a full round end at the pad centre, and that disc clipped
at the perpendicular bisector to the **nearest foreign power terminal group**
(the tab centre, not the gate).  A Power56's unnumbered thermal pads are
renumbered as duplicate exposed-pad pins (and given that net), so they no
longer act as no-net obstacles and leave a hole in the middle of the FET.  GND landings use the same full-Voronoi rule; they are
filled after the power/plane zones, with the power corridors subtracted at
0.30 mm so the second fill pass cannot violate clearance.

**Numbers (main board, 4Q1 close):** 20 pours (16 power + 4 GND landings),
high-current **16/16 PASS**, channels **0 short**, DRC **257 unconnected**
(unrouted taps), **0 clearance**, **0 zone islands**.  Fill: `VIN_SYS` 1.93,
`VBAT` 0.82, `SW1_OUT` 1.96, `N_CS` 1.08, `N_PACKMID` 1.58, `VOUT12` 3.49 mm.
`N_PACKMID` remains **2.5 mm free channel, pad-limited** (0.70 mm series pad,
32 A terminal) — moving `4Q1`/`4Q2` apart raises the free channel, not the
pad-limited copper.
