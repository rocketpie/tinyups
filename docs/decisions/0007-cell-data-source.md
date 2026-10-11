# 0007 – Cell data source: vendor specification + measurement

- Status: accepted

## Context

The project rule is "no component without a manufacturer + part number +
source". The chosen cell is the **Topband 33138-HE** (3.2 V / 15 Ah LiFePO₄,
33 × 140 mm). No public datasheet is available, and the cells are already
physically on hand, matched and from one batch.

Missing datasheet-grade data (OCV/SOC curve, DC internal resistance, thermal
mass, capacity at our C-rate, self-discharge) does **not** block the PCB: the
safety-relevant limits are known and the electrical protections are set from
LiFePO₄ standards with margin.

## Decision

- Accept the cell source as **vendor specification + in-house measurement**
  rather than a datasheet PDF.
- Use conservative, standard LiFePO₄ limits for protection (no vendor data
  needed): charge to **3.45 V/cell**, system force-off **3.0 V/cell**, AFE
  under-voltage **2.8 V/cell**, absolute minimum **2.5 V/cell**; charge
  inhibited outside **0–45 °C**, discharge **−20–60 °C**.
- Characterise the real cells during bring-up:
  1. capacity at our discharge current,
  2. DC internal resistance,
  3. OCV vs SOC for the SOC estimator (FR-6),
  4. temperature rise at load.
  Replace the first-order lumped model in `sim/` with the measured curve.

## Consequences

- Design can proceed immediately; SOC accuracy is refined after the board
  exists, not before.
- Protections are safe by construction even without vendor curves.
- Related requirements: FR-4, FR-6, FR-9, FR-11, NFR-11; `docs/datasheets/`.
