# TinyUPS – metrics log

Metrics only. One row per change to the process, board or metric; the **change**
column says what changed and **note** links the [history](history/) entry that
explains it. A blank cell means the metric was not measured.

Measure: placement — `ui/placement` (UI, or `render.py` on a saved placement);
routing — `hardware/routing_report.py`; power — `make power`, `make channels`;
gates — `make erc`, `make drc`.

## Placement

| # | change | HPWL | wHPWL | pow HPWL | decap m/max | pw parts | mean \|dx\| | max \|dx\| | straight | note |
| - | ------ | ---: | ----: | -------: | ----------: | -------: | ----------: | ---------: | -------: | ---- |
| 1 | shelf-pack | 9955 | 17504 | 1510 | 36.9 / 82.9 | | | | | all parts, one flow |
| 2 | block-aware, BW=52 | 5188 | 13461 | 1353 | 18.2 / 56.2 | | | | | grouped by block |
| 3 | block-aware, pad-bbox, 3-col | 4063 | 10187 | 1225 | 17.2 / 58.9 | | | | | pad-only extents |
| 4 | +connector padding, 3 mm | 5188 | 13461 | 1654 | 18.2 / 65.5 | | | | | DRC-clean |
| 5 | +decap-aware order, SW1/SW2 fix | 4978 | 12274 | 1459 | 21.2 / 65.5 | | | | | 115 nets |
| 6 | decap tightening | 6583 | 14199 | 1523 | 16.2 / 48.5 | | | | | rejected (146 mm tall) |
| 7 | power-path floorplan | 5942 | 12718 | 1355 | 17.3 / 48.9 | | | | | connectors anchored, 150×140 |
| 8 | block-aware shelf-pack (power pass) | | | | | 25 | 22.9 | 61.5 | 6.19 | |
| 9 | +pack terminals J6/J7 | | | | | 27 | 22.7 | 62.0 | 6.27 | |
| 10 | power-first bands | | | | 14.7 / — | 26 | 12.3 | 35.0 | 4.14 | HPWL 5942→8227 |
| 11 | try5 hand-tuned (UI) | 3527 | 13452 | | | | | | | wire 3960, ovl 8, axisR 0.68 — [history 0015](history/0015-placement-cleanup.md) |
| 12 | fixed1 hand-tuned (UI) | 3672 | 16501 | | | | | | 0.76 | wire 4295, ovl 0, out 0, axisR 0.76, path 574 — [history 0019](history/0019-board-fixup.md) |
| 13 | fixed2 hand-tuned (UI, new power parts) | 3736 | 17577 | | | | | | 0.78 | wire 4362, ovl 0, out 0, axisR 0.78 — [history 0019](history/0019-board-fixup.md) |
| 14 | fixed2 + Power56 FETs | 3804 | 16855 | | | | | | 0.79 | wire 4365, ovl 0, out 0, axisR 0.79 — [history 0020](history/0020-fet-pin-mapping.md) |
| 15 | fixed3 hand-tuned (UI) | 3771 | 17456 | | | | | | 0.78 | wire 4373, ovl 0, out 0, axisR 0.78 — [history 0020](history/0020-fet-pin-mapping.md) |
| 16 | fixed4 hand-tuned (UI) | 3233 | 14663 | | | | | | 0.80 | wire 4141, ovl 0, out 0, axisR 0.80 — [history 0022](history/0022-board-fixup.md) |
| 17 | fixed5 (4Q1 −6 mm) | 3227 | 14661 | | | | | | 0.80 | wire 4132, ovl 0, out 0, path 533 — N_PACKMID 8.8 mm, 16/16 channels ok — [history 0026](history/0026-pads-are-copper.md) |

## Routing

| # | change | stackup | rules | unrouted | min trace | below rule | unconn | vias | note |
| - | ------ | ------- | ----- | -------: | --------: | ---------: | -----: | ---: | ---- |
| 1 | | 4L, GND + VIN_SYS | 0.20 mm | — | — | — | — | — | never converged (~90–140) |
| 2 | | 4L, GND + VIN_SYS | 0.12 mm (loose) | 21 | — | — | — | — | converged, incomplete |
| 3 | | 4L, GND + VIN_SYS | 0.13 mm | 0 | 0.063 | 111 (rule 0.127) | 2 | 294 | QFN fanout thin |
| 4 | stackup fix | 4L, GND + 3 signal | 0.127 mm | 0 | 0.063 | 100 | 2 | 290 | [history 0013](history/0013-plane-layer-type-kills-vias.md) |
| 5 | SW1/SW2 fixed | 4L, GND + 3 signal | 0.127 mm | 1 | 0.095 | 78 | 4 | 288 | advanced PASS, standard FAIL |
| 6 | +radial QFN fanout | (as row 5) | 0.127 mm | — | 0.127 | 0 | — | — | rejected — 42 clearance + 14 shorts |
| 7 | try5-poured, not routed | F.Cu / In1 GND / In2 / B.Cu | — | — | — | — | 284 | 0 | [history 0015](history/0015-placement-cleanup.md) |
| 8 | fixed1 routed (re-poured) | F.Cu / In1 GND / In2 / B.Cu | 0.127 mm | 2 | 0.127 | 0 | 24 | 191 | 869 tracks, 2819 mm, 0 clearance; 20 of 24 unconn are pour islands — [history 0019](history/0019-board-fixup.md) |
| 9 | fixed3 routed | F.Cu / In1 GND / In2 / B.Cu | 0.127 mm | 8 | 0.127 | 0 | 20 | 221 | 1107 tracks, 3044 mm, 0 clearance; 13 pour islands + 7 GND/track — [history 0022](history/0022-board-fixup.md) |
| 10 | fixed5 routed (1 pass) | F.Cu / In1 GND / In2 / B.Cu | 0.127 mm | 47 | 0.127 | 0 | 47 | 159 | 800 tracks, 1939 mm, 0 clearance; 77 signal tracks on In1 (guard open, [0013](history/0013-plane-layer-type-kills-vias.md)); 30 dangling vias; taps outside the pours ([0027](history/0027-pour-taps.md)) |

