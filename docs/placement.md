# Placement intent

Placement is a design decision, not a netlist side effect.  Every footprint has
a **role** (what it does), and every part that has a physical requirement has
**limits**: the host it belongs to, a minimum and/or maximum distance, and the
reason.  The machine-readable source is
[`hardware/placement_spec.py`](../hardware/placement_spec.py); the report is
`make proximity` (writes `reports/proximity.rpt`), and the placement UI reads
the same limits from `build/layout/graph.json`.

There is no second, inferred copy.  The old "most specific shared net, nearest
Q/J on a tie" model is gone: on a flat rail such as `VIN_SYS` every candidate
ties, so it attributed four unrelated capacitors to one switch.  See
[history 0030](history/0030-placement-intent.md).

## What a limit means

| measure | measured between | used for |
| --- | --- | --- |
| `pad` | copper edge of the part pad and the host pad **on the named net** | bypass, filter, gate and Kelvin loops — the trace that matters |
| `edge` | courtyard/body boxes | thermal and EMI keep-aways |
| `board_edge` | body and the board outline | connectors, headers, panel parts |

`min_mm` is a keep-away (too close is the violation); `max_mm` is a reach (too
far is the violation).  A part may have several limits: for example `3C2` must
be within 10 mm of `5Q1`, within 15 mm of `5U1`, and at least 4 mm away from
the heat of both.

## Target families

The datasheets say "close" or "as close as possible"; these are the board-level
translations, applied consistently.

| family | reach | basis |
| --- | ---: | --- |
| high-di/dt pin loop: boot, VCC, VIN ceramic, gate | **3–5 mm** pad | LM5176 §10.1, BQ25720 Table 12-1 rules 2–9 |
| filtered sense / feedback / compensation node | **3–5 mm** pad | LM5176 §10.1, BQ76942 §18.1 |
| bias, divider, pull-up, enable | **10 mm** pad | controller pin is the reference |
| current-sense shunt → controller (Kelvin) | **10 mm** pad | LM5069 §11.1, BQ25720 rule 7, BQ76942 §18.1; the tap itself is checked by `make sense` |
| switching cell: FETs + inductor + shunt | **5–10 mm** pad | LM5176 §10.1, BQ25720 rules 2–6 |
| bulk input/output capacitor | **15 mm** pad | loop inductance; sim needs the hold-up at the converter input |
| electrolytic can near a FET/inductor | **≥ 4 mm** edge | electrolyte life; LM74700-Q1 §12.1 keeps the charge-pump cap off the FET for the same reason |
| analog IC / crystal / USB / cell harness near a 300–800 kHz inductor | **≥ 10–20 mm** edge | radiated field and thermal |
| connector / header / panel part | **0.5–6 mm** body to outline | mechanical access |

## Per block

### A — input protection (LM5069)

| part | limit | reason |
| --- | --- | --- |
| `1J1` | body 0.5–3 mm from outline | panel XT60 |
| `1F1` → `1J1`, `1R1` | ≤ 10 mm pad | first element, unfused stub short |
| `1D1` → `1F1` | ≤ 10 mm pad | TVS clamps at the fuse output |
| `1Q1` → `1U1` | ≤ 10 mm pad (`N_GATE`) | gate loop |
| `1R1` → `1U1` | ≤ 10 mm pad | Kelvin shunt tap |
| `1C1` → `1U1` | ≤ 3 mm pad (`N_TMR`) | timer capacitor |
| `1R2`–`1R7` → `1U1` | ≤ 10 mm pad | UV/OV/PWR/PGD set at the pins |

### B — priority power path (LM74700-Q1)

