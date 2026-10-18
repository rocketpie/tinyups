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
| Q1 | N-FET, 40 V | RDS(on) ≤ 3 mΩ, ≥ 30 A | hot-swap pass FET (e.g. onsemi NVMFS5C410N) **(verify)** |
| R_sns1 | **2.2 mΩ** | 1 %, ≥ 2 W | LM5069 current limit = 55 mV / R_S ≈ **25 A** (datasheet). **Vishay `WSR22L200FEA`** (WSR2, 2 W, 4527, ±1 %, 0.88 W here) — [datasheet](https://www.vishay.com/docs/30101/wsr.pdf); its recommended land (a = 3.94, b = 5.84 mm) is `R_Shunt_Vishay_WSR2_WSR3` |
| C_in1 | 2 × 10 µF / 25 V | X7R ceramic | HF decoupling |
| C_in2 | 100 µF / 25 V | low-ESR | input bulk |

## 2. Priority power path

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q2 | N-FET, 40 V | RDS(on) ≤ 2 mΩ, ≥ 30 A | pack ideal-diode FET (LM74700) |
| C_hold | 2 × 470 µF / 25 V + 10 µF | low-ESR polymer + ceramic | converter-input hold-up; sim needs ~1000 µF for a 50 µs handover |
| U2 | Comparator + ref | e.g. TLV3012 | input-valid detect (~10.5 V) → gates pack EN; use LM5069 PGOOD where possible **(verify)** |

## 3. Output buck-boost (C) — LM5176, 12 V / 15 A

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q3–Q6 | 4 × N-FET, 40 V | RDS(on) ≤ 2 mΩ, Qg moderate | e.g. onsemi NTMFS5C430N **(verify)** |
| L1 | **1.0 µH** | Isat ≥ 22 A, DCR ≤ 3 mΩ | LM5176 Eq. 13/14 → 0.87 µH (buck) / 0.55 µH (boost) at 300 kHz |
| C_out | 2 × 220 µF / 25 V + 10 µF | low-ESR polymer + ceramic | ripple ≤ 100 mVpp |
| R_sns2 | 1 mΩ | 1 %, ≥ 2 W | in series with the low-side FETs (valley current sense); ~20 A limit. Vishay `WSR21L000FEA` (2 W, 0.29 W here) |
| R_freq | **≈ 27 kΩ** (300 kHz) | 1 % | LM5176 Eq. 5; fsw range 100–600 kHz |
| R_fb1/R_fb2 | set Vout = 12.0 V | 1 % | feedback divider |

## 4. Charger — BQ25720, 4S LFP CC/CV

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| Q7–Q10 | 4 × N-FET, 30 V | RDS(on) ≤ 4 mΩ, ≥ 15 A | buck-boost stage **(verify)** |
| L2 | 2.2 µH | Isat ≥ 15 A | **confirmed** by datasheet (RAC 5 mΩ, RSR 5 mΩ, 2.2 µH, 800 kHz) |
| R_sns_in (RAC) | **5 mΩ** | 1 %, ≥ 1 W | input current limit (≤ 10 A) — datasheet example. Vishay `WSR25L000FEA` |
| R_sns_bat (RSR) | **5 mΩ** | 1 %, ≥ 1 W | charge current up to 16.2 A (used ≤ ~8 A) — datasheet example. Vishay `WSR25L000FEA` |
| NTC1 | 10 kΩ B = 3435 | | battery JEITA sensing |
| C caps | per datasheet | | input/output/battery decoupling |

## 5. Battery AFE — BQ76942

| Ref | Value / part | Spec | Notes |
| --- | --- | --- | --- |
| R_sns_pack | 1 mΩ | 1 %, ≥ 1 W, low TCR | coulomb counter (0.29 W @ 17 A); e.g. Vishay WSLP2726 |
| Q_chg, Q_dsg | 2 × N-FET, 40 V | RDS(on) ≤ 2 mΩ, ≥ 30 A | **high-side** protection FETs (common source), gate driven by the AFE charge pump (CP1) **(verify)** |
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
- **Terminals, not silicon, limit the power path** (docs/history/0007): a
  TO-252 source lead, a 1206 fuse and a 2512 shunt are ~4.5 A parts at 2 oz.
  The fuse and the five milliohm shunts (`R_sns1`, `2R1`, `2R2`, `4R1`, `5R3`)
  now use wide-terminal land patterns (`WSR2` 4527, pinned as
  `WSR22L200FEA` / `WSR25L000FEA` / `WSR21L000FEA`); the **FET packages are
  still open**.
- Remaining **(verify)**: exact orderable PNs for the FETs, inductors, sense
  resistors, TVS, NTCs and connectors.
- Component temperature limits and the fan's "within 5 °C" reference (FR-16).
- Chassis bonding detail; barrel-adapter cable current rating.
- Simulations are behavioural; confirm the LM5069/LM5176/BQ25720 loops on
  hardware (test plan Phases 2–5).
