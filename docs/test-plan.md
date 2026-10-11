# TinyUPS – Test & Validation Plan (Draft)

> Status: **Draft, aligned with the 12 V / 4S-LFP concept** in
> `docs/requirements.md`. Purpose: reproducible DVT of the first prototype once
> the parts arrive. Automatable tests run under `pytest` in `tests/` via
> `make test`.

## 1. Tools / instrumentation

| Tool | Purpose | Control |
| --- | --- | --- |
| Programmable 12 V supply (≥ 20 A) | Simulate input, OVP/UVLO tests | SCPI (PyVISA) |
| Electronic DC load | Load the output (steps, transients) | SCPI (PyVISA) |
| DMM (4½ digit or better) | Reference voltage/current | SCPI / manual |
| Oscilloscope | Transients, ripple, transfer event | manual / SCPI |
| USB protocol analyzer / host scripts | CDC traffic, HID-PDC enumeration | `pyserial`, `usbmon` |
| Thermocouples / thermal camera | Heating under load | manual |
| RP2040 debug probe | Flashing/debug | probe-rs / OpenOCD |

## 2. Phases

### Phase 0 – Visual inspection & bring-up (unpowered)

- Assembly, solder joints, polarity, pack wiring, short-circuit check
  (VCC/GND, cell taps).
- **Criterion:** no short on any supply node; cell taps correct.

### Phase 1 – Input & protection (A)

- Ramp input; check OVP, reverse polarity, fuse, transient survival.
- **Criteria:** protections trip; no damage; correct behaviour at 11.0–13.5 V.

### Phase 2 – Output regulation (C)

- 12.0 V across pack-voltage and load range; ripple ≤ 100 mVpp; no-load
  stability; load steps 10–100 % within 5 % recovering < 1 ms.
- **Criteria:** output stays in the picoPSU window; ripple and transient
  limits met.

### Phase 3 – Charging

- CC/CV to 13.8 V, termination, temperature inhibit (0–45 °C), precharge of a
  deeply discharged pack.
- **Criteria:** cell voltage ≤ 3.45 V; termination clean; no charging outside
  the temperature window.

### Phase 4 – Efficiency & thermal

- Efficiency at 25/50/100 % load (converter and charger); spot temperatures at
  40 °C ambient.
- **Criteria:** ≥ 90 %; component temps below the limit; no forced air.

### Phase 5 – Transfer (core function)

- Remove and restore the input abruptly under load; observe the output.
- **Criteria:** no host reset; output stays within spec; no battery cycling
  while mains is present (verify FR-1).

### Phase 6 – Runtime

- Fixed 50 W load until force-off.
- **Criterion:** ≥ 30 min at 50 W; force-off occurs at 3.0 V/cell.

### Phase 7 – Telemetry & SOC (D)

- CDC frames and HID-PDC enumeration; `nut`/`usbhid-ups` detects the UPS;
  SOC accuracy against a reference discharge.
- **Criteria:** protocol stable; SOC within the target accuracy.

### Phase 8 – Graceful shutdown

- Drive the pack to ≤ 30 % SOC and confirm the host shuts down cleanly via
  `upsmon` (and via the CDC channel).
- **Criteria:** warning precedes force-off with enough time to shut down.

### Phase 9 – Protection & robustness

- Cell OV/UV, charge/discharge OCP, short circuit, over-temperature, deep
  discharge + recovery, hot plug, extended run.
- **Criteria:** all protections latch/reset as specified; no damage.

## 3. Automation

- `tests/test_*.py`: bring-up and acceptance via PyVISA/PyMeasure; host-side
  USB checks via `pyserial` (`/dev/ttyACM*`).
- Logic-analyzer captures with `sigrok-cli` for internal buses.
- Output: `pytest-html` report in `reports/` per run.
- Results feed back into `docs/` (or a results table).

## 4. Results tracking

| Test | Date | Setup | Result | Comment |
| --- | --- | --- | --- | --- |
| | | | | |
