# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ ERC-clean (124 parts, 115 nets), now maintained in KiCad |
| Placement | ✅ `try5` adopted as `hardware/tinyups.kicad_pcb`; the only placement tool is the interactive [UI](ui/placement/README.md) |
| Routing | 🟡 board is placed + poured, **unrouted** — run `make route` |
| Power / ampacity | ⬜ gate to verify — `make power`; pours are on the board |
| Test plan / DVT | not started |

Commands: `make place` (UI) · `make drc` · `make render` · `make route` ·
`make sim` · `make power`.

`fixed3` + the `VBUS`→`VIN_SYS` charger-input fix is applied: `2R1`/`2U1`
are on `VIN_SYS`, the `VBUS` pour is gone, placement is DRC-clean (0
courtyard/clearance/short). Next: re-place `2R1`/`2U1` and the power path,
then route. `route.py` now stops after 10 min without a >5 % score gain.
The UI has the `show power pours` overlay from the last apply. `make sense`
now gates the Kelvin taps: fixed3's five loops are 19–73 mm from their
controllers (35–200 % shared-copper upper bound) — re-place them.

## Next steps

1. **Verify the power path** — `make power` (ampacity) and `make channels`
   (pour clearance); this is the blocker.
2. **Route** — `make route` from the main board, then `make drc`.
3. **Keep signals off `In1.Cu`** — it is a thin GND return that needs to carry
   the 20 A as well.

## Where things came from

The graph-placement PoC (sfdp/dagre/ELK engines, automatic placement) is
concluded and archived in [`docs/history/layout_poc/`](docs/history/layout_poc/).
The current placement was tuned by hand in the UI; the board itself is the
source of truth.
