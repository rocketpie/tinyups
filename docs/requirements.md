# TinyUPS – Design Goals & Requirements

> Status: **Draft, based on a design interview** (see "Decision log" below).
> This document supersedes the earlier 5 V / Raspberry-Pi-HAT / 1S-Li-Ion
> concept. It is the top-level requirement source: architecture, layout and the
> test plan must all trace back to the IDs defined here.
> Values marked `TBD` are still open and listed in §8.

## 1. Purpose

TinyUPS is a compact DC uninterruptible power supply for a PC-class machine
that is fed by an external 12 V adapter and a **picoPSU** DC-ATX converter. It
behaves like a laptop battery: while mains is present the load runs from the
adapter and the pack recharges; if mains disappears the load keeps running from
the pack with no interruption; when mains returns the pack recharges. The
module reports its state to the host and signals when the host should shut
down cleanly.

## 2. System context & interfaces

The module has four external interfaces:

| ID | Interface | Description |
| --- | --- | --- |
| **A** | External 12 V input | 12 V / 20 A (240 W) AC-DC adapter, XT connector. |
| **B** | Battery | Internal 4S1P LiFePO₄ pack, managed by an on-board AFE. |
| **C** | 12 V output | Fixed pigtail to the picoPSU-160-XT 12 V input. |
| **D** | Host link | USB-C (data only): telemetry + shutdown signalling. |

```
 A (12 V in, XT60) ─┐
                    ├─▶ [ priority power-path ] ─▶ [ 12 V buck-boost ] ─▶ C (picoPSU)
 B (4S LFP pack) ───┘                                   ▲
        ▲ AFE sense                                    │
        └──────────── [ RP2040 ] ────── D (USB-C: CDC + HID-PDC)
                        │
                        └── LEDs + reset button
```

## 3. Fixed design parameters (confirmed)

| Parameter | Value | Notes |
| --- | --- | --- |
| Cells | **4S1P LiFePO₄, Topband 33138-HE, 3.2 V / 15 Ah** each | 33 × 140 mm, 292 g. Datasheet to be filed under `hardware/libs` / `docs/`. |
| Cell limits | Charge **1C (15 A)**, discharge **2C (30 A)** | Pack peak (17 A ≈ 1.1C) and continuous (15 A ≈ 1C) are well inside. |
| Cell temperatures | Charge **0–45 °C**, discharge **−20–60 °C** | Drives the charge-inhibit window. |
| Cell life | **> 2000 cycles** | Favours 3.45 V/cell charge limit. |
| Pack | **12.8 V nominal, 15 Ah, ~192 Wh** | Usable energy to cutoff ≈ 170 Wh. |
| Max charge voltage | **3.45 V/cell → 13.8 V pack** | Prioritises cycle life. |
| System cutoff | **3.0 V/cell → 12.0 V pack** | UPS force-off, still above picoPSU floor. |
| AFE hard cutoff | 2.8 V/cell (11.2 V), 2.5 V/cell absolute | Protection layer. |
| Output | **12.0 V, always regulated** | Always inside picoPSU 10.8–13.2 V window. |
| Output load | **~50 W typical / 160 W peak** | Per server. |
| External supply | 12 V / 20 A, XT connector | Runs load and charges concurrently. |
| Runtime target | **≥ 30 min at 50 W** | Design delivers ≈ 3 h at 50 W typical. |
| Telemetry MCU | **RP2040**, USB Full-Speed | Composite CDC + HID-PDC. |
| SOC method | Coulomb counting + OCV correction | |
| Mechanical | Module (pack + PCB) in a **standard ATX bay (150×86×140 mm)** | 4-layer PCB. |
| Connectors | **XT60 input**, fixed 12 V output pigtail, spot-welded pack + harness | |
| Prototype | **JLCPCB, 5 pcs, EMC-ready** | Rules in `.kicad_dru`. |

### 3.1 Key components (see ADR-0006 and `docs/datasheets/`)

| Block | Part |
| --- | --- |
| Input front-end (inrush, UVLO/OVLO, current limit) | TI LM5069 |
| Priority power path | TI LM74700-Q1 ideal diode (pack branch) + input-valid gating |
| Charger (buck-boost CC/CV) | TI BQ25720 (LiFePO₄, IINDPM input-current regulation) |
| Output converter (buck-boost, 12 V regulated) | TI LM5176 |
| Battery AFE / BMS | TI BQ76942 (3–10S) + protection FETs |
| MCU | RP2040 + QSPI flash |
| Sources / datasheets | `docs/datasheets/` |

