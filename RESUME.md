# RESUME — TinyUPS

**Start here in a fresh session.** Handoff: what the project is, what changed
this session, the plan, current numbers, and exactly how to continue.

## Status at a glance

| Area | State |
| --- | --- |
| Schematic | ✅ generated, **ERC-clean** (129 symbols, 115 nets) |
| Placement | 🔄 **power-first bands** (power parts on the centreline), board 150×140 mm |
| Routing | ⬜ **not routed** — the old advanced-tier route is superseded; re-route pending Stage 2 |
| Power / ampacity | ❌ **10/10 nets FAIL** (`make power`) — no pours yet |
| DRC (standard 5 mil) | ⬜ pending re-route (unrouted board ⇒ 278 unconnected, no geometry errors) |
| Fabrication | not exported yet |
| Bench / DVT | not started (test plan exists) |

## key WIPs

1. **Power tooling built:**
   - `power_spec.py` — design current + rail voltage per net (single source).
   - `power_map.py` — per-component power map → `build/power-map.csv`
     (shunt P=I²R, FET I²Rds, inductor I²DCR, cap ripple `I_rms=V/|Z|`,
     divider V²/R, …). Defines "power-handling" = series element ≥ 1 A,
     capacitor ripple ≥ 1 A, or dissipation ≥ 1 W.
   - `power_silk.py` — draws those parts on F.Silkscreen (red via
     `make silk` + `hardware/themes/tinyups-red.json`).
   - `place_metrics.py` — **power-path score**: mean distance to the
     centreline + flow straightness.
4. **Pack path fixed (Option A, high-side).** The AFE protection FETs were
   shorted across `VBAT` and `N_CATH` (ideal-diode output) went nowhere — the
   pack could not feed the system. Now: `PACK+ → Q11 → N_PACKMID → Q12 → VBAT`
   (common source), `PACK− → CELL0 → R25 → GND`, AFE supply from `PACK+`
   (pre-FET), `N_CATH → VIN_SYS`. Added **J6** (2-pin high-current PACK
   terminal) + **J7** (5-pin CELLS sense header).
5. **Power-first placement** — `gen_pcb.py` splits each stage into
   power-handling vs signal parts: the power parts sit on the **centreline**
   (centre column), the signal parts flank them, in stage bands
   (`A`, `C`, `B+E`, `D+F`). Connectors are anchored first.
6. **3D renders with component bodies** — installed `kicad-packages3d`,
   `KICAD9_3DMODEL_DIR` wired in the Makefile + Dockerfile; `make render`
   → `build/tinyups.png` (isometric). Camera via `RENDER_ROTATE` / `RENDER_ZOOM`.

## The plan: power-path-first

**Stackup (ADR-0008): `F.Cu` = power pour (+ signals around it), `In1.Cu` =
GND, `In2.Cu` = signal, `B.Cu` = signal (+ GND pour).** GND stays adjacent to
the power layer so the converters' hot loops close tightly; power on the top
outer layer connects SMD pads directly (no via bottleneck, 1 oz).

Floorplan: connectors first (XT60 in back-centre; XT30 + USB front; USB left of
XT30), power path straight back→front, charger (C) and pack/AFE (E) branching
right, MCU (F) left.

- **Stage 1 ✅** — anchored floorplan + power corridor.
- **Stage 1.5 ✅** — power/signal split: power parts on the centreline, signal
  parts flanking (see score below).
- **Stage 2 ⬜ NEXT** — power **pours** on F.Cu sized to current, GND pour on
  In1, `Power`/`Signal` net classes, `route.py` marks the power/plane layers in
  the DSN so freerouting keeps signals off the corridor, then re-route and read
  DRC (standard) + `make power`.
- **Stage 3 ⬜** — MCU/signal refinement; confirm In2/B.Cu can carry the signals.

## Metrics (current)

```
placement: total HPWL 8227 mm · weighted 15448 mm · decap 14.7 mm
           power parts 26 · mean |dx| to centre 12.3 mm · straightness 4.14
routing:   not routed (rebuild in progress)
power:     10/10 nets FAIL  (worst ~46x short)  — pours not added yet
gates:     ERC 0 · test 6/6 · DRC geometry-clean (unrouted)
board:     150 x 140 mm · 124 footprints · 115 nets
```

Reproduce: `make erc`, `make drc`, `make power`, `make render`, `make silk`,
`/opt/eda/venv/bin/python hardware/{place_metrics,routing_report,power_map}.py`.

## Next step

**Stage 2 — pours + stackup + re-route.** Concretely:
1. `gen_pcb.py`: add power **zones** on F.Cu along the corridor (`+12V_IN`,
   `VIN_SYS`, `VBAT`, `VOUT12`), sized to design current; move the GND zone to
   In1 (already there) and add a B.Cu GND pour; define net classes.
2. `route.py`: mark F.Cu/In1.Cu as power/plane in the exported DSN so signals
   stay on In2/B.Cu (+ the gaps around the corridor); re-route; refill.
3. Read `make drc` (standard) + `make power` + `place_metrics`; iterate.

Also open:
- **F1 is a `Fuse_1206_3216Metric`** — cannot be a 25 A fuse; pick a real
  footprint (BOM value already flagged "(verify)").
- L2/L3 (`L_12x12mm_H8mm`) have no 3D model — add placeholder boxes if wanted.
- The `set_sheet.py` step is not in the rebuild loop yet (the 2D `make silk`
  view is off-sheet).