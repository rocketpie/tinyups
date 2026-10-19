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
| 12 | fixed1 hand-tuned (UI) | 3672 | 16501 | | | | | | 0.76 | wire 4295, ovl 0, out 0, axisR 0.76, path 574 — [history 0019](history/0019-place-apply-stale-pours.md) |

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
| 8 | fixed1 routed (re-poured) | F.Cu / In1 GND / In2 / B.Cu | 0.127 mm | 2 | 0.127 | 0 | 24 | 191 | 869 tracks, 2819 mm, 0 clearance; 20 of 24 unconn are pour islands — [history 0019](history/0019-place-apply-stale-pours.md) |

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
| 9 | fixed1 routed | pours on F.Cu | 0.000 | 22/24 | 0 | 53 | 24 | FAIL | — | channels +12V_IN 6.4, N_AF 5.2, VIN_LM 4.0 / 9.4 mm SHORT; pad-limited — [0007](history/0007-power-pads-limit.md), [0019](history/0019-place-apply-stale-pours.md) |
