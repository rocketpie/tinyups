# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ generated, ERC-clean (124 parts, 115 nets) |
| Placement | ✅ **PoC concluded** — graph-derived placement beats the hand floorplan and is adopted as the **baseline** ([`hardware/layout_poc/README.md`](hardware/layout_poc/README.md)) |
| Routing | ⬜ not routed (nothing has been routed on the new baseline) |
| Power / ampacity | ⬜ `make power` FAIL — no pours yet |
| Test plan / DVT | not started |

Commands: `make layout` · `make baseline` · `make mermaid` (plus the usual
`erc`/`drc`/`netlist`/`bom`/`render`).

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

**Web-based, user-interactive placement.**

A browser UI where the user places/moves components by hand, starting from
`build/layout/baseline.kicad_pcb`, with live feedback, writing the result back
to a KiCad board. The PoC code is directly reusable: `extract.py` (components,
courtyards, pad geometry, nets), `render.py` (SVG, mnemonic labels `CHG-2R11`,
legend, colour = net current), `legalize.py` (rotation + overlap logic),
`compare.py` (metrics).

Things to settle first:

1. **Which board is the source of truth** for the session — load
   `baseline.kicad_pcb`, and decide where edits are written back to (a new file
   under `build/layout/`, or the tracked board).
2. **Live legality** — courtyard overlap warnings as the user drags, using the
   *KiCad* courtyard geometry (see the Y-down bug in the PoC README: our own
   bbox metric was not a substitute for real DRC).
3. **Feedback to show** — ratsnest per net, HPWL (live), the power path
   highlight, net current by colour/width.
4. **Scope** — drag/no-overlap only, or does it also rotate, snap to grid, lock
   parts, and run the legaliser on demand?

## Key files

| File | Role |
| --- | --- |
| `hardware/layout_poc/README.md` | **the PoC result + method** — read this first |
| `hardware/layout_poc/extract.py` | netlist → placement graph (courtyards, pads, nets, IPC-2221 widths) |
| `hardware/layout_poc/legalize.py` | rotation, de-overlap, grid snap — the reusable part |
| `hardware/layout_poc/render.py` | SVG/PNG renders + metrics (reusable for the UI) |
| `hardware/layout_poc/run_all.sh`, `compare.py` | run/score all engines |
| `hardware/layout_poc/apply.py` | placement → full KiCad board (+DRC) |
| `hardware/gen_pcb.py` | the hand placer (fallback), still generates the tracked board |
| `Makefile` | `layout`, `baseline`, `mermaid`, plus the usual check targets |
