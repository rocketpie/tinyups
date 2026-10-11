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

## Status

All blocks placed and **ERC-clean** (0 errors, 0 warnings, 110 symbols):

| Block | Parts | State |
| --- | --- | --- |
| A – input protection + hot-swap | XT60, fuse, TVS, LM5069, pass FET, UVLO/OVLO/TIMER/PWR/PGD support | done |
| B – priority power path | LM74700 ideal diode, pack FET, charge-pump cap, hold-up caps | done |
| C – charger | BQ25720 + 4 FETs, 2.2 µH inductor, senses, boot/REGN/VDDA caps, SMBus pull-ups | done |
| D – output converter | LM5176 + 4 FETs, 1.0 µH inductor, feedback/comp/soft-start, sense, output caps + XT30 | done |
| E – battery AFE | BQ76942 + CHG/DSG FETs, pack sense, cell RC filters, thermistors, LDOs | done |
| F – MCU / USB / fan | RP2040 + QSPI flash, 3V3 reg, crystal, USB, SWD, 80 mm fan header, LEDs | done |

`make check` also runs `drc`, which needs a PCB (`hardware/tinyups.kicad_pcb`)
that does not exist yet — so use `make erc netlist bom` until layout starts.

## First-pass caveats (to refine before layout)

- IC pins are typed `passive`; power/input/output types + `PWR_FLAG`s come later.
- Some IC pins are marked **no-connect** where their support network is not
  modelled yet (e.g. BQ25720 COMP/PSYS/PROCHOT, BQ76942 precharge/predischarge,
  unused RP2040 GPIOs). These are intentional placeholders.
- No footprints assigned yet (BOM `Footprint` column empty).
- Component values are first-pass (see `docs/bom.md`); dividers/compensation
  are nominal.

