# Simulations

ngspice netlists validating the power architecture **before layout**. Run all
of them with `make sim`; logs land next to each netlist (`*.log`, git-ignored).

These are first-order behavioural models — they check that the requirements are
plausible and size the first passives. They are not transistor-level models of
the chosen ICs.

## `power-path.cir` — input priority & seamless transfer (FR-1, FR-2)

Source-selection node feeding the 12 V buck-boost. The pack is modelled
**full (13.8 V)** on purpose: a plain ideal-diode OR would let the higher pack
win. The input is removed abruptly at t = 1 ms under a ~50 W load.

| Measurement | Result | Meaning |
| --- | --- | --- |
| `Vout_nom` | 11.58 V | converter input on mains |
| `dip` | **187 mV** | sag at handover (limit 5 % ≈ 580 mV) |
| `Ipk_mains` | ~0 A | **pack does not discharge on mains** (FR-1) |
| `Ipk_backup` | 4.17 A | pack carries the load after transfer (FR-2) |

Conclusion: with a ~1000 µF hold-up cap and a ~50 µs handover delay the
transfer stays well inside spec. Model gate/handover timing against the real
comparator and confirm on hardware (test-plan Phase 5).

## `output-stage.cir` — 12 V regulation & load step (IF-3)

Behavioural regulated source (10 mΩ output impedance, 470 µF).

| Measurement | Result |
| --- | --- |
| `Vout_50W` | 11.96 V (−0.35 %) |
| `Vout_160W` | 11.87 V (−1.1 %) |
| step deviation | ~90 mV |

Conclusion: 12.0 V ±3 % is achievable across 50–160 W; final numbers depend on
the LM5176 design.

## `charger-cccv.cir` — CC/CV charge (FR-4)

Battery lumped as a capacitor (~13.5 Ah over 12.0–13.8 V).

| Measurement | Result |
| --- | --- |
| `Ichg_start` | **5.0 A** (CC phase) |
| `time_to_13V` | 4860 s ≈ 81 min |
| `Vbat_end` | 13.76 V (CV taper) |

## `pack-runtime.cir` — backup time (FR, runtime target)

4S pack at 50 W constant power, from full to the 3.0 V/cell (12.0 V) cutoff.

| Measurement | Result |
| --- | --- |
| `time_to_cutoff` | **11 925 s ≈ 3.3 h** |

Conclusion: the ≥ 30 min target is met with large margin. The linear
lumped model overestimates available energy slightly; refine with the cell
datasheet (OCV/SOC curve, DCR, temperature).
