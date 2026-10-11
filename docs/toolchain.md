# Toolchain – Stand & Verifikation

Verifiziert im laufenden Dev-Container am 2026-10-11.

## Umgebung

| Punkt | Wert |
| --- | --- |
| Basis | Ubuntu 26.04.1 LTS (Dev-Container) |
| Agent | OpenCode v2.0.26 (Port 4096) |
| Architektur | x86_64, 12 Kerne, 15 GB RAM |

Die Toolchain ist **zur Laufzeit installiert** und im
[`.devcontainer/Dockerfile`](../.devcontainer/Dockerfile) nachgezogen, damit ein
Rebuild sie reproduzierbar mitbringt.

## Versionen

| Werkzeug | Version |
| --- | --- |
| KiCad / `kicad-cli` | 9.0.8 |
| kicad-libraries (Symbole, Footprints, 3D) | 9.0.8 |
| ngspice | 45.2 |
| sigrok-cli | 0.7.2 |
| KiBot | 1.9.1 |
| KiUtils | 1.4.8 |
| PyVISA / PyVISA-py | 1.16.2 / 0.8.1 |
| PyMeasure | 0.16.0 |
| python-can | 4.6.1 |
| pytest / pytest-html | 9.1.1 / 4.2.0 |
| Python | 3.14 (`/opt/eda/venv`, `--system-site-packages`) |

## Verifizierte Kommandos

Getestet gegen das KiCad-Demoprojekt `interf_u` (nicht gegen das noch leere
TinyUPS-Projekt). ERC/DRC melden erwartungsgemäß Verletzungen des Demos; wichtig
ist, dass die Prüfung ausgeführt und ein Report erzeugt wird.

| Aktion | Kommando (via Makefile) | Ergebnis |
| --- | --- | --- |
| ERC | `make erc` | `reports/erc.rpt`, Exit 5 bei Verletzungen |
| DRC + Schematic-Parity | `make drc` | `reports/drc.rpt` |
| Netlist | `make netlist` | `build/<name>.net` |
| BOM | `make bom` | `build/<name>-bom.csv` |
| Gerber | `make gerbers` | `build/gerbers/*.g*` |
| Bohrdaten | `make drill` | `build/gerbers/*.drl` + Bohrplan |
| Bestückung | `make pos` | `build/<name>-pos.csv` (mm, beidseitig) |
| 3D | `make step` | `build/<name>.step` |
| Render | `make render` | `build/<name>.png` (headless Raytracing) |
| SVG (Review) | `make svg` | `build/sch-svg/`, `build/pcb-svg/` |
| Simulation | `make sim` | ngspice Batch, Logs je `.cir` |
| Tests | `make test` | 6/6 Smoke-Tests grün |
| KiBot | `kibot -b <pcb> -e <sch> -c <yaml>` | ERC/DRC-HTML-Reports |

## Erkenntnisse / Fallstricke

- **KiBot braucht wxPython.** Das venv wird deshalb mit
  `--system-site-packages` erzeugt, damit das System-`python3-wxgtk4.0` gefunden
  wird. Zusätzlich sind `lxml` und `--no-compile` nötig (KiBot-Empfehlung).
- **`kicad-cli pcb export drill`** nutzt `--excellon-units mm` (nicht `--units`).
- **`kicad-cli pcb export svg`** benötigt in KiCad 9 `--mode-multi` für die
  Ausgabe in ein Verzeichnis.
- `kicad-cli` schreibt harmlose `Directory ... couldn't be created (error 17)`-
  Warnungen (HOME/XDG-Init); das Ergebnis ist davon unberührt.
- `kicad-cli pcb render` funktioniert **headless** (kein Display nötig).

## Nicht installiert (bei Bedarf)

| Werkzeug | Zweck | Wie |
| --- | --- | --- |
| FreeCAD | Gehäuse / Mechanik | nicht in den Repos, PPA/Flatpak |
| Node/npm | nur für code-first EDA (tscircuit) | devcontainer-Feature |
| InvenTree / Part-DB | Inventar & Wareneingang | `docker compose` |
| desktop-lite (noVNC) | GUI-KiCad im Browser | devcontainer-Feature |

## GUI-Hinweis

Der Agent arbeitet vollständig headless. Für eine manuelle Layout-Session in
KiCad: entweder KiCad auf dem WSL-Host nutzen (das Projekt liegt im
Bind-Mount) oder das `desktop-lite`-Feature für einen Browser-Desktop im
Container aktivieren.

## Rebuild-Hinweis

Der Container kann sich **nicht selbst** neu bauen. Laufzeit-Installationen
gelten sofort; die `.devcontainer/Dockerfile`-Änderungen greifen beim nächsten
`devcontainer rebuild`.