## 4. Functional requirements

- **FR-1 Priority power path.** While the input is valid, the load is supplied
  from the input and the pack does not discharge. Input has priority even
  though a charged pack (~13.8 V) is *higher* than 12 V.
- **FR-2 Uninterruptible transfer.** On loss of input the pack takes over with
  no host reset: output stays within the §4.3 window continuously.
- **FR-3 Regulated output.** The output is held at 12.0 V ±3 % across the full
  pack range (11.2–13.8 V) and over the full load range.
- **FR-4 Charging.** Whenever the input is valid, the pack is charged with a
  CC/CV profile to 13.8 V, within the allowed temperature window, and the
  charge terminates cleanly.
- **FR-5 Simultaneous run & charge.** The load runs from the input while the
  pack charges; the adapter's 20 A budget covers both. Charge current is
  limited so that input current stays within the adapter rating — the charger
  throttles back as load rises (input power-budget management, BQ25720 IINDPM).
  Default charge current 5 A (0.33C); the achievable maximum is ~8 A because
  the charger's input-current limit caps at ~10 A at 12 V, below the cell's
  1C (15 A) rating.
- **FR-6 SOC estimation.** State of charge is estimated by coulomb counting
  with open-circuit-voltage correction, and is reported with defined accuracy.
- **FR-7 Telemetry.** Pack voltage, current, per-cell voltages, temperatures,
  SOC, estimated remaining runtime, charge state and status flags are exposed
  over USB (both CDC and HID-PDC views).
- **FR-8 Low-battery warning.** At ≤ 30 % SOC (and no less than the §4.3 time
  needed to shut down) the module signals the host to shut down.
- **FR-9 Force-off.** At 3.0 V/cell the UPS forces the host off / removes the
  output to protect the pack.
- **FR-10 Recovery.** After a force-off the host stays off; there is no
  automatic restart. When input returns the UPS re-enables the 12 V output so
  the host's own power button works again.
- **FR-11 Protection.** The module protects against cell over-voltage,
  under-voltage, charge/discharge over-current, short circuit, over-temperature,
  reverse input polarity, and input over-voltage/transients, without user action.
- **FR-12 Balancing.** The pack is kept balanced (passive balancing via the AFE).
- **FR-13 Indication & control.** LEDs show mains / battery / charge / fault,
  and a reset button is provided.
- **FR-14 Deep-discharge recovery.** A deeply discharged pack is pre-charged
  before normal charging / output enable resumes.
- **FR-15 USB roles.** USB-C carries data only (no PD/USB power role); the
  module is not powered from USB.

## 5. Non-functional requirements

- **NFR-1 Efficiency.** Output converter ≥ 90 % and charger ≥ 90 % at typical
  load (`TBD` exact measurement points).
- **NFR-2 Self-consumption.** ≤ 1 mA drawn from the pack when idle with no
  input, so a stored module is not drained.
- **NFR-3 Thermal.** Fanless; heat spread into the PCB/enclosure; component
  temperatures below `TBD` °C at 40 °C ambient (operating range 0–40 °C).
- **NFR-4 Mechanical.** Pack + PCB + connectors fit a standard ATX bay
  (150×86×140 mm) including creepage/clearance and pack retention.
- **NFR-5 EMC.** Designed for EMC/CE but no formal test for the prototype.
- **NFR-6 Reproducibility.** Schematic, layout, BOM, simulations and the test
  plan are versioned and reproducible headlessly (`make` / KiBot / ngspice).
- **NFR-7 Safety.** Fusing on pack and input, insulated pack, defined
  creepage/clearance, temperature monitoring on the cells.
- **NFR-8 Cost.** Prototype unit cost `TBD`.
- **NFR-9 Manufacturing.** JLCPCB, 5 boards, ≥ 4 layers; DRU aligned to the
  fab's capabilities.
- **NFR-10 Serviceability.** Pack is spot-welded with a lead harness; the board
  is replaceable and re-flashable over USB (RP2040 UF2).
- **NFR-11 Measurement accuracy.** Voltage/current/SOC accuracy `TBD` (see test
  plan §Phase 7).

## 6. Interface requirements

