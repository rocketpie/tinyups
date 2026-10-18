# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ generated, ERC-clean (124 parts, 115 nets) |
| Placement | ✅ PoC concluded — graph-derived placement beats the hand floorplan and is the **baseline** ([`hardware/layout_poc/README.md`](hardware/layout_poc/README.md)); the interactive model has since gained a **belongs-to** ring for a controller's small parts ([ADR-0012](docs/decisions/0012-belongs-to-force.md), measurement: [history 0006](docs/history/0006-host-force-on-neutral-starts.md)) |
| Model A/B | ✅ **wired** — `make ab` (`hardware/layout_poc/ab.mjs`) scores configs on *neutral* starts over N seeds; force model + metrics live once in `hardware/layout_poc/web/public/model.js`, shared with the UI ([ADR-0013](docs/decisions/0013-one-model-and-neutral-ab.md)) |
| Interactive placement | ✅ built — `make place` (port 4097); tuning in the tracked [`params.json`](hardware/layout_poc/params.json), saves in [`placements/`](hardware/layout_poc/placements/) (ADR-[0010](docs/decisions/0010-placement-params-source-of-truth.md)/[0011](docs/decisions/0011-placements-are-tracked.md)); [`web/README.md`](hardware/layout_poc/web/README.md) |
| Routing | 🟡 `try5` routed, but **Power is still traces** |
| Power / ampacity | ⬜ **the blocker** — 11/11 FAIL |
| Test plan / DVT | not started |

Commands: `make layout` · `make baseline` · `make place` · `make ab` ·
`make mermaid` · `make route` (plus the usual `erc`/`drc`/`netlist`/`bom`/`render`).

## Next steps

1. **Make the power path work — this is the blocker.** 
3. **Keep signals off `In1.Cu`** it's a thin GND return that needs to handle the 20A as well. 

## The baseline

