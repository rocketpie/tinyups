# Toolchain – status and verification

Verified in the running dev container.

## Environment

| Item | Value |
| --- | --- |
| Base | Ubuntu 26.04.1 LTS (dev container) |
| Agent | OpenCode v2.0.26 (port 4096) |
| Architecture | x86_64 |

## Versions

| Tool | Version |
| --- | --- |
| KiCad / `kicad-cli` | 9.0.8 |
| kicad-libraries (symbols, footprints, 3D) | 9.0.8 |
| ngspice | 45.2 |
| sigrok-cli | 0.7.2 |
| KiBot | 1.9.1 |
| KiUtils | 1.4.8 |
| PyVISA / PyVISA-py | 1.16.2 / 0.8.1 |
| PyMeasure | 0.16.0 |
| python-can | 4.6.1 |
| pytest / pytest-html | 9.0.2 / 4.2.0 |
| pypdf | 6.20.0 |
| Java (OpenJDK JRE) | 25.0.4.1 |
| freerouting | 2.5.0 (`/opt/freerouting/freerouting.jar`) |
| Python | 3.14 (`/opt/eda/venv`, `--system-site-packages`) |

## Findings / pitfalls

- **KiBot needs wxPython.** The venv is therefore created with
  `--system-site-packages` so that the system `python3-wxgtk4.0` is found.
  `lxml` and `--no-compile` are also required (KiBot recommendation).
- **`kicad-cli pcb export drill`** uses `--excellon-units mm` (not `--units`).
- **`kicad-cli pcb export svg`** needs `--mode-multi` in KiCad 9 to write into
  a directory.
- `kicad-cli` prints harmless `Directory ... couldn't be created (error 17)`
  warnings (HOME/XDG init); the result is unaffected.
- `kicad-cli pcb render` works **headless** (no display needed).
- **Routing needs freerouting** (KiCad has no autorouter). `kicad-cli` cannot
  create/import a PCB from a netlist either — build the board with the
  `pcbnew` Python module (`hardware/gen_pcb.py`) and route via Specctra
  (`pcbnew.ExportSpecctraDSN` / `ImportSpecctraSES` + freerouting,
  `hardware/route.py`).
- freerouting runs **headless** with the jar if the GUI is disabled: put
  `{ "gui": { "enabled": false } }` in `freerouting.json` in the working dir.
  (The native `freerouting-cli` build crashed in the autoroute stage; the jar
  works.)
- **Datasheets are PDFs and `webfetch` cannot read them.** Download the vendor
  PDF and text-extract it with **`pypdf`**, e.g.
  `python -c "from pypdf import PdfReader; print('\n'.join((p.extract_text() or '') for p in PdfReader('x.pdf').pages))"`.
  Used to verify the BOM values against the TI datasheets (`docs/bom.md`).

## Not installed (if needed)

| Tool | Purpose | How |
| --- | --- | --- |
| FreeCAD | enclosure / mechanics | not in the repos, PPA/flatpak |
| Node/npm | only for code-first EDA (tscircuit) | devcontainer feature |
| InvenTree / Part-DB | inventory & goods receipt | `docker compose` |
| desktop-lite (noVNC) | GUI KiCad in the browser | devcontainer feature |

## GUI note

The agent works fully headless. For a manual layout session in KiCad: either
use KiCad on the WSL host (the project is in the bind mount) or enable the
`desktop-lite` feature for a browser desktop in the container.
