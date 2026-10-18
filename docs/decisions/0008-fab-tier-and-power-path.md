# 0008 – Fab tier and power-path-first layout

- Status: accepted

## Decision

1. **Standard 5 mil tier by default** (min trace/clearance 0.127 mm); advanced
   3.5 mil only for a documented geometry that genuinely cannot meet it (NFR-9).
   The autorouter at 3.5 mil had used 0.095–0.127 mm for **everything**,
   including power: `power_report.py` showed 10/10 power nets undersized (the
   XT60 → fuse link a single 0.127 mm trace at ~0.27 A; `VIN_SYS` at 0.095 mm
   ~0.43 A; ≈46× short). DRC has no ampacity rule, so it passed every gate.
2. **Power first, then signals.**
   - **Stackup:** `F.Cu` = power pour (+ signals routed around it), `In1.Cu` =
     GND, `In2.Cu` = signal, `B.Cu` = signal. GND stays adjacent to the power
     layer so the switching converters' hot loops close tightly.
   - High-current nets (`+12V_IN`, `N_AF`, `VIN_SYS`, `VBAT`, `VSYS`, `VOUT12`,
     switch nodes) are carried as **copper pours** sized to their design current
     — never signal-width traces. `hardware/pour_power.py` builds them.
   - **Floorplan:** connectors on the edges, the power path straight back→front,
     branches to the charger and the pack, the MCU on the left.
3. **Add the missing gate.** `power_report.py` sizes every power net against its
   design current (IPC-2221) and fails otherwise; it must size a **pour** (a
   zone), not only a trace.
4. **2 oz outer copper**, which halves every required width (20 A → **9.4 mm** at
   10 °C rise). The inner-layer weight sets the GND return and is to be confirmed.

## Consequences

- Signals must stay off the `In1.Cu` GND plane so it stays one surface. The
  guard that does that is settled by measurement
  ([history 0013](../history/0013-plane-layer-type-kills-vias.md)); until then
  the plane is *measured* by `power_report.py` rather than forbidden.
- The fuse footprint (`Fuse_1206_3216Metric`) physically cannot be a 25 A fuse;
  revisit.
- Requirements: FR-1, FR-3, FR-5, NFR-1, NFR-7, NFR-9.
