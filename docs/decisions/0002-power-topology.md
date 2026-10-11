# 0002 – Power topology: 4S LiFePO₄ with a regulated 12 V output

- Status: accepted

## Context

The load is a picoPSU-160-XT (160 W continuous / 200 W peak) that needs a
12 V input within ±10 %, i.e. **10.8–13.2 V**, and whose +12 V rail is
essentially the input passed through. The energy source is a 4S1P LiFePO₄
pack (11.2–13.8 V usable). A full pack is *higher* than the 12 V adapter.

## Decision

1. **4S LFP** pack (12.8 V nominal) — the voltage window overlaps the picoPSU
   window, so little conversion is wasted.
2. **Always-regulated 12.0 V buck-boost** produces the output from either
   source, keeping the picoPSU in spec across the whole pack range.
3. **Active input-priority power path** (power mux / back-to-back FETs), *not*
   a passive ideal-diode OR, because a charged pack (13.8 V) would otherwise
   win the OR and cycle the battery on mains.
4. **Buck-boost (4-switch) CC/CV charger** from the 12 V input to the pack,
   because the pack is both above and below 12 V depending on SOC.
5. Two independent paths on mains: load from the input, pack charged in
   parallel, so the 20 A adapter can run the load and charge at once.

## Consequences

- Output stays in the picoPSU window under all conditions; transfer on input
  loss is seamless and must not reset the host.
- One conversion in the output path even on mains; efficiency target ≥ 90 %.
- Requires a priority power-path controller and two switching stages
  (charger + output), i.e. more silicon and layout care than a passive design.
- Related requirements: FR-1, FR-2, FR-3, FR-4, FR-5, IF-1, IF-3, NFR-1.
