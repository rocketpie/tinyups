# TinyUPS – Test- & Validierungsplan (Entwurf)

> Status: **Entwurf**. Zweck: reproduzierbare DVT (Design Verification Test) des
> ersten Prototyps, sobald die Bauteile eintreffen.
> Automatisierbare Tests laufen als `pytest` in `tests/` und sind über
> `make test` aufrufbar.

## 1. Werkzeuge / Prüfmittel

| Werkzeug | Zweck | Ansteuerung |
| --- | --- | --- |
| Labornetzgerät (programmierbar) | Eingang simulieren, OVP/UVLO-Tests | SCPI (PyVISA) |
| Elektronische Last / DC-Last | Ausgang belasten (Stufen, Lastsprünge) | SCPI (PyVISA) |
| DMM (4½-stellig o. besser) | Spannung/Strom referenzieren | SCPI / manuell |
| Oszilloskop | Transienten, Ripple, Umschaltvorgang | manuell / SCPI |
| Logikanalysator | I²C/UART-Telemetrie, Shutdown-GPIO | sigrok-cli |
| Thermografie / Thermoelemente | Erwärmung unter Last | manuell |
| Programmier-Adapter | MCU flashen/debuggen | probe-rs / OpenOCD |

## 2. Testphasen

### Phase 0 – Sichtprüfung & Inbetriebnahme (spannungsfrei)

- Bestückung, Lötstellen, Polarität, Kurzschlussmessung (VCC/GND).
- **Kriterium:** kein Kurzschluss an Versorgungsknoten.

### Phase 1 – Eingang & Schutz

- Eingang rampen, UVLO/OVP/Verpolgrenzen prüfen.
- **Kriterien:** Schutzeinrichtungen greifen; keine Beschädigung.

### Phase 2 – Ausgang unbelastet & Leerlauf

- Ausgangsspannung über alles: `5,0 V ±3 %` (`TBD`), Ripple ≤ `TBD` mVpp.
- **Kriterien:** Spannung im Fenster; Leerlaufstabilität.

### Phase 3 – Laden

- Ladeprofil (CC/CV), Ladeende, Temperaturabschaltung.
- **Kriterien:** Zellspannung ≤ 4,2 V; Terminierung sauber.

### Phase 4 – Last & Wirkungsgrad

- Lastrampen bis Nennstrom, Wirkungsgrad bei 25/50/100 % Last.
- **Kriterien:** Wirkungsgrad ≥ `TBD` %; Temperatur ≤ `TBD` °C.

### Phase 5 – Umschalten (Kernfunktion)

- Eingang abrupt entfernen/wiederherstellen unter Last.
- **Kriterien:** unterbrechungsfrei, Einbruch ≤ `TBD` mV für ≤ `TBD` µs,
  kein Reset des SBC.

### Phase 6 – Backup-Zeit

- Definierte Last ziehen, bis Shutdown-Schwelle.
- **Kriterium:** Backup-Zeit ≥ `TBD` min bei `TBD` W.

### Phase 7 – Telemetrie & Kommunikation

- I²C/UART-Register, Messgenauigkeit (V/I/Temperatur) gegen Referenz.
- **Kriterien:** Genauigkeit ≤ `TBD` %; Protokoll stabil.

### Phase 8 – Geschütztes Herunterfahren

- Shutdown-Signal vor Erschöpfung; SBC fährt sauber herunter.
- **Kriterien:** Signalrechtzeitig, korrekte Polarität/Timing.

### Phase 9 – Robustheit (optional)

- Lastsprünge, Hot-Plug Ein/Aus, Dauerlauf, EMV-Vorprüfung.

## 3. Automatisierung

- `tests/test_*.py`: Bring-up und Abnahmetests über PyVISA/PyMeasure.
- `sigrok-cli`-Captures für Telemetrie, Ergebnis als Artefakt.
- Ausgabe: `pytest-html`-Report (z. B. `reports/`) je Durchlauf.
- Ergebnisse fließen zurück in `docs/` bzw. eine Ergebnistabelle.

## 4. Ergebnis-Tracking

| Test | Datum | Setup | Ergebnis | Kommentar |
| --- | --- | --- | --- | --- |
| | | | | |
