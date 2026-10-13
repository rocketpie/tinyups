# TinyUPS – Progress & metrics log

Running record of the layout work. Tables are **pivoted so each new approach is
a new row** — append a row per experiment and compare across columns.

Reproduce any row with:
```sh
/opt/eda/venv/bin/python hardware/place_metrics.py      # placement
/opt/eda/venv/bin/python hardware/routing_report.py     # routing / fab
/opt/eda/venv/bin/python hardware/power_report.py       # power / ampacity (gate)
kicad-cli pcb drc --severity-all --output reports/drc.rpt hardware/tinyups.kicad_pcb
```

## Metric tiers

1. **Gates (must be 0):** ERC, DRC, unconnected nets, schematic↔PCB parity.
2. **Manufacturability/cost:** fab tier, min trace/clearance, layers, board
   size, via count.
3. **Layout quality:** decap distance, critical-loop length (SW nodes),
   power-net HPWL, inter-block nets.
4. **Performance** (from `requirements.md`, verified on the bench): output
   voltage, ripple, efficiency, standby, runtime, thermal.

## Placement (rows = approach)

| # | Approach | total HPWL (mm) | weighted HPWL (mm) | power HPWL (mm) | decap mean (mm) | decap max (mm) | notes |
| - | -------- | --------------: | -----------------: | --------------: | --------------: | -------------: | ----- |
| 1 | shelf-pack (naive) | 9955 | 17504 | 1510 | 36.9 | 82.9 | global packing, all parts in one flow |
| 2 | block-aware, BW=52 | 5188 | 13461 | 1353 | 18.2 | 56.2 | parts grouped by functional block |
| 3 | block-aware, pad-bbox, 3-col | 4063 | 10187 | 1225 | 17.2 | 58.9 | pad-only extents (denser) |
| 4 | + connector padding, margin 3 mm | 5188 | 13461 | 1654 | 18.2 | 65.5 | DRC-clean placement |
| 5 | + decap-aware ordering + SW1/SW2 fix | 4978 | 12274 | 1459 | 21.2 | 65.5 | nets 115 |
| 6 | decap tightening (IC+caps group packing) | 6583 | 14199 | 1523 | 16.2 | 48.5 | **rejected** — board 146 mm tall, HPWL much worse |

Rows 1–5 are from earlier runs in this project's history.

## Routing (rows = approach)

| # | Stackup | Rules | Unrouted | Min trace (mm) | Below rule | Unconnected | Vias | Notes |
| - | ------- | ----- | -------: | -------------: | ---------: | ----------: | ---: | ----- |
| 1 | 4L, GND + VIN_SYS planes | 0.20 mm | — | — | — | — | — | never converged (oscillated ~90–140) |
| 2 | 4L, GND + VIN_SYS planes | 0.12 mm (loose) | 21 | — | — | — | — | converged, incomplete |
| 3 | 4L, GND + VIN_SYS planes | 0.13 mm | 0 | 0.063 | 111 (vs 0.127) | 2 | 294 | QFN fanout thin |
| 4 | 4L, GND + 3 signal | 0.127 mm | 0 | 0.063 | 100 | 2 | 290 | stackup fix |
| 5 | 4L, GND + 3 signal, SW1/SW2 fixed | 0.127 mm | 1 | 0.095 | 78 | 4 | 288 | fab: advanced PASS, standard FAIL |
| 6 | + radial QFN fanout (scripted escapes) | 0.127 mm | — | 0.127 | 0 | — | — | **rejected** — escapes hit 42 clearance + 14 shorts at package corners |

## Power / ampacity (rows = state)

Gate: every power net must carry its **design current**. `power_report.py`
computes the ampacity of the narrowest segment of each net (IPC-2221,
dT = 10 °C, 1 oz outer / 0.5 oz inner — JLCPCB 4-layer default) and compares it
against the current from `requirements.md`/`bom.md`. A signal-width trace is
not a power trace.

| # | State | Power routing | min power width | Nets failing | Notes |
| - | ----- | ------------- | --------------: | -----------: | ----- |
| 1 | routed, advanced accepted | power as 5 mil signal traces (F/In1/In2) | 0.095 mm | **10/10** | **baseline — FAIL** |

