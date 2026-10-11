# Toolchain – Stand & Verifikation

Verifiziert im laufenden Dev-Container.

## Umgebung

| Punkt | Wert |
| --- | --- |
| Basis | Ubuntu 26.04.1 LTS (Dev-Container) |
| Agent | OpenCode v2.0.26 (Port 4096) |
| Architektur | x86_64 |

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
| pytest / pytest-html | 9.0.2 / 4.2.0 |
| Python | 3.14 (`/opt/eda/venv`, `--system-site-packages`) |

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
