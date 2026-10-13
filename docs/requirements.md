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
| **A** | External 12 V input | Panel **XT60** (2-pin, +12 V / GND) at the ATX AC-inlet location; 12 V / 20 A AC-DC adapter. |
| **B** | Battery | Internal 4S1P LiFePO₄ pack (spot-welded nickel strips + harness), managed by an on-board AFE. |
| **C** | 12 V output | **XT30** pigtail (2-pin) → short adapter cable to the picoPSU's 5.5 × 2.5 mm barrel jack. |
| **D** | Host link | USB-C (data only): telemetry + shutdown signalling. |

```
 A (12 V in, XT60) ─┐
                    ├─▶ [ priority power-path ] ─▶ [ 12 V buck-boost ] ─▶ C (XT30 → barrel → picoPSU)
 B (4S LFP pack) ───┘                                   ▲
        ▲ AFE sense                                    │
        └──────────── [ RP2040 ] ────── D (USB-C: CDC + HID-PDC)
                        │
                        └── LEDs + reset button + 80 mm fan header
```

## 3. Fixed design parameters (confirmed)

| Parameter | Value | Notes |
| --- | --- | --- |
| Cells | **4S1P LiFePO₄, Topband 33138-HE, 3.2 V / 15 Ah** each | 33 × 140 mm, 292 g, round, **spot-weldable**; no datasheet — sourced from vendor spec + measurement (ADR-0007). |
| Cell limits | Charge **1C (15 A)**, discharge **2C (30 A)** | Pack peak (17 A ≈ 1.1C) and continuous (15 A ≈ 1C) are well inside. |
| Cell temperatures | Charge **0–45 °C**, discharge **−20–60 °C** | Drives the charge-inhibit window. |
| Cell life | **> 2000 cycles** | Favours 3.45 V/cell charge limit. |
| Pack | **12.8 V nominal, 15 Ah, ~192 Wh** | Usable energy to cutoff ≈ 170 Wh. |
| Max charge voltage | **3.45 V/cell → 13.8 V pack** | Prioritises cycle life. |
| System cutoff | **3.0 V/cell → 12.0 V pack** | UPS force-off, still above picoPSU floor. |
| AFE hard cutoff | 2.8 V/cell (11.2 V), 2.5 V/cell absolute | Protection layer. |
| Output | **12.0 V, always regulated** | Always inside picoPSU 10.8–13.2 V window. |
| Output load | **~50 W typical / 160 W peak** | Per server. |
| External supply | 12 V / 20 A, XT60 | Runs load and charges concurrently. |
| Runtime target | **≥ 30 min at 50 W** | Design delivers ≈ 3 h at 50 W typical. |
| Telemetry MCU | **RP2040**, USB Full-Speed | Composite CDC + HID-PDC. |
| SOC method | Coulomb counting + OCV correction | |
| Mechanical | Module (pack + PCB) in a **standard ATX bay (150×86×140 mm)** | 4-layer PCB. |
| Connectors | **XT60 input** on panel, **XT30 output** → 5.5×2.5 mm barrel adapter to the picoPSU | Spot-welded pack + harness. |
| Cooling | **80 mm fan**, on-board 4-pin header (12 V, PWM, tach) | Temperature-controlled by the MCU. |
| Ambient | **30–35 °C** inside the server | Design margin above this. |
| Prototype | **JLCPCB, 5 pcs, EMC-ready** | Rules in `.kicad_dru`. Default to the **standard 5 mil** tier. |

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
- **FR-16 Fan control.** An 80 mm fan on the on-board 4-pin header runs at a
  fixed **~33 % duty by default**, and ramps to **100 %** once any monitored
  temperature (cells or power components) comes **within 5 °C of its limit**.
  It runs at 100 % regardless of whether the module is on input or battery
  (no runtime-saving cutoff).

## 5. Non-functional requirements

- **NFR-1 Efficiency.** Output converter ≥ 90 % and charger ≥ 90 % at typical
  load (`TBD` exact measurement points).
- **NFR-2 Self-consumption.** ≤ 1 mA drawn from the pack when idle with no
  input, so a stored module is not drained.
- **NFR-3 Thermal.** Fan-cooled (80 mm, FR-16); heat spread into the PCB and
  enclosure; component and cell temperatures below `TBD` °C at **35 °C ambient**
  (module sits inside the server; design margin above that).
- **NFR-4 Mechanical.** Pack + PCB + connectors fit a standard ATX bay
  (150×86×140 mm) including creepage/clearance and pack retention.
- **NFR-5 EMC.** Designed for EMC/CE but no formal test for the prototype.
- **NFR-6 Reproducibility.** Schematic, layout, BOM, simulations and the test
  plan are versioned and reproducible headlessly (`make` / KiBot / ngspice).
- **NFR-7 Safety.** Fusing on pack and input, insulated pack, defined
  creepage/clearance, temperature monitoring on the cells.
- **NFR-8 Cost.** Prototype unit cost `TBD`.
- **NFR-9 Manufacturing.** JLCPCB, 5 boards, ≥ 4 layers; DRU aligned to the
  fab's capabilities. **Target the standard 5 mil tier** (min trace/clearance
  0.127 mm) by default; only step up to the advanced 3.5 mil tier where a
  documented geometry genuinely cannot meet 5 mil. A trace must also carry its
  net's **design current** (see `hardware/power_report.py`).
- **NFR-10 Serviceability.** Pack is spot-welded with a lead harness; the board
  is replaceable and re-flashable over USB (RP2040 UF2).
- **NFR-11 Measurement accuracy.** Voltage/current/SOC accuracy `TBD` (see test
  plan §Phase 7).

