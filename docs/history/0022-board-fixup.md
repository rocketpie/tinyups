# 0022 – Board fixup: power pours, charger input, CELL0

**Power-first pours.** The constant-width corridor and round caps overhung the
neighbouring net at shared parts, so the filler split `VIN_SYS`, `VBUS`,
`SW2_OUT` and `N_CS`. The corridor now tapers into each pad at the pad's
terminal width (cap = the pad's inscribed radius); the report measures the
designed corridor and treats a zero fill as a hard split. Each pour also gets an
F.Cu rule area (tracks forbidden, vias and pours allowed), and the UI shows the
applied board's pours. The full-corridor keepout made freerouting oscillate
(67–146 unrouted); the narrower margin keepout is still too strong for this
4-layer board. `route.py` stops after 10 min without a >5 % score gain. `N_CS`
still has one of three parallel source pins outside the fill; `N_PACKMID`
remains 1.5 / 7.5 mm.

**Charger input.** `VBUS` had no adapter feed: only `2R1` pad 1 and `2U1`
`VBUS`/`ACP`. The three `VBUS` labels are `VIN_SYS` now, so the netlist feeds
`2R1` and the BQ25720 `VBUS`/`ACP` pins from the 12 V rail. The 10 A flows
through the external `2R1` → `N_ACN` → `2Q1`/`2Q2`, not through the QFN pins
(`VBUS` is supply, `ACP`/`ACN` are sense). The old `2R1`→`2U1` pour was a sense
island and is gone; `sync_footprints.py` now re-applies pad nets from the
netlist even when no footprint changes.

**CELL0.** `CELL0` is the pack return through `4R1` (17 A), not a Kelvin tap; it
had been set to 0.01 A, which removed the `4R1` pour. It is 17 A again; `CELL4`
is the 0.01 A tap.

**Status:** fixed; the placement needs a touch-up around `2R1`/`2U1` and the BMS
pair, and the keepout strategy is still open. The sense taps are
[0025](0025-sense-gate.md).
