# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ generated, ERC-clean (124 parts, 115 nets) |
| Placement | ✅ PoC concluded — graph-derived placement beats the hand floorplan and is the **baseline** ([`hardware/layout_poc/README.md`](hardware/layout_poc/README.md)); the interactive model has since gained a **belongs-to** ring for a controller's small parts ([ADR-0012](docs/decisions/0012-belongs-to-force.md), measurement: [history 0006](docs/history/0006-host-force-on-neutral-starts.md)) |
| Model A/B | ✅ **wired** — `make ab` (`hardware/layout_poc/ab.mjs`) scores configs on *neutral* starts over N seeds; force model + metrics live once in `hardware/layout_poc/web/public/model.js`, shared with the UI ([ADR-0013](docs/decisions/0013-one-model-and-neutral-ab.md)) |
| Interactive placement | ✅ built — `make place` (port 4097); tuning in the tracked [`params.json`](hardware/layout_poc/params.json), saves in [`placements/`](hardware/layout_poc/placements/) (ADR-[0010](docs/decisions/0010-placement-params-source-of-truth.md)/[0011](docs/decisions/0011-placements-are-tracked.md)); [`web/README.md`](hardware/layout_poc/web/README.md) |
| Routing | ⬜ **nothing routed yet** — route **`placements/try4.json`** (HPWL 3940, wire 4024, 0 overlaps, axisR 0.66) |
| Power / ampacity | ⬜ `make power` FAIL — no pours yet |
| Test plan / DVT | not started |

Commands: `make layout` · `make baseline` · `make place` · `make ab` ·
`make mermaid` (plus the usual `erc`/`drc`/`netlist`/`bom`/`render`).

## Next steps

1. **Route and validate `try4`** — the thing the whole field agrees on and this
   project has never done. `route.py` (FreeRouting) on
   `hardware/layout_poc/placements/try4.json`, then `routing_report.py` for
   **routed wirelength, via count and DRVs**; `make place-apply F=…placements/try4.json`
   gives the KiCad DRC verdict on the same board. That, not HPWL, decides whether
   a placement is good — see [history 0006](docs/history/0006-host-force-on-neutral-starts.md)
   for why the pre-route proxies cannot be trusted alone.
2. **A/B the model before believing any force change** — `make ab` on neutral
   starts, several seeds, and treat overlapping ranges as "inconclusive".
   Open questions worth a run: `HOST_STR`/`HOST_D` sweep (`HOST_POWER` off vs on),
   `D0`/`DK` (rest length), `CHARGE` (currently 0 in the tracked tuning).
3. **Port the model into `engines/d3force.mjs`** (and `d3force_incremental.mjs`) so
   the headless engines *import* `web/public/model.js` instead of re-implementing
   it — that retires the last copy and makes `make layout` and the UI the same
   model. The published `d3-force` numbers are still wrong today
   ([history 0002](docs/history/0002-d3force-inert-link-params.md)); re-score the
   table in the PoC README afterwards.
4. Optional human-in-the-loop: does a hand-tuned placement (`try4`) beat the
   automatic one **after routing**?

Legality of anything from the UI is advisory (position-only): run `legalize.py`
and DRC before calling a board good.

## The baseline

**`build/layout/baseline.kicad_pcb`** — 150×140 mm, 124 parts, produced by
graphviz `sfdp` → free-orientation search → legalise (rotate, de-overlap, grid
snap). Regenerate with `make layout && make baseline`.

* **−60 % pre-route HPWL** vs the hand floorplan (3295 vs 8304 mm).
* **KiCad DRC: 0 courtyard overlaps, 0 board-edge violations.**
* Cleanest main power path by eye (no crossings, visible branching); neato is
  second. The hand placer in `gen_pcb.py` is now a fallback, not the target.

Known caveats (in full in the PoC README): the numbers are **pre-route proxies**;
rotation is decided *after* placement; signal parts are only loosely constrained.

## Key files

| File | Role |
| --- | --- |
| `hardware/layout_poc/README.md` | **the PoC result + method** — read this first |
| `hardware/layout_poc/web/README.md` | **the interactive UI** + its parameters + A/B |
| `hardware/layout_poc/web/public/model.js` | **the model** (defaults, forces, host assignment, metrics) — UI *and* A/B runner import it |
| `hardware/layout_poc/ab.mjs` | A/B runner over neutral starts (`make ab`) |
| `hardware/layout_poc/params.json` | the tracked tuning (edited from the UI) |
| `hardware/layout_poc/placements/` | the tracked placements (`try1`…`try4`; `try4` is the routing candidate) |
| `hardware/layout_poc/web/server.mjs` | Node server (port 4097): UI, graph, saves, tuning |
| `hardware/layout_poc/extract.py` | netlist → placement graph (courtyards, pads, nets, IPC-2221 widths) |
| `hardware/layout_poc/legalize.py` | rotation, de-overlap, grid snap — the reusable part |
| `hardware/layout_poc/render.py` | SVG/PNG renders + metrics (independent python metric check) |
| `hardware/layout_poc/apply.py` | placement → full KiCad board (+ DRC) |
| `hardware/layout_poc/route.py`, `routing_report.py` | FreeRouting + the routed-wirelength / via / DRV report — **step 1** |
| `hardware/layout_poc/run_all.sh`, `compare.py` | run/score all engines |
| `hardware/gen_pcb.py` | the hand placer (fallback), still generates the tracked board |
| `Makefile` | `layout`, `baseline`, `place`, `ab`, `mermaid`, plus the usual check targets |
