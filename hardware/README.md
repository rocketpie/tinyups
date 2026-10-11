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
  (Java). The flow is: export Specctra DSN (via `pcbnew.ExportSpecctraDSN`) →
  route with freerouting → import the session (`pcbnew.ImportSpecctraSES`).

  ```sh
  # export
  python -c "import pcbnew;b=pcbnew.LoadBoard('hardware/tinyups.kicad_pcb');pcbnew.ExportSpecctraDSN(b,'/tmp/t.dsn')"
  # route (jar build; GUI disabled via freerouting.json {gui:{enabled:false}})
  java -jar freerouting.jar -de /tmp/t.dsn -do /tmp/t.ses -mp 30
  # import
  python -c "import pcbnew;b=pcbnew.LoadBoard('hardware/tinyups.kicad_pcb');pcbnew.ImportSpecctraSES(b,'/tmp/t.ses');pcbnew.SaveBoard('hardware/tinyups.kicad_pcb',b)"
  make drc
  ```

- **Note:** `make drc` fails until *every* net is routed (unconnected pads are
  DRC errors). The current placement is automatic (shelf-packed) and not
  electrically optimised — a hand-tuned placement (power components grouped,
  short high-current loops) is the main thing that improves routing quality.

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

`make check` also runs `drc`, which needs a PCB (`hardware/tinyups.kicad_pcb`)
that does not exist yet — so use `make erc netlist bom` until layout starts.

## Remaining before/with layout

- **Pin electrical types**: IC pins are still `passive`. Typing them
  (`power_in`/`output`/…), which also needs the internal rails (REGN, VDDA,
  REG1/2, VCC, DVDD) modelled, is deferred to the layout phase.
- A few pins stay **no-connect** where the network isn't modelled yet
  (BQ76942 precharge/predischarge, unused RP2040 GPIOs, charger BATFET).
- Values are first-pass (`docs/bom.md`); dividers/compensation are nominal.


