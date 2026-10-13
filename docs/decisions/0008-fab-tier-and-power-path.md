# 0008 – Fab tier and power-path-first layout strategy

- Status: proposed (fab tier: accepted)

## Context

The board was routed by an autorouter at the JLCPCB **advanced** 3.5 mil tier,
because the 0.4 mm-pitch QFNs (RP2040, BQ25720, LM5176, BQ76942) cannot be
escaped at 5 mil with plain traces. Along the way the autorouter used the
minimum width (0.095–0.127 mm) for **everything**, including the power path,
and no power pours were ever added. `hardware/power_report.py` shows the
result: all 10 power nets are undersized — e.g. the XT60 → 25 A fuse link is a
single 0.127 mm trace on In2.Cu (~0.27 A ampacity), and `VIN_SYS` (20 A) is
0.095 mm (~0.43 A). Worst case ≈ 46× short. DRC has no ampacity rule, so this
passed every gate.

Two things were wrong at once: (1) we bought the advanced tier instead of
solving the fine pitch, and (2) the layout had no notion of a power path.

## Decision

1. **Target the standard 5 mil tier (min trace/clearance 0.127 mm) by
   default.** Advanced 3.5 mil is only for a documented geometry that genuinely
   cannot meet 5 mil (NFR-9). The design rules (`.kicad_dru`, project rules,
   `gen_pcb.py`) now enforce 5 mil, so the current board shows 524 violations
   (446 clearance + 78 width) — the honest baseline.
2. **Power first, then signals.** The layout is organised around a power path,
   not around an autorouter:
   - **Stackup: `F.Cu` = power pour (+ signals routed around it),
     `In1.Cu` = GND, `In2.Cu` = signal, `B.Cu` = signal (+ GND pour).** GND
     stays **adjacent to the power layer** so the switching converters' hot
     loops (input cap → switch FET → GND return) close tightly; power on the
     top outer layer gives a direct pad connection (no via bottleneck) and
     1 oz copper. (Rejected alternative: power F / GND B / signal In1+In2 —
     puts the power return two layers away and leaves In1 without a GND
     reference.)
   - High-current nets (`+12V_IN`, `N_AF`, `VIN_SYS`, `VBAT`, `VSYS`,
     `VOUT12`, switch nodes) are carried as **copper pours** on the power
     layer, sized to their design current — never as signal-width traces.
   - **Floorplan:** external connectors first (XT60 input at the back/centre,
     XT30 output + USB at the front; USB left of XT30), then the power path
     laid **straight back→front**, branching right twice (back half → charger,
     front half → pack/BMS output), then the RP2040 on the left; signals use
     the remaining copper (top layer around the corridor, In2, B.Cu).
3. **Add the missing gate.** `hardware/power_report.py` sizes every power net
   against its design current (IPC-2221) and fails CI otherwise.

## Consequences

- The autorouter cannot be the source of truth any more: the power path and the
  floorplan are **encoded in `gen_pcb.py`** (anchored placement + pours), and
  `route.py` must keep signals off the power corridor / plane layers (mark
  `F.Cu` as power and `In1.Cu` as plane in the DSN so signals go on the
  remaining copper).
- Signals get the top layer **around the power corridor**, plus `In2.Cu` and
  `B.Cu`. Whether that carries everything is the main risk; the floorplan
  (short, mostly intra-block nets) has to make it work. `routing_report.py`
  will show whether it does.
- The fuse footprint must be revisited: F1 is a `Fuse_1206_3216Metric`, which
  physically cannot be a 25 A fuse (BOM already flags the value "(verify)").
- Copper weight matters: JLCPCB 4-layer default is 1 oz outer / 0.5 oz inner,
  so inner-layer pours carry about half the current of outer ones.
- Related requirements: FR-1, FR-3, FR-5, NFR-1, NFR-7, NFR-9.

## Open questions

- Does the pack branch and the charger branch really tap the same rail node, or
  do they connect at different points along the power path? (Topology from
  ADR-0002: input → protection → {priority path, charger}; pack → priority
  path → converter.)
- 2 oz outer copper (JLCPCB option) may be worth it for the power pours.