| part | limit | reason |
| --- | --- | --- |
| `3U1` ↔ `3Q1` | ≤ 5 mm pad on `N_PGATE`, `VBAT`, `VIN_SYS` | ANODE/GATE/CATHODE at source/gate/drain |
| `3C1` → `3U1` | ≤ 5 mm pad (`N_VCAP`) | charge-pump capacitor |
| `3C1` vs `3Q1` | ≥ 5 mm edge | keep the cap off the FET heat |
| `3C2`, `3C3` → `5U1` | ≤ 15 mm pad (`VIN_SYS`) | converter input hold-up for the handover |
| `3C2`, `3C3` → `5Q1` | ≤ 10 mm pad | bulk loop closes at the input FET |
| `3C2`, `3C3` vs `5Q1`, `5L1` | ≥ 4 mm edge | electrolyte life |

`3C2`/`3C3` are **not** charger capacitors: they are the converter-input
hold-up that carries `VIN_SYS` through the input→pack handover
(`sim/power-path.cir`).

### C — charger (BQ25720)

| part | limit | reason |
| --- | --- | --- |
| `2Q1`–`2Q4` → `2U1` | ≤ 5 mm pad (gate nets) | gate loop |
| `2Q1`/`2Q2` ↔ `2L1`, `2Q3`/`2Q4` ↔ `2L1` | ≤ 10 mm pad (`SW1`/`SW2`) | switching cell |
| `2Q1` ↔ `2Q2`, `2Q3` ↔ `2Q4` | ≤ 5 mm pad | half-bridge loop |
| `2R1` → `2Q1` / `2U1` | ≤ 5 / 10 mm pad | RAC loop and Kelvin pair |
| `2R2` → `2Q4` / `2U1` | ≤ 5 / 10 mm pad | RSR loop and Kelvin pair |
| `2U1` vs `2Q1`–`2Q4` | ≥ 3 mm edge | controller next to, not under, the FETs |
| `2C1`, `2C2` → `2U1` + switch | ≤ 3 mm pad | bootstrap loop |
| `2C3`, `2C4`, `2C6`, `2C7`, `2R3`–`2R5` → `2U1` | ≤ 3 mm pad | pin bypass / filter |
| `2C5`, `2C8`, `2C9` ↔ `2R8`, `2R9`, `2R10` | ≤ 3 mm | RC filter pair (the pin sees the filtered node) |

### E — battery AFE (BQ76942)

| part | limit | reason |
| --- | --- | --- |
| `4C1`–`4C10` → `4U1` | ≤ 3 mm pad | cell/supply filters at the AFE pins |
| `4R9`–`4R13` → `4U1` | ≤ 5 mm pad | 100 Ω cell filter resistors |
| `4R9`–`4R13` → `4J7` | ≤ 30 mm pad | cell harness reach |
| `4R1` → `4U1` / `4J6` | ≤ 10 / 5 mm pad | pack shunt Kelvin and return |
| `4Q1`, `4Q2` → `4U1` | ≤ 10 mm pad (gates) | charge-pump gate loop |
| `4Q1` ↔ `4Q2` | ≤ 5 mm pad (`N_PACKMID`) | common-source pair |
| `4Q1`, `4Q2` vs `4U1` | ≥ 5 mm edge | thermal |
| `4R2`–`4R4` → `4J7` / `4U1` | ≤ 20 mm edge / ≤ 30 mm pad | NTC at the pack harness, TS line to the AFE |
| `4R2`–`4R4` vs power FETs/inductors | ≥ 15 mm edge | must read pack, not board, temperature |
| `4U1` vs `2L1`, `5L1` | ≥ 20 mm edge | AFE away from the switching field |

### D — output converter (LM5176)

