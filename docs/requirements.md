# TinyUPS – Designziele & Anforderungen

> Status: **Entwurf**. Mit `TBD` markierte Werte sind Vorschläge und noch zu bestätigen.
> Dieses Dokument ist die oberste Anforderungsquelle; Architektur, Layout und
> Testplan müssen darauf zurückführbar sein.

## 1. Zweck

Eine kompakte, unterbrechungsfreie DC-Stromversorgung („Mini-UPS") für
Single-Board-Computer (Raspberry Pi & vergleichbare SBC), die den SBC bei
Ausfall oder Wegfall der externen Versorgung für eine definierte Zeit
weiterbetreibt und den Zustand über eine Telemetrieschnittstelle meldet.

## 2. Kontext & Annahmen (Vorschlag, zu bestätigen)

| Größe | Vorschlag | Anmerkung |
| --- | --- | --- |
| Ziel-SBC | Raspberry Pi 4 / 5 und kompatible SBC | Lastprofil 5 V |
| Ausgangsspannung | **5,0 V** (toleranzarm, `TBD` ±3 %) | Pi 5 benötigt bis ~5 A |
| Ausgangsstrom | **bis 5 A** (`TBD`) | Dauerstrom, Peak berücksichtigen |
| Ausgangsleistung | bis **25 W** (`TBD`) | |
| Eingang | **5 V DC**, Barrel/USB-C (`TBD`) | ggf. USB-C-PD-Sink |
| Batterie | **1S Li-Ion** (3,0–4,2 V) mit BMS (`TBD`) | Alternative: LiFePO4, Supercaps |
| Backup-Zeit | **≥ 10 min bei 10 W** (`TBD`) | hängt von Zellkapazität ab |
| Recheneinheit | **MCU** mit Telemetrie (`TBD: ESP32-C3 / STM32 / RP2040`) | Spannungs-/Strommessung, Status |
| Telemetrie | I²C und/oder UART/USB (`TBD`) | Protokoll noch offen |
| Schutzart | OVP, OCP, UVLO, Verpol-, Übertemperaturschutz | |
| Formfaktor | `TBD` (z. B. Pi-HAT-kompatibel) | |
| Stückzahl | Prototyp (1–5) (`TBD`) | bestimmt Fertiger/Regeln |

## 3. Funktionale Anforderungen

- **FR-1** Der SBC wird bei vorhandener Eingangsspannung aus dem Eingang versorgt
  („priority power path", Eingang hat Vorrang vor Batterie).
- **FR-2** Bei Ausfall des Eingangs übernimmt die Batterie **unterbrechungsfrei**
  (definierter Spannungseinbruch ≤ `TBD` mV für ≤ `TBD` µs).
- **FR-3** Der Ausgang hält 5,0 V über den gesamten Batteriespannungsbereich.
- **FR-4** Die Batterie wird bei anliegendem Eingang mit definiertem Profil
  geladen (CC/CV, Temperatur-/Spannungsgrenzen).
- **FR-5** Der MCU erfasst Batteriespannung, -strom, Temperatur und Statusflags
  und stellt sie über die Telemetrieschnittstelle bereit.
- **FR-6** Ein sauberes Herunterfahren des SBC wird signalisiert (z. B. GPIO-IRQ,
  `TBD`), bevor die Batterie erschöpft ist.
- **FR-7** Alle Schutzfunktionen greifen ohne Eingriff des Nutzers.

## 4. Nicht-funktionale Anforderungen

- **NFR-1 Effizienz**: Wandlungs-/Ladewirkungsgrad ≥ `TBD` % bei Nennlast.
- **NFR-2 EMV**: Störungen gering halten (Schaltregler-Layout); CE-Prüfung
  `TBD` (für Prototyp optional, Vorbereitung dennoch).
- **NFR-3 Thermik**: Bauteiltemperaturen unter `TBD` °C im Nennbetrieb.
- **NFR-4 Sicherheit**: Schutzbeschaltung für Li-Ion (Überladen/Tiefentladung/
  Kurzschluss/Überstrom), Battery-Management `TBD` (diskret vs. IC).
- **NFR-5 Reproduzierbarkeit**: Design, Checks und Testplan vollständig im Repo
  versioniert und per CLI/CI reproduzierbar.
- **NFR-6 Kosten**: Stückkosten (Prototyp) `TBD`.
- **NFR-7 Fertigung**: Leiterplatte bei `TBD` (JLCPCB / PCBWay / Aisler), Regeln
  als `.kicad_dru` hinterlegt.

## 5. Randbedingungen

- EDA und Review erfolgen **headless über KiCad 9 + `kicad-cli`/KiBot**
  (siehe `docs/decisions/0001-tooling-and-workflow.md`).
- Alle Artefakte (Schaltplan, Layout, BOM, Gerber, Testskripte) liegen in git.
- Werkzeuge laufen im Dev-Container (siehe `.devcontainer/`).

## 6. Offene Fragen

1. Ziel-SBC und tatsächliches Lastprofil (5 V/3 A vs. 5 V/5 A)?
2. Eingangsstecker und -spannung: Barrel 5 V, USB-C-PD, oder 12 V?
3. Batteriechemie und Kapazität (Backup-Zeit-Ziel)?
4. Wo wird der UPS funktional eingeschleift (inline am SBC vs. HAT)?
5. MCU-Familie und Telemetrie-Protokoll (I²C-Register vs. UART-Text/USB-CDC)?
6. Soll ein sauberes Shutdown-Signal (GPIO) vorgesehen werden?
7. Fertiger und Stückzahl für die Layoutregeln?
8. Zulassungsanspruch (CE/EMV) schon für den Prototyp relevant?