## Power / gates

| # | change | power routing | min width | nets failing | ERC | DRC | unconn | standard | advanced | note |
| - | ------ | ------------- | --------: | -----------: | --: | --: | -----: | -------- | -------- | ---- |
| 1 | schematic only | — | — | — | 0 | n/a | n/a | — | — | |
| 2 | routed, pre-fix | | | | 0 | 102 | 2 | FAIL | PASS | |
| 3 | routed, SW1/SW2 fixed | | | | 0 | 79 | 4 | FAIL (78 fanout) | PASS | |
| 4 | routed, advanced accepted | 5 mil signal traces (F/In1/In2) | 0.095 | 10/10 | 0 | 1 (dangling via) | 4 | deferred | PASS | baseline — FAIL; [history 0012](history/0012-gnd-return-does-not-carry-20a.md) |
| 5 | routed + manual DRC fix | | | | 0 | 0 | 0 | FAIL (78 fanout) | PASS | |
| 6 | standard 5 mil rules | | | | 0 | 524 (446 clr + 78 w) | 0 | FAIL | PASS | |
| 7 | try5-poured (pours open) | pours on F.Cu | 0.000 | 11/11 | 0 | 52 | 284 | FAIL | — | channel N_AF 3.3/9.4 mm — [history 0015](history/0015-placement-cleanup.md) |
| 8 | derived board gets the DRU | pours on F.Cu | 0.000 | 11/11 | 0 | 52 (was 73) | 284 | FAIL | — | 21 false 5U1 pad-pad items gone — [history 0017](history/0017-drc-rules-do-not-follow-a-board-copy.md) |
| 9 | fixed1 routed | pours on F.Cu | 0.000 | 22/24 | 0 | 53 | 24 | FAIL | — | pad-limited [0019](history/0019-board-fixup.md) |
| 10 | fixed2 + Power56 FETs, terminal-aware gate | all high-current nets poured | — | 6/23 | 0 | 42 (silk) | 280 | PASS | — | high-current rails pass copper + terminal; [ADR-0015](decisions/0015-terminal-rating-in-power-gate.md) |
| 11 | fixed3 routed | pours on F.Cu | 0.127 | 5/23 | 0 | 59 | 20 | PASS | — | pour split: VIN_SYS, VBUS, SW2_OUT, N_CS; +3V3 0.13 mm ~0.9 A; N_PACKMID channel 1.5/7.5 — [ADR-0015](decisions/0015-terminal-rating-in-power-gate.md), [0022](history/0022-board-fixup.md) |
| 12 | charger input VBUS -> VIN_SYS | pours on F.Cu | — | 7/22 | 0 | 46 (silk) | 259 | — | — | 2R1/2U1 on VIN_SYS, VBUS net/pour gone; placement touch-up pending — [0022](history/0022-board-fixup.md) |
| 13 | fixed5 applied (unrouted) | pours on F.Cu | — | 6/22 (all unrouted signal nets) | 0 | 62 (silk) | 261 | — | — | high-current 16/16 PASS; 16/16 channels ok, N_PACKMID 2.4→8.8; N_CS/SW1_OUT fill 0.70/0.67 (pad necks) — [0026](history/0026-pads-are-copper.md) |
| 14 | fixed5 routed | pours on F.Cu | 0.127 | 2/22 (`N_VCAP` unrouted, `+3V3` 0.9 of 1.0 A) | 0 | 92 (silk 62, via dangling 30) | 47 | PASS | — | high-current 16/16 PASS; 16/16 channels ok; 5/5 sense loops no Kelvin (pour, 0 mm dedicated) |
| 15 | pour trunk/branches (fixed5, unrouted) | pours on F.Cu | — | 6/22 (all unrouted signal nets) | 0 | 62 (silk) | 262 | — | — | high-current 16/16 PASS; VIN_SYS `1Q1→3Q1→5Q1`, `2R1`/caps on branches; fill +12V_IN 5.48→6.01, N_AF 7.06→7.44, VIN_SYS 1.11→1.35, VOUT12 1.58→2.72; 0 clearance, 0 zone islands — [0027](history/0027-pour-taps.md) |

## Sense (Kelvin)

| # | change | shunts | worst distance | worst shared error | note |
| - | ------ | -----: | -------------: | -----------------: | ---- |
| 1 | `make sense` / `sense_report.py` | 5 | 73.2 mm (`2R2`) | 200 % (`4R1`) | fixed3, unrouted; sense-trace total — (unrouted), shunt-IC span 212.4 mm; 1 % budget, upper bound if the tap is not at the pad — [0025](history/0025-sense-gate.md) |
| 2 | fixed4 | 5 | 51.3 mm (`4R1`) | 168 % (`4R1`) | shunt-IC span 138.4 mm (was 212.4); `2R1` 13.1 mm (was 25.4); unrouted, still not Kelvin — [0025](history/0025-sense-gate.md) |
| 3 | fixed5 routed | 5 | 51.3 mm (`4R1`) | 168 % (`4R1`) | 0.0 mm dedicated sense tracks; all 5 loops `pour/zone`, no Kelvin — [0025](history/0025-sense-gate.md) |