| part | limit | reason |
| --- | --- | --- |
| `5Q1`–`5Q4` → `5U1` | ≤ 5 mm pad (gate nets) | gate loop |
| `5Q1`/`5Q2` ↔ `5L1`, `5Q3`/`5Q4` ↔ `5L1` | ≤ 10 mm pad | switching cell |
| `5Q1` ↔ `5Q2`, `5Q3` ↔ `5Q4` | ≤ 5 mm pad | half-bridge loop |
| `5R3` → `5U1` / `5Q2`,`5Q3` | ≤ 10 / 5 mm pad | Kelvin pair and low-side path |
| `5C1` → `5U1`, `5Q1` | ≤ 3 mm pad (`VIN_SYS`) | input bypass and loop |
| `5C2`–`5C8` → `5U1` | ≤ 3 mm pad | pin bypass / timing |
| `5C2` → `5Q1`, `5C3` → `5Q4` | ≤ 3 mm pad | bootstrap switch-node loop |
| `5R1`, `5R2` → `5U1` | ≤ 3 mm pad (`N_FB`) | feedback divider at FB |
| `5R4`, `5R5`, `5R6` → `5U1` | ≤ 3 mm pad | RT / MODE / COMP |
| `5C9` → `5J2` / `5Q4` | ≤ 15 / 10 mm pad | bulk output at connector and cell |
| `5C9` vs `5L1`, `5Q4` | ≥ 4 mm edge | electrolyte life |
| `5C10` → `5Q4` / `5J2` | ≤ 3 / 15 mm pad | output ceramic |
| `5J2` | body 0.5–3 mm from outline | XT30 output |

### F — control, host link, UI

| part | limit | reason |
| --- | --- | --- |
| `6Y1` → `6U1` | ≤ 5 mm pad (`N_XIN`) | crystal at the oscillator |
| `6C1`, `6C2` → `6U1` / `6Y1` | ≤ 3 mm | load capacitors at pin and body |
| `6U2` → `6U1` | ≤ 15 mm pad (`N_QCS`) | QSPI flash, short direct traces |
| `6U3` → `6U1` | ≤ 15 mm pad (`+3V3`) | regulator at its load |
| `6C3` → `6U3` | ≤ 3 mm pad (`VIN_SYS`) | 3.3 V buck input bypass |
| `6C4` → `6U1` / `6U3` | ≤ 5 / 10 mm pad | MCU decoupling and regulator output |
| `6C5` → `6U1` | ≤ 3 mm pad (`N_DVDD`) | DVDD bypass |
| `6R6`, `6R7` → `6U1` | ≤ 3 mm pad | 27 Ω USB series termination |
| `6J3` → `6R6` | ≤ 10 mm pad | USB pair to termination |
| `6J3` → `6U1` | ≤ 20 mm edge | connector reach |
| `6J4` → `6U1` | ≤ 30 mm pad (`N_SWCLK`) | SWD access |
| `6J5` → `6U1` | ≤ 20 mm pad (`N_FANPWM`) | fan control |
| `6J3`, `6J4`, `6J5` | body 0.5–6 mm from outline | connector access |
| `6Y1`, `6J3` vs `2L1`,`5L1` | ≥ 15 mm edge | switching field |
| `6U2`, `6R6`, `6R7` vs `2L1`,`5L1` | ≥ 10 mm edge | switching field |

## Parts without a proximity rule

Declared explicitly, with the reason:

- `2R6`, `2R7` — I2C pull-ups; the bus is distributed, any point is equivalent.
- `6D1`–`6D4` — panel LEDs; position is set by the enclosure/light pipe.

`2U1`, `5U1` and `5L1` are **anchors**: their position is set by the parts that
must come to them.  The 470 µF hold-up pair and the NTCs assert their limits on
both sides, so the rule sits on the part that moves.

## Changing the rule

1. Edit `hardware/placement_spec.py`; every part needs a role and either a
   limit or an entry in `FREE`/`ANCHORS`.
2. Run `make proximity` (the coverage check fails if a footprint on the board
   has no role).  To inspect one part:
   `make proximity PART=5Q3` — `make` itself parses `--part`, so pass it as a
   variable (or `PROX_ARGS="--part 5Q3"`) rather than after the target.
3. `make place` regenerates the graph; the UI's belongs-to ring and inspector
   use the same limits.

An ADR is required when a target family changes, not when a part is added.
