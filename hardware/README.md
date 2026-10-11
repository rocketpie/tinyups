# Hardware / schematic

The schematic is **generated** from a small, readable description so it stays
deterministic and diff-friendly.

## Files

| File | Role |
| --- | --- |
| `gen_schematic.py` | Generator: symbol placement + netlist description. Edit this. |
| `tinyups.kicad_sch` | **Generated** schematic (do not hand-edit). |
| `tinyups.kicad_pro` | KiCad project. |
| `sym-lib-table` | Project symbol table (standard libs + `tinyups`). |
| `libs/tinyups.kicad_sym` | **Generated** custom IC symbols (box symbols). |

## Regenerate & check

```sh
/opt/eda/venv/bin/python hardware/gen_schematic.py   # rebuild the schematic
make erc                                             # electrical rule check
make netlist && make bom                             # netlist + BOM
```

## Approach

- Standard symbols come from KiCad's libraries (`Device`, `Transistor_FET`,
  `Connector_Generic`, `power`).
- ICs are generated as **box symbols** from their datasheet pinouts
  (`box_symbol(...)`); see `docs/datasheets/` for the sources.
- **Connectivity is by named labels placed on each pin** (`b.net(ref, pin,
  name)`). KiCad connects same-named labels on a sheet, so no wire routing is
  needed and the result is stable.
- All placements are snapped to the 1.27 mm grid (ERC `endpoint_off_grid`).

## PCB / layout

- **`gen_pcb.py`** builds `tinyups.kicad_pcb` from the netlist: 4 copper
  layers, board outline, design rules, all footprints placed (shelf-packing,
  so no courtyard overlaps) and nets assigned to pads.

  ```sh
  make netlist                                   # ensure build/tinyups.net
  /opt/eda/venv/bin/python hardware/gen_pcb.py   # build the board
  ```

- **Routing:** KiCad has no autorouter, so routing uses **freerouting**
  (Java), driven by `hardware/route.py`: export Specctra DSN →
  relax the design rules to the JLCPCB minimum (0.13 mm) → route → import the
  session → refill zones.

  ```sh
  FREEROUTING_JAR=/opt/freerouting/freerouting.jar \
      /opt/eda/venv/bin/python hardware/route.py
  make drc
  ```

  Two things matter for it to converge:
  1. **Planes.** GND (In1.Cu) and the main 12 V rail VIN_SYS (In2.Cu) are
     copper zones, exported to the DSN as `plane`s, so the router doesn't
     have to route those high-fan-out nets as tracks. Filled by
     `hardware/fill_zones.py`.
  2. **Rules.** The default 0.2 mm track/clearance cannot escape the
     0.4 mm-pitch QFN parts (RP2040, BQ25720, LM5176); relaxing to 0.13 mm
     (5 mil, JLCPCB minimum) lets the router fan them out.

- **Note:** `make drc` fails until *every* net is routed (unconnected pads are
  DRC errors). The current placement is automatic and not electrically
  optimised — a hand-tuned placement is the main thing that improves routing.

## Placement quality

Placement is quantified (see `hardware/place_metrics.py`) so it can be
compared and improved objectively:

| Metric | Meaning | shelf-pack (naive) | block-aware |
| --- | --- | --- | --- |
| total HPWL | Σ per-net pad bounding-box (w+h) — total copper length | 9 955 mm | **5 188 mm** |
| weighted HPWL | same, high-current nets ×6 | 17 504 mm | **13 461 mm** |
| power-net HPWL | only the high-current nets | 1 510 mm | 1 654 mm |
| decap distance | mean IC supply pin → nearest cap | 37 mm | **18 mm** |

`gen_pcb.py` places parts **grouped by functional block** (A–F, same split as
the schematic) and packs the blocks on a 3-column grid, instead of packing all
parts globally. That roughly halved the wirelength and the decoupling distance.

Run it on any board:

```sh
/opt/eda/venv/bin/python hardware/place_metrics.py
```

## Status

All blocks placed, **footprints assigned to every part**, and **ERC-clean**
(0 errors, 0 warnings; 122 components):

| Block | Parts | State |
| --- | --- | --- |
| A – input protection + hot-swap | XT60, fuse, TVS, LM5069, pass FET, UVLO/OVLO/TIMER/PWR/PGD support | done |
| B – priority power path | LM74700 ideal diode, pack FET, charge-pump cap, hold-up caps | done |
| C – charger | BQ25720 + 4 FETs, 2.2 µH inductor, senses, boot/REGN/VDDA, SMBus pull-ups, COMP/PSYS/monitor + CHRG_OK/PROCHOT networks | done |
| D – output converter | LM5176 + 4 FETs, 1.0 µH inductor, feedback/comp/soft-start, sense, output caps + XT30 | done |
| E – battery AFE | BQ76942 + CHG/DSG FETs, pack sense, cell RC filters, thermistors, LDOs, CFETOFF/DFETOFF | done |
| F – MCU / USB / fan | RP2040 + QSPI flash, 3V3 reg, crystal, USB, SWD, 80 mm fan header, LEDs | done |

Support networks (compensation, monitors, pull-ups) are taken from the TI
reference designs PMP21278 / PMP22419. `PWR_FLAG`s mark the externally-sourced
nets (`+12V_IN`, `GND`, `VBAT`, `VOUT12`, `+3V3`).

`make check` runs `erc`, `drc`, `netlist` and `bom`. `drc` only passes once
every net is routed (unconnected pads are DRC errors) — see below.

## PCB status

`tinyups.kicad_pcb` is generated and **routed**: **4 layers, 122 footprints,
113 nets, 145 × 138 mm** (inside the ATX bay), ~1630 tracks / ~294 vias.

- Placement is DRC-clean (no clearance/overlap/edge issues).
- Routing: **112 of 113 nets** routed by freerouting (planes on In1/In2,
  JLCPCB 0.09 mm rules).
- **Remaining `drc` findings (3):** one unrouted status net (`N_PGOOD`), a
  `VIN_SYS` stub and a dangling via on `N_PGOOD`. These are a few minutes of
  manual cleanup in the KiCad GUI.
- Traces use **0.09 mm (3.5 mil)** in places (QFN fanout) → **JLCPCB
  "advanced"** tier, or widen on a re-route.

So `make erc` passes; `make drc` fails only on those 3 items.

## Remaining before/with layout

- **Pin electrical types**: IC pins are still `passive`. Typing them
  (`power_in`/`output`/…), which also needs the internal rails (REGN, VDDA,
  REG1/2, VCC, DVDD) modelled, is deferred to the layout phase.
- A few pins stay **no-connect** where the network isn't modelled yet
  (BQ76942 precharge/predischarge, unused RP2040 GPIOs, charger BATFET).
- Values are first-pass (`docs/bom.md`); dividers/compensation are nominal.


