# TinyUPS – Component selection & BOM (first pass)

> Derived from the topology (ADR-0002/0003), the key silicon (ADR-0006) and the
> simulations (`sim/`). Values flagged **(verify)** must be confirmed against
> the vendor datasheet before the schematic is frozen. `TBD` = still open.
> This is the design-level BOM; the machine-readable BOM comes from the
> schematic via `make bom`.

## Design targets used for sizing

| Quantity | Value |
| --- | --- |
| Input | 12 V nominal, up to ~20 A (load + charge) |
| Output | 12.0 V, 13 A cont. / 17 A peak |
| Pack | 4S LFP, 11.2–13.8 V, 15 Ah |
| Charge | 5 A default, ~8 A max |
| Switching frequency (output / charger) | 300 kHz / 800 kHz |
| Ambient | 35 °C |

---

## 1. Input front-end (A) — LM5069

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| F1 | Fuse 25 A | **ATO/ATC blade, 25 A, 32 V**, soldered | backup to the eFuse. `Fuse:Fuse_Blade_ATO_directSolder` — the blade family is 1–40 A; a 1206 (1.25 mm terminals) or a Nano2 (1–5 A or 20 A) cannot do 25 A in this path. Soldered = not field-replaceable (acceptable: the LM5069 eFuse is the working protection). **(verify)** order PN (Littelfuse 257 / Bussmann ATC class) |
| D1 | TVS SMBJ15A | standoff 15 V, clamp ~24 V | input transient clamp **(verify)** |
| Q1 | **NTMFS5C410N** (40 V) | 0.92 mΩ, 300 A (T_C); 46 A / 32 A at T_A = 25 / 100 °C | hot-swap pass FET (LM5069). Power56 (SO-8FL), `Package_SON:VSONP-8-1EP_5x6_P1.27mm` — [datasheet](https://www.onsemi.com/download/data-sheet/pdf/ntmfs5c410n-d.pdf). **Pin map:** the Power56 land is S=1/G=2/D=3; use `Q_NMOS_SGD` (or a GDS-numbered land). The current TO-252 board pairs `Q_NMOS_GSD` with a GDS land, so drain/source are reversed — fix before syncing ([history 0020](history/0020-fet-pin-mapping.md)) |
| R_sns1 | **2.2 mΩ** | 1 %, ≥ 2 W | LM5069 current limit = 55 mV / R_S ≈ **25 A** (datasheet). **Vishay `WSR22L200FEA`** (WSR2, 2 W, 4527, ±1 %, 0.88 W here) — [datasheet](https://www.vishay.com/docs/30101/wsr.pdf); its recommended land (a = 3.94, b = 5.84 mm) is `R_Shunt_Vishay_WSR2_WSR3` |
| C_in1 | 2 × 10 µF / 25 V | X7R ceramic | HF decoupling |
| C_in2 | 100 µF / 25 V | low-ESR | input bulk |

## 2. Priority power path

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q2 | **NTMFS5C410N** (40 V) | 0.92 mΩ, ≥ 30 A | pack ideal-diode FET (LM74700); same package/pin note as Q1 |
| C_hold | 2 × 470 µF / 25 V + 10 µF | low-ESR polymer + ceramic | converter-input hold-up; sim needs ~1000 µF for a 50 µs handover |
| U2 | Comparator + ref | e.g. TLV3012 | input-valid detect (~10.5 V) → gates pack EN; use LM5069 PGOOD where possible **(verify)** |

## 3. Output buck-boost (C) — LM5176, 12 V / 15 A

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q3–Q6 | 4 × **NTMFS5C430N** (40 V) | 1.7 mΩ, 185 A (T_C); 35 A / 25 A at T_A = 25 / 100 °C | output buck-boost (LM5176). Power56, same land/pin note as Q1 — [datasheet](https://www.onsemi.com/pdf/datasheet/ntmfs5c430-d.pdf) |
| L1 | **1.0 µH** | Isat ≥ 22 A, DCR ≤ 3 mΩ | LM5176 Eq. 13/14 → 0.87 µH (buck) / 0.55 µH (boost) at 300 kHz |
| C_out | 2 × 220 µF / 25 V + 10 µF | low-ESR polymer + ceramic | ripple ≤ 100 mVpp |
| R_sns2 | 1 mΩ | 1 %, ≥ 2 W | in series with the low-side FETs (valley current sense); ~20 A limit. Vishay `WSR21L000FEA` (2 W, 0.29 W here) |
| R_freq | **≈ 27 kΩ** (300 kHz) | 1 % | LM5176 Eq. 5; fsw range 100–600 kHz |
| R_fb1/R_fb2 | set Vout = 12.0 V | 1 % | feedback divider |

## 4. Charger — BQ25720, 4S LFP CC/CV

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q7–Q10 | 4 × **NTMFS4C01N** (30 V) | 0.9 mΩ, 303 A (T_C); 47 A at T_A = 25 °C | charger buck-boost (BQ25720). Power56, same land/pin note as Q1 — [datasheet](https://www.onsemi.com/pdf/datasheet/ntmfs4c01n-d.pdf) |
| L2 | 2.2 µH | Isat ≥ 15 A | **confirmed** by datasheet (RAC 5 mΩ, RSR 5 mΩ, 2.2 µH, 800 kHz) |
| R_sns_in (RAC) | **5 mΩ** | 1 %, ≥ 1 W | input current limit (≤ 10 A) — datasheet example. Vishay `WSR25L000FEA` |
| R_sns_bat (RSR) | **5 mΩ** | 1 %, ≥ 1 W | charge current up to 16.2 A (used ≤ ~8 A) — datasheet example. Vishay `WSR25L000FEA` |
| NTC1 | 10 kΩ B = 3435 | | battery JEITA sensing |
| C caps | per datasheet | | input/output/battery decoupling |

## 5. Battery AFE — BQ76942

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| R_sns_pack | 1 mΩ | 1 %, ≥ 1 W, low TCR | coulomb counter (0.29 W @ 17 A); e.g. Vishay WSLP2726 |
| Q_chg, Q_dsg | 2 × **NTMFS5C410N** (40 V) | 0.92 mΩ, ≥ 30 A | **high-side** protection FETs (common source), gate driven by the AFE charge pump (CP1); same package/pin note as Q1 |
| J6 | Pack terminal | 2-pin, ≥ 30 A | PACK+ / PACK−, high-current harness |
| J7 | Cell-sense header | 5-pin 2.54 mm | CELL0…CELL4 Kelvin taps |
| R_bal | 100 Ω / cell | | passive balance ≈ 30 mA; keep total die power within limit (design choice) |
| R_cell, C_cell | 100 Ω + 100 nF / cell | | cell input RC filter |
| NTC2, NTC3 | 10 kΩ B = 3435 | | cell temperature sensing |
| C_pack, C_cp | per datasheet | | charge-pump / supply caps |

## 6. MCU, USB, fan, UI

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| U3 | RP2040 | QFN-56 | telemetry / control |
| U4 | W25Q128 | 16 MB QSPI flash | firmware |
| Y1 | 12 MHz | crystal | RP2040 clock |
| U5 | 3.3 V buck | low Iq | e.g. TPS62172 / MP2315 **(verify)** |
| J_usb | USB-C receptacle | 2 × 5.1 kΩ CC | data only |
| J_fan | 4-pin header | 12 V / GND / PWM / TACH | PWM from RP2040; TACH pull-up 10 kΩ to 3V3 |
| — | Fan 80 mm | 4-pin PWM | e.g. Noctua NF-A8 PWM |
| LED1–4 | mains / battery / charge / fault | + series resistors | |
| SW1 | reset button | | |
| J_swd | SWD header | 3V3 / GND / SWDIO / SWCLK | RP2040 programming |

## 7. Connectors & harness

| Ref | Part | Notes |
| --- | --- | --- |
| J_in | XT60, 2-pin | +12 V / GND (IF-1) |
| J_out | XT30, 2-pin | +12 V / GND pigtail |
| — | 5.5 × 2.5 mm barrel plug + cable | XT30 → picoPSU adapter (IF-3) |
| — | Nickel strip + pack harness | 4S1P weld pack, ~12–14 AWG leads |

## 8. Derived / cross-checks

- **Hold-up cap:** sim shows ~187 mV dip with 1000 µF and a 50 µs handover
  (`sim/power-path.cir`) → C_hold ≈ 2 × 470 µF + ceramics.
- **Output ripple/step:** sim (`sim/output-stage.cir`) → ≤ 1.1 % deviation;
  final values from the LM5176 design.
- **Runtime:** ~3.3 h at 50 W (`sim/pack-runtime.cir`); refine with measured
  cell OCV/DCR (ADR-0007).
- **Charge:** 5 A CC, CV to 13.8 V (`sim/charger-cccv.cir`).

## 9. Open / verify

- **Verified from the vendor datasheets** (fetched and text-extracted):
  - LM5069 current limit = **55 mV / R_S** → 2.2 mΩ ≈ 25 A.
  - LM5176 fsw set by R_T (Eq. 5, 100–600 kHz) and inductor by Eq. 13/14.
  - BQ25720 example: **RAC = RSR = 5 mΩ, L = 2.2 µH at 800 kHz**.
  - BQ76942 passive balancing via the external cell resistance (target ~30 mA).
- **FETs selected** (datasheet terminals in `power_spec.PART_TERMINAL_A`):
  Q1/Q2/Q_chg/Q_dsg = **NTMFS5C410N** (40 V, 0.92 mΩ); Q3–Q6 =
  **NTMFS5C430N** (40 V, 1.7 mΩ); Q7–Q10 = **NTMFS4C01N** (30 V, 0.9 mΩ),
  all Power56 5×6. Board refs: Q1=`1Q1`, Q2=`3Q1`, Q3–Q6=`5Q1`–`5Q4`,
  Q7–Q10=`2Q1`–`2Q4`, Q_chg/Q_dsg=`4Q1`/`4Q2`.
- **Pin map / package:** the Power56 land is S=1/G=2/D=3; use `Q_NMOS_SGD`
  (or a custom GDS-numbered land). The current TO-252 board pairs
  `Q_NMOS_GSD` (S=2/D=3) with a GDS land (D=2/S=3), so every FET's drain and
  source are reversed — the BMS pair is common-drain, not common-source.
  Fix the symbols and the pad nets before syncing the Power56 footprints
  ([history 0020](history/0020-fet-pin-mapping.md)).
- **Terminal-aware power gate:** `make power` sizes copper with IPC-2221 and
  component terminals from the datasheet (`PART_TERMINAL_A`); a missing rating
  is printed as `unrated`
  ([ADR-0015](decisions/0015-terminal-rating-in-power-gate.md)).
- Remaining **(verify)**: exact orderable PNs for the inductors, TVS, NTCs and
  connectors (the FET, fuse and shunt parts are above).
- Component temperature limits and the fan's "within 5 °C" reference (FR-16).
- Chassis bonding detail; barrel-adapter cable current rating.
- Simulations are behavioural; confirm the LM5069/LM5176/BQ25720 loops on
  hardware (test plan Phases 2–5).
