# 0018 — placement UI: route feedback and pad nets

**What:** the placement UI grew a route-feedback loop and a pad-level net view,
and in the process exposed a set of **stale-data** bugs rather than drawing bugs:
the graph was built from the netlist, route markers were coloured by the net's
design current, the pad MST was purely geometric, the rotation buttons were
labelled backwards, and the belongs-to fallback picked an IC from another block.

**Why:** the board, not the netlist, is the component source of truth. After the
last component swap, `extract.py` still loaded the netlist's old footprint ids
(`1F1` a blade fuse, `2R1` a WSR2) and drew their pads/courtyards: 8 false
courtyard overlaps and a pad-clearance metric that did not match the DRC. The
pad-level view then coloured every pad on a 20 A net red, so a 100 k pull-up
looked like a power trace, and its geometric MST linked `1F1` to the nearest tap
instead of to `1R1`.

**Status:** fixed — `extract.py` now reads the board's own footprints; all
**507 pads match the board within 0.0005 mm**, courtyard overlaps fell **8 → 0**,
and the live clearance metric matches the DRC (`5U1` 0.15 mm, one part). The
placement numbers moved with the real geometry: HPWL 3527 → 3525, wHPWL
13452 → 13428, wire 3960 → 3910, axisR 0.68 → 0.78, in/out 31/38 → 10/13.

`hardware/route_feedback.py` (run by `make route` and by Apply-to-board + DRC)
writes unrouted/clearance/power-channel JSON; the UI overlays it and lists the
counts, with clickable legend filters. On the applied unrouted board that is
**284 pad-to-pad unrouted pairs** and one channel short (`N_AF` 3.3 / 9.4 mm);
the 21 amber clearance items were the missing-rules artifact of
[0017](0017-drc-rules-do-not-follow-a-board-copy.md). The router log itself is
5 passes at 52/28/18/81/13 unrouted, 0 violations, best score 942.22.

The pad-level ratsnest uses each **pad's** conducted current and a
thickest-first Kruskal tree, so `1F1.2 → 1R1.1` (N_AF) and `4J6.1 → 4Q1.3`
(PACK+) show 17–20 A while `1R7`/`5R7` taps stay 0.1 A hairlines. `power_spec`
is now the single `DESIGN_CURRENT` table (`PACK+` added, VSYS/SW1/SW2 at 10 A):
the power gate is **24/24 FAIL** on the unrouted board, and `N_PACKMID` is the
second channel short (5.0 / 7.5 mm).

Also fixed: pin/unpin in place, ±90° rotation with the CW/CCW buttons the right
way round (KiCad Y-down: positive angle is visually CCW), a collapsible Engine
body, amber pad-clearance / red courtyard-overlap outlines, and the belongs-to
fallback constrained to the part's own block (`2C9` now rings `2U1`, not `6U3`).

**Follow-up:** a GND-return overlay for power parts (the pack return ends in the
plane, which the ratsnest drops), and starting `make route` from the UI so the
same feedback refreshes without a terminal. The metrics row for the
`DESIGN_CURRENT` correction is power row 9 in [`docs/progress.md`](../progress.md).