- **IF-1 (A, input).** XT60 input, 12 V nominal; operating window 11.0–13.5 V;
  over-voltage protection above `TBD` V, transient survival to `TBD` V; reverse
  and short-circuit protected; fused.
- **IF-2 (B, battery).** Internal 4S1P LFP pack wired to internal terminals;
  pack-level AFE **TI BQ76942** with per-cell sensing, current sense and
  NTC(s); passive balancing; charge/discharge FETs on the PCB.
- **IF-3 (C, output).** Fixed pigtail (≈14 AWG) delivering 12 V/GND; continuous
  ≥ 15 A (180 W), peak ≥ 17 A (200 W) for ≤ 10 s; ripple ≤ 100 mVpp; load-step
  deviation ≤ 5 % recovering in < 1 ms.
- **IF-4 (D, host link).** USB-C (Full-Speed, data only) presenting a composite
  device: **CDC-ACM** (line-framed protocol for custom tooling) and **USB HID
  Power Device Class** (so the OS / Network UPS Tools `usbhid-ups` sees a native
  UPS). The HID-PDC path provides low-battery signalling that `upsmon` turns
  into a clean host shutdown with no custom daemon.
- **IF-5 (enclosure).** Standard ATX bay; XT60 input on the panel; output
  pigtail with strain relief; LED/button access.

## 7. Constraints

- EDA: KiCad 9 + `kicad-cli`/KiBot, headless, driven through the `Makefile`
  (`docs/decisions/0001-tooling-and-workflow.md`).
- Simulation: ngspice for the power path, converter and protections.
- Everything in git; checks reproducible in CI.

## 8. Open items (TBD)

1. ~~**Exact cell**~~ **Resolved:** Topband 33138-HE, 3.2 V / 15 Ah LiFePO₄,
   33 × 140 mm, 1C charge / 2C discharge, 0–45 °C charge, −20–60 °C discharge,
   > 2000 cycles. *Still to do:* file the manufacturer datasheet in the repo.
2. ~~**AFE part**~~ **Resolved:** TI BQ76942 (3–10S, LiFePO₄). Balancing
   current still `TBD` (target 20–50 mA). ADR-0006.
3. ~~**Buck-boost output controller**~~ **Resolved:** TI LM5176. ~~**Charger**~~
   **Resolved:** TI BQ25720. ADR-0006.
4. **Charger current ceiling:** default 5 A confirmed, but the BQ25720's ~10 A
   input-current limit caps charging at **~8 A** (not the 1C/15 A the cell
   allows). Decide whether ~8 A is acceptable or a different charger is needed.
   Termination rule still `TBD`.
5. Exact ATX bay dimensions and tolerance in the particular chassis.
6. Component temperature limit and efficiency/accuracy measurement points.
7. Firmware stack (Pico SDK vs PlatformIO) and the on-wire CDC protocol framing.
8. Output ripple and transfer-transient limits confirmation.
9. Whether to add a discrete shutdown/FSD line as a hardware backup to the USB
   signalling.
10. Prototype cost target and USB connector type on the enclosure.
11. Derive the passives: protection/ideal-diode FETs, inductors, sense
    resistors (5 mΩ charger sense), TVS, NTCs. Verify the ADI LTC4421
    alternative if a purpose-built priority controller is preferred.
12. **Cell datasheet file/link** still missing (see `docs/datasheets/`).

## 9. Decision log

| Decision | Choice | Rationale |
| --- | --- | --- |
| Cell configuration | 4S LFP | Voltage overlaps the picoPSU window; only one conversion needed on mains. |
| Output stage | Always-regulated 12 V buck-boost | Full pack range usable; output always in spec. |
| Power path | Input-priority mux (not plain ideal-diode OR) | A charged pack is above 12 V, so OR would let the pack win. ADR-0002. |
| Charger | Buck-boost CC/CV | Pack can be both below and above 12 V during charging. |
| BMS | On-board AFE + FETs | Per-cell telemetry, protection, balancing. ADR-0003. |
| Host link | USB-C composite CDC + HID-PDC | Simple tooling *and* native OS/NUT compatibility. ADR-0004. |
| SOC | Coulomb counting + OCV | Accurate on the flat LFP curve. |
| Mechanical | Module in an ATX bay, welded pack | Self-contained drop-in for the PSU bay. ADR-0005. |
| Docs language | English | Project decision. |