## 6. Interface requirements

- **IF-1 (A, input).** **XT60** panel connector (2-pin, **+12 V / GND**, 60 A
  peak / ~30 A cont.) at the ATX AC-inlet location on the mounting-screw side
  of the enclosure. 12 V nominal; operating window 11.0–13.5 V; over-voltage
  protection above `TBD` V, transient survival to `TBD` V; reverse and
  short-circuit protected; fused.
- **IF-2 (B, battery).** Internal 4S1P LFP pack, spot-welded with nickel strips
  and a lead harness to internal PCB terminals; pack-level AFE **TI BQ76942**
  with per-cell sensing, current sense and NTC(s); passive balancing;
  charge/discharge FETs on the PCB.
- **IF-3 (C, output).** **XT30** output pigtail (2-pin, +12 V / GND) feeding a
  short XT30 → 5.5 × 2.5 mm barrel-plug adapter into the picoPSU; continuous
  ≥ 15 A (180 W), peak ≥ 17 A (200 W) for ≤ 10 s; ripple ≤ 100 mVpp; load-step
  deviation ≤ 5 % recovering in < 1 ms. The barrel plug, XT30 and cable are
  part of the BOM.
- **IF-4 (D, host link).** USB-C (Full-Speed, data only) presenting a composite
  device: **CDC-ACM** (line-framed protocol for custom tooling) and **USB HID
  Power Device Class** (so the OS / Network UPS Tools `usbhid-ups` sees a native
  UPS). The HID-PDC path provides low-battery signalling that `upsmon` turns
  into a clean host shutdown with no custom daemon.
- **IF-5 (enclosure).** Standard ATX bay; **XT60 input** on the panel at the
  AC-inlet location with strain relief; internal XT30 output to the picoPSU;
  **80 mm fan** mount; LED/button access; **chassis-ground bonding** (the
  picoPSU 12 V input has no dedicated earth return, so the module is grounded
  to the chassis).

## 7. Constraints

- EDA: KiCad 9 + `kicad-cli`/KiBot, headless, driven through the `Makefile`
  (`docs/decisions/0001-tooling-and-workflow.md`).
- Simulation: ngspice for the power path, converter and protections.
- Everything in git; checks reproducible in CI.

## 8. Open items (TBD)

1. ~~**Exact cell**~~ **Resolved:** Topband 33138-HE, 3.2 V / 15 Ah LiFePO₄,
   33 × 140 mm, round, spot-weldable, 1C charge / 2C discharge, 0–45 °C charge,
   −20–60 °C discharge, > 2000 cycles. No datasheet: source is vendor spec +
   in-house measurement (ADR-0007). Cells are matched/new.
2. ~~**AFE part**~~ **Resolved:** TI BQ76942 (3–10S, LiFePO₄). Balancing
   current still `TBD` (target 20–50 mA). ADR-0006.
3. ~~**Buck-boost output controller**~~ **Resolved:** TI LM5176. ~~**Charger**~~
   **Resolved:** TI BQ25720. ADR-0006.
4. **Charger current ceiling:** default 5 A confirmed, but the BQ25720's ~10 A
   input-current limit caps charging at **~8 A** (not the 1C/15 A the cell
   allows). Decide whether ~8 A is acceptable or a different charger is needed.
   Termination rule still `TBD`.
5. ~~**ATX bay**~~ **Resolved:** standard ATX bay; input panel connector at the
   AC-inlet location on the mounting-flange side. Exact clearance in the
   particular chassis to confirm during layout.
6. Component temperature limit and efficiency/accuracy measurement points.
7. Firmware stack (Pico SDK vs PlatformIO) and the on-wire CDC protocol framing.
8. Output ripple and transfer-transient limits confirmation.
9. Whether to add a discrete shutdown/FSD line as a hardware backup to the USB
   signalling.
10. Prototype cost target and USB connector type on the enclosure.
11. ~~**Derive the passives**~~ **First pass done:** see `docs/bom.md`
    (FETs, inductors, sense resistors, TVS, NTCs, caps) — values marked
    "verify" there are to be confirmed against the vendor datasheets.
    Verify the ADI LTC4421 alternative if a purpose-built priority controller
    is preferred.
12. ~~**Cell datasheet file/link**~~ **Resolved (waived):** no vendor datasheet
    exists for the sourced cells; characterise the real cells on the bench
    (ADR-0007).
13. ~~**MR60 third pin**~~ **Resolved:** input connector changed to **XT60**
    (2-pin, +12 V/GND) — no paralleled pins needed (IF-1).
14. **Fan**: control curve fixed (FR-16); component limits (cells/power) and
    the fan's PWM/tach electricals to confirm.
15. **Chassis grounding/bonding** scheme for the module.
16. ~~**Connector part numbers**~~ **First pass:** listed in `docs/bom.md` and
    `docs/datasheets/` (XT60, XT30, 5.5 × 2.5 mm barrel plug, 80 mm fan);
    exact orderable PNs to confirm at purchase.

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
| Input connector | XT60 (2-pin, +12 V/GND) | 60 A peak; simpler than a 3-pin motor connector, ample for ~20 A. |
| Output connector | XT30 → 5.5×2.5 barrel | 13 A output fits XT30; barrel matches the picoPSU. |
| Cooling | 80 mm fan, temp-controlled | Ambient 30–35 °C; fan saves runtime on battery. |
| Mechanical | Module in an ATX bay, welded pack | Self-contained drop-in for the PSU bay. ADR-0005. |
| Cell data source | Vendor spec + measurement | No datasheet exists. ADR-0007. |
| Docs language | English | Project decision. |
