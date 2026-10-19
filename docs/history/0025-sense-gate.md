# 0025 – Current-sense loops were not gated

**What:** nothing checked the Kelvin taps. `hardware/sense_report.py` (and
`make sense`) now finds each shunt with a controller sense pair (`ACP/ACN`,
`SRP/SRN`, `CS/CSG`, `SENSE/VIN`), measures the shunt-to-IC distance, and checks
for a dedicated track from the shunt pad. A shared power-pour path is costed at
1 % of the shunt drop: `R_budget = 0.01 R_shunt`, with 2 oz copper.

**Numbers** (fixed3, unrouted; the error is the shared-pour upper bound):

| shunt | pair | distance | error if shared |
| --- | --- | ---: | ---: |
| `1R1` | `1U1` SENSE/VIN | 33.5 mm | 40 % |
| `2R1` | `2U1` ACP/ACN | 25.4 mm | 35 % |
| `2R2` | `2U1` SRP/SRN | 73.2 mm | 100 % |
| `4R1` | `4U1` SRP/SRN | 61.0 mm | 200 % |
| `5R3` | `5U1` CS/CSG | 19.2 mm | 63 % |

The 1 % budget is 0.84 mm for `1R1` (9.4 mm pour), 0.73 mm for the 5 mΩ pairs
(3.6 mm pour), and 0.30 mm for the 1 mΩ pairs (7.5 mm pour). The sense trace
itself carries µA, but the tap must be at the shunt pad.

**Status:** open — re-place each shunt close to its controller and route the
sense pair as dedicated tracks from the shunt pads; `make sense
SENSE_BOARD=build/layout/board-routed.kicad_pcb` gates it. The report also
prints the total routed sense-trace length (both sides; lower is better). That
is a metric only — it does not change the pass/fail.
