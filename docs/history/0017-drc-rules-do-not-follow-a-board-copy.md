# 0017 — DRC rules do not follow a board copy

**What:** `build/layout/board.kicad_pcb` (written by `make place-apply` / the UI)
and every routed board under `build/` were checked **without** the custom rules.
KiCad resolves `<board>.kicad_dru` from a sidecar named after the board, and the
copies are named `board.*` and `tinyups-routed.*` — never `tinyups.*`. The 5U1
pads then read as 21 clearance errors, one per adjacent pad pair.

**Why:** 5U1 (LM5176, QFN-28, 0.4 mm pitch) uses the IPC land pattern's 0.25 mm
pads → a **0.15 mm** copper gap between neighbours. That is 24 perimeter pairs,
minus 3 same-net pairs (10/11 `N_ISNS`, 20/21 `VCC`, 27/28 `VIN_SYS`) = exactly
21. With the JLCPCB rule
loaded (`JLCPCB min clearance (min 0.127mm)`) 0.15 mm is clean — 5.9 mil is
above the standard 5 mil floor of NFR-9/ADR-0008. Without it the netclass
`Default` clearance (0.2 mm) applies to every pair. `kicad-cli pcb drc` has no
flag to point at a rules file; the filename is the only handle.

Measured, same board file, only the sidecar renamed:

| board | sidecar next to it | clearance items |
| --- | --- | ---: |
| `hardware/tinyups.kicad_pcb` | `tinyups.kicad_dru` | 0 |
| `build/layout/board.kicad_pcb` | – | 21 |
| `board.kicad_pcb` | `tinyups.kicad_dru` | 21 |
| `board.kicad_pcb` | `board.kicad_dru` | 0 |

The 21 also account for 21 of the 29 DRC items in
`reports/routed-drc-try5.rpt` (that run was `try5-routed.kicad_pcb`).

**Status:** fixed — `apply.py` and the `route` target copy
`hardware/tinyups.kicad_dru` to `<derived board>.kicad_dru`. Derived board: 73 →
52 DRC items, the 21 clearance entries gone; `route-feedback.json` and the UI
panel stop listing them. The tracked board is unaffected (0 clearance items
before and after). `make check` still stops at the pre-existing 52 warnings
(44 `isolated_copper`, 8 silk) and the open `power` blocker (11/11 FAIL).

**Follow-up:** the blanket 0.127 mm rule also silences the 0.2 mm *design
preference* for tracks/vias/pours; the `route` target's summary line already
labels those "accepted". Scoping the rule to pads (`A.Type == 'Pad' && B.Type ==
'Pad'`) is the lever if the 0.2 mm floor should hold for routing — note that
`A.Reference`/`A.Footprint` conditions did not match these pads in testing.
