# 0009 – Interactive placement UI (browser, d3-force)

- Status: proposed

## Context

The placement PoC ([`hardware/layout_poc/README.md`](../../hardware/layout_poc/README.md))
concluded with a graph-derived baseline (`build/layout/baseline.kicad_pcb`,
150 × 140 mm, 124 parts, 0 courtyard/edge DRC violations) and named the next
step: **a web-based, user-interactive placement** that starts from the baseline,
lets a human move parts by hand with live feedback, and writes a KiCad board.

The RESUME questions to settle were: which board is the source of truth, where
edits are written back, what feedback to show, and how much the tool should do
(drag only vs. rotate/snap/lock/solve).

Building it surfaced a defect in the PoC engine's link model — its per-link
`distance`/`strength` parameters were never applied — which point 5 below fixes.
The finding, its numbers and the surrounding gotchas are recorded in
[`docs/history/0002-d3force-inert-link-params.md`](../history/0002-d3force-inert-link-params.md).

## Decision

1. **Build a browser UI served by a dependency-free Node server** on port
   **4097** (`make place`, `hardware/layout_poc/web/`). It draws the placement
   graph (courtyards + current-coloured net edges) over the board outline.
2. **The engine is d3-force**, vendored (already in `node_modules/`) and run in
   the browser so it simulates *while* you drag. It is the right engine for
   interaction: incremental, pins parts natively (`fx`/`fy`), and its parameters
   are the physical knobs. Layered engines (dagre/ELK/graphviz) are batch and
   ignore pins; SA-PCB is not installed.
3. **A dragged part is pinned** (`fx`/`fy`); the engine solves around it.
   Right-click releases it. `1J1`/`5J2` stay pinned (graph anchors).
4. **All engine parameters are exposed and editable** with the same key names as
   `engines/d3force.mjs` (signal/power link force, link distance, repulsion,
   collision, centring, run length, …). d3 caches force accessors, so the UI
   re-sets them on every change to make sliders effective mid-run.
5. **Fix the link model and make it stable.** Wire `forceLink.distance()/
   .strength()` as intended, and add a **velocity clamp** (`MAX_V`, default
   3 mm/tick) — without it the wired 2–26 mm rest lengths diverge from a dense
   start. This is a behaviour change to the engine, not just a UI.
6. **Source of truth / write-back.** Read `build/layout/graph.json` + a seed in
   `build/layout/` (baseline `leg-gv-sfdp.json` by default). Write only to
   `build/layout/interactive-*.json` (untracked) and, on demand,
   `build/layout/interactive.kicad_pcb` + DRC. **`hardware/` and the tracked
   board are not touched.**
7. **Scope for now: position only.** Rotation comes from the seed; snapping and
   the full legalisation pass are left to `legalize.py`. Overlap is reported live
   (courtyard AABBs) and fought by a rectangular collision force, but the tool
   does not itself guarantee DRC legality.

## Consequences

- The interactive phase exists: baseline → drag/tune → save → render/DRC, all
  via `make place` and the `place-render` / `place-apply` targets.
- The PoC's `d3-force` scores predate the link-model fix and must be re-scored
  once it is ported into `engines/d3force.mjs`; the measurements are in
  [`docs/history/0002-d3force-inert-link-params.md`](../history/0002-d3force-inert-link-params.md).
- Port 4097 is added to `.devcontainer/devcontainer.json` (`runArgs` +
  `forwardPorts`); a running container must be **recreated** for the published
  port to take effect, or the port forwarded from the editor.
- Interactive legality is *advisory*. The real gate remains `kicad-cli pcb drc`
  on an applied board; `legalize.py` is still the piece that guarantees 0
  overlaps.
- Requirements touched: FR-1, FR-3, NFR-1, NFR-9 (placement quality / fab tier),
  via a faster human-in-the-loop placement loop.

## Open questions

- Does a human-assisted d3-force placement beat the fully automatic baseline on
  **routed** wirelength/vias (the field's yardstick, FreeRouting + KiCad DRC)?
- Rotation in the loop (currently position-only) — joint pos/orient was the
  PoC's gap #2 and the UI does not close it.
- Should the fix + clamp be ported into `engines/d3force.mjs` and
  `fitpos`/`legalize` re-scored, and does the improved HPWL survive routing?
- Write-back to the tracked board / `gen_pcb.py` still needs its own decision.
