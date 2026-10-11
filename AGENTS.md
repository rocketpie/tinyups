# AGENTS.md – Hinweise für den Agent

## Projekt

**TinyUPS** – kompakte DC-USV für Raspberry Pi / SBC. Schaltplan, Layout,
Bauteile, Simulation und Testplan liegen vollständig in diesem Repo.

Die oberste Anforderungsquelle ist [`docs/requirements.md`](docs/requirements.md).
Architektur: [`docs/architecture.md`](docs/architecture.md).
Testplan: [`docs/test-plan.md`](docs/test-plan.md).

## Kommandos

Immer über das `Makefile` (identisch zu CI). `make help` listet alles:

```sh
make erc        # Electrical Rule Check (kicad-cli sch erc)
make drc        # Design Rule Check + Schematic-Parity (kicad-cli pcb drc)
make netlist    # Netzliste
make bom        # Stückliste (CSV)
make gerbers    # Gerber
make drill      # Excellon-Bohrdaten (+ Bohrplan)
make fab        # Gerber + Drill als Fab-Paket
make pos        # Bestückungsdaten (CSV, mm, beidseitig)
make step       # 3D STEP
make render     # 3D-PNG-Render (headless)
make svg        # Schematic-/PCB-SVG fürs Review
make sim        # ngspice-Simulationen aus sim/*.cir
make test       # pytest (Toolchain-Smoke + später Bring-up/Abnahme)
make check      # erc + drc + netlist + bom (CI-Einstiegspunkt)
make clean
```

KiBot (ERC/DRC-HTML-Reports, CI-Berichte) läuft zusätzlich per
`kibot -b <pcb> -e <sch> -c <kibot.yaml>`.

Versionsstand und verifizierte Kommandos: [`docs/toolchain.md`](docs/toolchain.md).

## Umgebung (verifiziert)

- `kicad-cli` (KiCad 9.0.8), `ngspice` 45.2, `sigrok-cli` 0.7.2
- `/opt/eda/venv` (Python 3.14): KiBot 1.9.1, KiUtils, PyVISA, PyMeasure,
  pytest. `--system-site-packages` ist nötig, damit KiBot das System-wxPython
  findet.

`/opt/eda/venv/bin` liegt auf dem `PATH`.

## Konventionen

- **Textformate, git-freundlich.** KiCad-Dateien (S-Expression) bevorzugt per
  KiUtils/`kicad-cli` bearbeiten statt manuell zu flippen.
- **Jede Änderung an Schaltplan/Layout mit `make check` abschließen**, erst dann
  als fertig melden. ERC/DRC-Reports (in `reports/`) sind die Belege.
- **Designentscheidungen** als ADR in `docs/decisions/` dokumentieren.
- **Anforderungen referenzieren.** Änderungen an Schaltung/Bauteilen auf die
  FR-/NFR-IDs in `docs/requirements.md` zurückführen.
- **Keine Bauteile ohne Datenblatt-Quelle** (Hersteller + Teilenummer + Link).
- Ausgabeartefakte (`gerbers/`, `reports/`, `build/`) sind nicht versioniert.

## Wichtige Hinweise

- Der Container kann sich selbst **nicht** neu bauen; `Dockerfile`-Änderungen
  greifen erst beim nächsten Rebuild. Zur Laufzeit installierte Tools sofort
  nutzen, aber im `Dockerfile` nachziehen.
- Für GUI-KiCad optional das `desktop-lite`-Feature (noVNC) aktivieren.
