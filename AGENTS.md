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
make power      # Power / ampacity check (design current per net)
make sense      # Current-sense (Kelvin) check (SENSE_BOARD=<board>)
make test       # pytest (Toolchain-Smoke + später Bring-up/Abnahme)
make check      # erc + drc + netlist + bom (CI-Einstiegspunkt)
make clean
```


KiBot (ERC/DRC-HTML-Reports, CI-Berichte) läuft zusätzlich per
`kibot -b <pcb> -e <sch> -c <kibot.yaml>`.

Versionsstand: [`docs/toolchain.md`](docs/toolchain.md).

## Umgebung

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
- work through the `Makefile`; every schematic/layout change ends
  with `make check`; design decisions get an ADR in `docs/decisions/`;
  output artifacts (`build/`, `reports/`, `gerbers/`) are not versioned.

## Documentation: history vs. timeless docs

- **Do not add a history or decision entry unless it was called for.** The
  edited files and the diff are the record; most changes need neither, and a
  session that produces documentation instead of progress has produced nothing.
- **Entries are brief.** A history entry is a paragraph or two — what was wrong,
  what fixed it, the numbers that matter. The context lives in the files that
  changed; do not restate it.
- **An entry gets its one line in [`docs/history/README.md`](docs/history/README.md)
  as it is written**, not on request — at most 80 characters, no extra detail.
- **Never spread fixed bug reports, gotchas, "was broken, now fixed"
  narratives, reverts or one-off findings through the long-lived docs.** They
  are point-in-time and rot; a stale story in a timeless doc is worse than no
  story.
- **`docs/history/` is where they go** — one file per finding,
  `NNNN-<slug>.md` with the same fixed-width counter as the ADRs (see
  [`docs/history/README.md`](docs/history/README.md)). No dates in names (git
  holds chronology). Append-only: do not rewrite an old entry, add a new one.
- **Timeless docs stay clean of point-in-time state.** `README.md`, `AGENTS.md`,
  `docs/requirements.md`, `docs/architecture.md`, `hardware/**/README.md` and
  `docs/decisions/*` describe *how things are*, never *what happened* or *what's
  currently broken*. At most, link to the `docs/history/` entry.
- **ADRs are decisions, not changelogs.** Keep the decision and its rationale in
  the ADR; put the defect that motivated it (and its numbers) in
  `docs/history/` and reference it.
- **`RESUME.md` is the one allowed exception:** it is current session state, so
  it may carry a short, up-to-date status — but it points at `docs/history/` for
  the story instead of retelling it.
- **`docs/progress.md` is metrics-only.** It tracks how the numbers move as
  placement / routing / power advance. Record a row **with numbers** whenever the
  process, the board or a metric changes; the story (if any) goes in
  `docs/history/` and is linked from the row. No commentary, no findings.
