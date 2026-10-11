# 0001 – Werkzeuge und Workflow für PCB-Design

- Status: akzeptiert

## Kontext

Der TinyUPS soll dokumentiert, entworfen, mit Bauteilauswahl versehen und
validiert werden. Der Agent arbeitet dabei in einem Dev-Container und soll
möglichst alle Werkzeuge headless und reproduzierbar nutzen können.

## Entscheidung

1. **EDA-Kern: KiCad 9 + `kicad-cli`/KiBot (Hybrid).**
   KiCad für Schaltplan/Layout; alle Prüfungen und Exporte headless über
   `kicad-cli` und KiBot. Formate sind textbasiert und git-freundlich.
2. **Simulation: ngspice (ggf. via PySpice).**
   Für Power-Path, Wandler und Schutzbeschaltungen vor dem Layout.
3. **Recheneinheit: MCU mit Telemetrie.**
   Verhalten unabhängig vom SBC beobachtbar und autark testbar.
4. **Ziel: DC-UPS für PC**, Ausgang ~12 V.
5. **Test: `pytest` + PyVISA/PyMeasure + sigrok-cli** für automatisierte
   Bring-up- und Abnahmetests.
6. **Alles im Repo**: Schaltplan, Layout, BOM, Gerber, Tests, Doku. Checks als
   `make`-Ziele, identisch in CI (GitHub Actions).

## Konsequenzen

- GUI-KiCad ist optional (noVNC-Feature) und nicht Voraussetzung für den Workflow.
- Der Agent kann ERC/DRC/Exporte selbst ausführen und iterieren.
- Der laufende Container muss die Werkzeuge enthalten; Änderungen am
  `Dockerfile` greifen erst beim nächsten Rebuild.
