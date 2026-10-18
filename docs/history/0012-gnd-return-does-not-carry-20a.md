# 0012 – The GND return does not carry 20 A

**What:** the first pour-aware ampacity measurement. `power_report.py` can now
size a **pour** (a zone), not just a trace — a min-cut test: erode the filled
polygon by w/2 and ask whether the pads the current flows between are still
joined. Pointed at the only pour, the `In1.Cu` GND plane, and measured between
the return's two ends (`1J1` GND ↔ `5J2` GND):

| case | min cut | capacity |
| --- | --- | --- |
| routed `try5` (plane split into 5 islands, thermal pads) | 0.00 mm | 0 A |
| unrouted board, **solid** pad connections, plane in one piece | **9.38 mm** | 3.67 A @0.5 oz, 6.06 A @1 oz |

20 A wants **97 mm** of continuous copper at 0.5 oz inner (49 mm at 1 oz) by
IPC-2221 at 10 °C. The plane delivers a tenth of that.

**Why:** a plane is a sheet, not a wide trace; its capacity is the min cut
between the pads the current flows between, and three things eat it at once —
signals routed on `In1.Cu` (177 tracks cut it into 5 pieces), thermal pad
connections (~0.7 A per pad, and the pad centre is a hole in the fill), and pad
antipads (a clean plane still pinches to 9.38 mm).

**Consequence:** the return needs the plane *plus* outer copper. 9.4 mm of 2 oz
carries 20 A, and the plane's 9.38 mm cut contributes ~2.4 mm of 2 oz-equivalent
at 0.5 oz — so roughly **7 mm of GND pour on `F.Cu`/`B.Cu` beside the rail pour**
closes it. The scary "97 mm" only applies if the return runs in the inner plane
alone.

**Sizing:** 200 W sustained on the input leg (160 W load + 40 W charge, 240 W
adapter ceiling) ⇒ **20 A** stands; charger legs ~8 A (not 1C), output/pack
17 A peak. `DESIGN_CURRENT` was corrected for `VSYS`/`SW1`/`SW2` accordingly.

**Status:** open. Not a routing problem — it needs outer-layer copper, solid pad
connections, signals off `In1.Cu`, and a placement that gives the path a corridor.
