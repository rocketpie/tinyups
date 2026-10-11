# 0006 – Key component selection

- Status: accepted (primary parts; alternatives noted)

## Context

The topology is fixed (ADR-0002, ADR-0003). This ADR records the concrete
silicon choices for the input, power path, charger, output, AFE and MCU, with
vendor sources. Final passives (FETs, inductors, sense resistors, TVS) are
derived from these and are still open.

## Selection

| Block | Part | Vendor | Why / key specs | Source |
| --- | --- | --- | --- | --- |
| Input protection / front-end | **LM5069** | TI | 9–80 V hot-swap, inrush limit, adjustable UVLO/OVLO, current limit + circuit breaker, POWER GOOD. Iq ≈ 1.3 mA. | ti.com/product/LM5069 |
| Priority power path | **LM74700-Q1** (pack ideal diode) + LM5069 PG / comparator for priority | TI | 3.2–65 V ideal-diode controller, external N-FET, 20 mV drop, reverse-current block < 0.75 µs, EN pin, 80 µA Iq. | ti.com/product/LM74700-Q1 |
| Priority power path (alternative) | LTC4421 | ADI | Purpose-built prioritized (2-input) PowerPath controller. *Vendor page did not load here — datasheet to verify before use.* | analog.com (TBD) |
| Charger | **BQ25720** | TI | 1–4 cell, **LiFePO₄**, NVDC buck-boost, CC up to 16.2 A (5 mΩ sense), input-current regulation (IINDPM) + input OVP, JEITA battery-temperature profile, SMBus. 3.5–26 V. | ti.com/product/BQ25720 |
| Output converter | **LM5176** | TI | 4-switch synchronous buck-boost, 4.2–55 V, 2 A gate drivers, current limit, UVLO, OVP, spread spectrum. | ti.com/product/LM5176 |
| Output converter (newer option) | LM51772 / LM51770 | TI | Same family with I²C / 78 V bidirectional. | ti.com/product/LM5176 |
| Battery AFE / BMS | **BQ76942** | TI | 3–10S, **LiFePO₄**, high-side NFET drivers, 2 ADCs, coulomb counter (< 1 µV offset), cell V < 10 mV, autonomous balancing, dual LDO, 400 kHz I²C/SPI/HDQ. Sleep 24–41 µA, DEEPSLEEP 9–10 µA, SHUTDOWN 1 µA. | ti.com/product/BQ76942 |
| MCU | **RP2040** + QSPI flash | Raspberry Pi | Native USB FS (composite CDC + HID-PDC), ample CPU/ADC. | raspberrypi.com |
| Reference designs | PMP21278 (300 W 12 V/25 A buck-boost, LM5176), PMP22419 (140 W charger, BQ25720), PMP22125 (battery-backup switch + charger + monitor) | TI | Starting points for layout and sizing. | ti.com |

## Consequences

- The whole design is buildable from **TI + Raspberry Pi** parts, all with
  public datasheets (except the ADI alternative).
- **Charge-current ceiling:** the BQ25720 input-current limit tops out at
  ~10 A, so charging from the 12 V input realistically caps at **~8 A** into
  the pack, not the cell's 1C (15 A). The 5 A default is unaffected; a 15 A
  ceiling would require a different (external-FET) charger controller.
- **Priority path** is implemented with an ideal diode on the pack branch
  whose enable is released only when the input is invalid; the input branch is
  the default source. The exact handover timing must be validated (Phase 5)
  and the converter input hold-up sized accordingly.
- Balancing current is set by the BQ76942 external resistors (target 20–50 mA,
  TBD).
- Related requirements: FR-1, FR-4, FR-5, FR-7, FR-11, IF-1, IF-2, IF-3,
  NFR-1, NFR-2.
