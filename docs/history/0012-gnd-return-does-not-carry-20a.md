# 0012 – The GND return does not carry 20 A

**What:** the first pour-aware ampacity measurement. `power_report.py` can now
size a **pour** (a zone), not just a trace — a min-cut test: erode the filled
polygon by w/2 and ask whether the pads the current flows between are still
joined, i.e. whether copper at least w wide connects them. Pointed at the one
pour that exists, the GND plane on `In1.Cu`, and measured **between the two ends
of the return** (`1J1`'s GND ↔ `5J2`'s GND), which is the honest question:

| case | min cut | capacity |
| --- | --- | --- |
| as built, routed `try5` (plane split into **5 islands**, thermal pads) | 0.00 mm | 0 A |
| unrouted board, **solid** pad connections, plane in one piece | **9.38 mm** | 3.67 A @ 0.5 oz, 6.06 A @ 1 oz |

20 A wants **97 mm** of continuous copper at 0.5 oz inner (49 mm at 1 oz) by
IPC-2221 at 10 °C rise. The plane delivers a tenth of that.

**Why — a plane is a sheet, not a wide trace.** Its capacity is the min cut
between the pads the current flows between, and three things each eat it, all
present at once:

1. **Signals routed on the plane layer** — 177 tracks of `try5`'s route are on
   `In1.Cu`, which cuts the plane into 5 pieces (and is where its GND
   unconnected pads come from).
2. **Thermal pad connections** (`gen_pcb.py` sets `ZONE_CONNECTION_THERMAL`) —
   fine for hand soldering, ~0.7 A per pad at 0.5 oz, and the pad centre is a
   *hole* in the fill so the pour measures 0 there.
3. **Pad antipads** necking the sheet — a clean plane still pinches to 9.38 mm.

For reference, the cut across **all 71** GND pads is 1.41 mm. That is the right
number for "is the plane one piece", but it is over-strict for ampacity:
signal grounds carry milliamps, and only the return's own ends matter.

**Consequence for the design.** The return needs the plane *plus* outer copper.
9.4 mm of 2 oz carries 20 A, and the plane's 9.38 mm cut contributes about 2.4 mm
of 2 oz-equivalent at 0.5 oz — so roughly **7 mm of GND pour on `F.Cu`/`B.Cu`
beside the rail pour** closes it. That is a spine, not a lake; the scary "97 mm"
only applies if the return is asked to run in the inner plane alone.

**Sizing case (maintainer, this session):** 160 W load + 40 W charge = 200 W on
the input leg, held while the servers come back up with empty cells; the
adapter's 240 W is the ceiling, so **20 A** on the input leg stands. The charger
legs are **FR-5's ~8 A** (default 5 A, the charger's input-current limit caps at
~8 A) — not the cell's 1C capability — and the output/pack legs 17 A peak.
`power_report.py`'s `DESIGN_CURRENT` was corrected for `VSYS`, `SW1`, `SW2`
(16/10 → 8 A) with that citation.

**Status:** open; the gate (`power_report.py`) is pour-aware and `GND` is in it.
Nothing here is a routing problem — it needs copper area on the outer layers,
solid pad connections, signals off `In1.Cu`, and a placement that gives the
power path a corridor to run in.
