# Interactive placement (browser UI)

A drag-and-drop placement board for TinyUPS. It draws the **placement graph**
from `extract.py` (components = courtyard rectangles, nets = current-coloured
edges) over the 150 × 140 mm outline and runs a **live d3-force** simulation that
you tune from the left-hand panel.

```sh
make place            # -> http://localhost:4097/   (node web/server.mjs)
```

Start point is the adopted baseline (`build/layout/leg-gv-sfdp.json`); the seed
drop-down loads any `leg-*` / `pos-*` / `raw-*` file from `build/layout/`.

## What it does

| | |
| --- | --- |
| **Drag a part** | pins it (`fx`/`fy`) — the engine treats it as fixed and solves the rest around it |
| **Right-click a part** | pin ↔ unpin |
| **Click a part** | inspect it (value, footprint, nets + currents, pads drawn on the board) |
| **Drag empty space / wheel** | pan / zoom |
| **Solve** | reheat the engine (alpha = 1) |
| **Scatter** | random start (RNG seed from the panel), then solve |
| **Reset** | restore the seed positions, keep only the terminals pinned |
| **Save** | write `build/layout/interactive-<name>.json` (engine-output shape, so `render.py`/`apply.py` accept it) |
| **Apply to board + DRC** | `apply.py` → `kicad-cli pcb drc` on the saved file |

The two power terminals (`1J1`, `5J2`) are always pinned (`anchor` in the graph).
Live metrics reproduce `render.py`'s set: HPWL, weighted HPWL, drawn wirelength,
courtyard **overlaps**, off-board count, power-path length, straightness, flow
`axisR`, and the input/output distances.

## Which placement engine, and why d3-force

`d3-force 3.0.0` is already vendored by the PoC (`node_modules/`, served to the
browser through an import map) and it is **the** interactive choice: it is a
tick-by-tick simulation, so it can run while you drag, and its parameters are
exactly the physical knobs a layout needs (link force, link distance, repulsion,
collision, centring). The other available engines are the wrong shape for this:

| engine | available here | fit for interactive drag |
| --- | --- | --- |
| **d3-force** | ✅ vendored | ✅ incremental, pins parts natively, live tunables |
| elkjs (`force`, `stress`, `layered`, …) | ✅ vendored | ✋ layered, batch, no native pins |
| dagre / graphviz (`sfdp`, `neato`, `dot`) | ✅ | ✋ batch solvers, no live interaction |
| SA-PCB (OpenROAD) | ✖ not installed | annealing — good with rotation, but a separate C++ tool |

The server only hosts files + a save/apply API; the solver runs in the tab, so
the same `node web/server.mjs` also works headless server-side if you ever want
batch runs.

## Parameters

Every slider maps to a force in `engines/d3force.mjs` (same key names, so an
environment-tuned PoC run and a session here describe the same config).

**Links** — `forceLink`
- `SIG_STR` signal trace link force — strength for a zero-width net
- `POW_STR` power trace link force — strength reached at a full `WREF`-wide trace
- `WREF` reference width (mm) — the IPC-2221 width of a 20 A net (18.71 mm)
- `D0` link rest distance (mm), `DK` extra distance per unit width, `DMAX` cap
- `LINK_ITER` link constraint iterations

**Spread** — `forceManyBody` / `forceCollide` / `forceX|Y` / bounds
- `CHARGE`, `CHARGE_SIZE`, `CHARGE_MAX` repulsion
- `COLLIDE_PAD` courtyard clearance; `RECT_COLLIDE` rectangle vs d3 circle
- `CENTER_X`, `CENTER_Y` pull to board centre; `BOUND` keep-in force

**Solver**
- `ITERS` run length (alpha decay), `MAX_V` velocity clamp, `VEL_DECAY`,
  `SEED` for *Scatter*

**Implementation note.** The link forces are applied with
`forceLink.distance()`/`.strength()`. d3-force **caches** every force's
strength/distance/radius at `initialize()` time, and it ignores the per-link
`distance`/`strength` *properties*, so the UI re-sets each accessor whenever a
parameter changes — that is what makes a slider effective mid-run. A velocity
clamp (`MAX_V`, default 3 mm/tick) keeps the wired link model stable from a dense
start. Background and measurements: [`docs/history/`](../../../docs/history/).

## Source of truth, and where edits go

- **Read:** `build/layout/graph.json` + a seed position file in
  `build/layout/` (`leg-gv-sfdp.json` = the adopted baseline by default).
- **Write:** `build/layout/interactive-<name>.json` (untracked output). Nothing
  in `hardware/` is touched. Applying to a board writes
  `build/layout/interactive.kicad_pcb` and runs DRC.
- Replacing the tracked board / `gen_pcb.py` still needs an ADR — see
  `docs/decisions/0009-interactive-placement.md`.

## Files

| File | Role |
| --- | --- |
| `web/server.mjs` | dependency-free Node HTTP server: UI, graph, seeds, vendor, save/apply |
| `web/public/index.html` | page + import map |
| `web/public/app.js` | scene, drag/pin, d3-force integration, metrics |
| `web/public/style.css` | panel + board styling |
