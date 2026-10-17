# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ generated, ERC-clean (124 parts, 115 nets) |
| Placement | ✅ **PoC concluded** — graph-derived placement beats the hand floorplan and is adopted as the **baseline** ([`hardware/layout_poc/README.md`](hardware/layout_poc/README.md)) |
| Interactive placement | ✅ **built** — browser UI, drag/pin + live d3-force, reorderable params persisted in the tracked [`hardware/layout_poc/params.json`](hardware/layout_poc/params.json) ([`hardware/layout_poc/web/README.md`](hardware/layout_poc/web/README.md), [ADR-0010](docs/decisions/0010-placement-params-source-of-truth.md)); saved sessions reload from the seed list |
| Routing | ⬜ not routed (nothing has been routed on the new baseline) |
| Power / ampacity | ⬜ `make power` FAIL — no pours yet |
| Test plan / DVT | not started |

Commands: `make layout` · `make baseline` · `make place` · `make mermaid` (plus
the usual `erc`/`drc`/`netlist`/`bom`/`render`).

## The baseline

**`build/layout/baseline.kicad_pcb`** — 150×140 mm, 124 parts, produced by
graphviz `sfdp` → free-orientation search → legalise (rotate, de-overlap, grid
snap). Regenerate with:

```sh
make layout && make baseline
```

* **−60 % pre-route HPWL** vs the hand floorplan (3295 vs 8304 mm).
* **KiCad DRC: 0 courtyard overlaps, 0 board-edge violations.**
* Cleanest main power path by eye (no crossings, visible branching); neato is
  second. The hand placer in `gen_pcb.py` is now a fallback, not the target.

Known caveats (in full in the PoC README): the numbers are **pre-route proxies**
— the board has never been routed; rotation is decided *after* placement;
signal parts are only loosely constrained.

## Next step (single)

**Port the engine fix + clamp into `engines/d3force.mjs`, then re-score and
route.**

The interactive UI is built (`make place`, ADR-0009) and it exposed a defect
that makes the published `d3-force` numbers wrong — see
[`docs/history/0002-d3force-inert-link-params.md`](docs/history/0002-d3force-inert-link-params.md).
So:

1. **Fix `engines/d3force.mjs`** (and `d3force_incremental.mjs`) — wire
   `.distance()`/`.strength()`, add the velocity clamp, run `make layout`, refresh
   the score table in the PoC README.
2. Then do the thing the whole field agrees on and the PoC never did: **route the
   baseline** (FreeRouting via `route.py`) and report **routed wirelength, vias
   and DRVs** (`routing_report.py`). That, not HPWL, is the yardstick.
3. Optional human-in-the-loop: does a hand-tuned interactive placement beat the
   automatic one *after routing*?

Interactive placement can be used right now for eyeballing/experiments, but its
metrics are pre-route proxies and its legality is advisory (position-only; still
run `legalize.py` / DRC for a legal board).

## Key files

| File | Role |
| --- | --- |
| `hardware/layout_poc/README.md` | **the PoC result + method** — read this first |
| `hardware/layout_poc/web/README.md` | **the interactive UI** + its parameters |
| `hardware/layout_poc/web/server.mjs` | Node server (port 4097): UI, graph, save/apply |
| `hardware/layout_poc/extract.py` | netlist → placement graph (courtyards, pads, nets, IPC-2221 widths) |
| `hardware/layout_poc/legalize.py` | rotation, de-overlap, grid snap — the reusable part |
| `hardware/layout_poc/render.py` | SVG/PNG renders + metrics (reusable for the UI) |
| `hardware/layout_poc/run_all.sh`, `compare.py` | run/score all engines |
| `hardware/layout_poc/apply.py` | placement → full KiCad board (+DRC) |
| `hardware/gen_pcb.py` | the hand placer (fallback), still generates the tracked board |
| `Makefile` | `layout`, `baseline`, `mermaid`, plus the usual check targets |