Baseline detail (state 1): `+12V_IN` XT60 → 25 A fuse is a single 0.127 mm
**In2.Cu** trace (~0.27 A ampacity); `VIN_SYS` (20 A) is 0.095 mm (~0.43 A).
Every power net is 0.095–0.127 mm; there is **no power pour anywhere** (the
only zone is the GND plane). Worst case ≈ **46× short**. DRC cannot see this
(no ampacity rule), which is why it slipped through.

## Gates & fab (rows = state)

| State | ERC | DRC violations | Unconnected | Standard 5 mil | Advanced 3.5 mil |
| ----- | --: | -------------: | ----------: | -------------- | ---------------- |
| schematic only | 0 | n/a | n/a | — | — |
| routed, pre-fix | 0 | 102 | 2 | FAIL | PASS |
| routed, SW1/SW2 fixed | 0 | 79 | 4 | FAIL (78 fanout) | PASS |
| routed, **advanced tier accepted** | 0 | **1** (dangling via) | **4** (3 GND stubs + `ILIM_HIZ`) | deferred | **PASS** |
| routed + manual DRC fix (advanced rules) | 0 | **0** | **0** | FAIL (78 fanout) | PASS |
| **same board under standard 5 mil rules** | 0 | **524** (446 clearance + 78 width) | 0 | **FAIL** | PASS |

Final routed state: 1315 tracks, 288 vias, min trace 0.095 mm (advanced PASS),
inter-block 8 nets. Remaining DRC: 1 dangling via + 4 unconnected (3 GND stubs
that need a plane via, and the `ILIM_HIZ` signal) — a few minutes of manual
cleanup in the GUI.

## Decision

**Fab tier: go back to standard 5 mil by default (NFR-9).** The board had been
accepted at the JLCPCB **advanced** 3.5 mil tier to escape the 0.4 mm-pitch
QFNs. We are targeting the **standard 0.127 mm** tier again and solving the QFN
fanout / stackup properly instead of buying the fine pitch. Advanced stays only
for a documented geometry that genuinely cannot meet 5 mil. The current routed
board does **not** meet standard yet: 524 DRC violations (446 clearance + 78
width) under the 5 mil rules.

**Power path strategy (proposed, ADR-0008).** Stackup **F.Cu = power pour
(+ signals around it), In1.Cu = GND, In2.Cu = signal, B.Cu = signal (+ GND
pour)** — GND stays adjacent to the power layer so the converters' hot loops
close tightly. High-current nets (input, `VIN_SYS`, `VBAT`, `VOUT12`, switch
nodes) are carried as **pours** on the power layer, not as signal-width traces.
Floorplan: external connectors first (XT60 in / XT30 + USB out), then the power
path **straight back→front** with two right-hand branches (back half → charger,
front half → pack/BMS output), then the RP2040 on the left. Tooling must
enforce the power ampacity gate.

The old advanced-tier acceptance is superseded by this decision.


## Findings worth keeping

- **Placement metrics caught a schematic bug:** `SW1`/`SW2` merged the charger
  and output switch nodes (10 pads). Splitting them cut SW-node HPWL from
  ~240 mm to ~65 mm and inter-block nets from 10 to 8.
- **A dedicated power plane hurt.** VIN_SYS on In2 cost a signal layer and the
  router perforated it anyway; `F.Cu / GND / signal / signal` routes at 5 mil.
- **The QFN fanout is the only sub-5-mil feature.** 0.4 mm-pitch parts
  (RP2040, BQ25720, LM5176) need the fine traces; everything else is 5 mil.
- **Decap distance is the standing weak point** (~18–21 mm vs a <5 mm target).
- **Decap tightening (this pass) traded HPWL for decap** and overshot the board
  height → rejected. Reaching <5 mm needs **pin-level** placement (caps at the
  specific supply pins), not bbox-level packing.
- **QFN fanout (this pass):** scripted radial 5 mil escapes (QFN pads are
  perimeter-only, so escapes *should* fit) collided at the package corners
  (42 clearance + 14 shorts) regardless of escape length. A reliable 5 mil
  fanout needs careful per-side geometry (or via-in-pad/HDI). Practical
  outcome: **the QFN fanout stays at the advanced tier (3.5 mil)** unless
  finished by hand.
