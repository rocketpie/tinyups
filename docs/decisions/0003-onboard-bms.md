# 0003 – On-board AFE battery management

- Status: accepted

## Context

The module contains a 4S1P LiFePO₄ pack. LiFePO₄ needs over/under-voltage,
over-current, short-circuit and temperature protection, cell balancing, and
the telemetry that FR-6/FR-7 require (per-cell voltages, pack current,
temperatures, coulomb counting).

## Decision

- Use an **analog front-end (AFE) BMS** on the PCB (e.g. the BQ769x2 family)
  with **charge and discharge protection FETs**, per-cell sense inputs, a
  current-sense resistor, and NTC inputs.
- **Passive balancing** is sufficient for a 1P pack.
- The AFE is the primary safety layer (hard cutoffs at 2.8 V/cell; absolute
  minimum 2.5 V/cell); the MCU adds the application layer (force-off at
  3.0 V/cell, SOC, signalling).
- The battery terminals are internal to the module; there is no external pack
  connector.

## Consequences

- Per-cell telemetry and coulomb counting are available directly to the MCU
  over I²C, supporting accurate SOC on the flat LFP curve.
- More design effort (FET sizing, sense routing, protection) than a simple
  protection IC, and a larger BOM.
- The pack is not user-serviceable at cell level; the board is re-flashable.
- Related requirements: FR-6, FR-7, FR-9, FR-11, FR-12, FR-14, IF-2, NFR-7.
