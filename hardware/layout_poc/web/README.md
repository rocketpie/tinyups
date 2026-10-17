# Interactive placement (browser UI)

A drag-and-drop placement board for TinyUPS. It draws the **placement graph**
from `extract.py` (components = courtyard rectangles, nets = current-coloured
edges) over the 150 × 140 mm outline and runs a **live d3-force** simulation that
you tune from the left-hand panel.

```sh
make place            # -> http://localhost:4097/   (node web/server.mjs)
```

Start point is the adopted baseline (`build/layout/leg-gv-sfdp.json`); the seed
drop-down loads any `leg-*` / `pos-*` / `raw-*` / `interactive-*` file from
`build/layout/`.

## What it does

| | |
| --- | --- |
| **Drag a part** | pins it (`fx`/`fy`) — the engine treats it as fixed and solves the rest around it |
| **Right-click a part** | pin ↔ unpin |
| **Click a part** | inspect it (value, footprint, nets + currents, pads drawn on the board). The selection is an outline; hover is what dims the rest, so a click never leaves the board faded |
| **Click empty space / Esc** | clear the selection |
| **Drag empty space / wheel** | pan / zoom |
| **Solve** | reheat the engine (alpha = 1) |
| **Scatter** | **random** start: uniform over the whole board, a *fresh* seed on every click, written back into the `SEED` field. Tick **reuse SEED** to re-run the same start (reproducibly) |
| **Reset** | restore the seed positions, keep only the terminals pinned |
| **Drag a parameter row** (by its `⠿` grip) | reorder the Engine panel — your important knobs on top. `↕ Default order` restores the built-in order |
| **Save** | write `build/layout/interactive-<name>.json` (engine-output shape, so `render.py`/`apply.py` accept it) |
| **Apply to board + DRC** | `apply.py` → `kicad-cli pcb drc` on the saved file |

The two power terminals (`1J1`, `5J2`) are always pinned (`anchor` in the graph).
Live metrics reproduce `render.py`'s set: HPWL, weighted HPWL, drawn wirelength,
courtyard **overlaps**, off-board count, power-path length, straightness, flow
`axisR`, and the input/output distances.

## Where the tuning lives

| State | Lives in |
| --- | --- |
| Parameter **values** and the parameter **row order** | **`hardware/layout_poc/params.json`** — tracked in git, written by this UI on every change ([ADR-0010](../../../docs/decisions/0010-placement-params-source-of-truth.md)) |
| View toggles, the seed you were last on, the save name | your browser (`localStorage`, key `tinyups.place.ui.v1`) |
| Placement (positions, pin flags) **and** the params that produced it | `build/layout/interactive-<name>.json` — written by **Save** |

Parameter values are resolved as **built-in defaults < `params.json` < the
`params` of a seed you pick deliberately** (drop-down, **Load**, `?seed=`).
A seed's params are a session override — they reach the file only once you change
a parameter. `↺ Default values` resets the values and writes that; `↕ Default
order` drops the `order` override.

Writes are debounced (700 ms) and flushed when the tab closes. Because the file
is tracked, an experiment is undone with `git checkout
hardware/layout_poc/params.json`, and `git log -p` on it is the record of which
knobs turned out to matter. A key may be deleted from the file to fall back to
its built-in default; `_comment` is preserved.

`params.json` is the *human's* tuning: `engines/d3force.mjs` reads the same key
names from the environment and does **not** read the file yet, so a `make layout`
run and a UI session can still be configured differently.

Saved sessions appear in the seed drop-down (`interactive-*`) and can be loaded
again — that is the way to resume a placement, pins included.

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
  `SEED` for *Scatter* (a new random value on every click unless **reuse SEED**
  is ticked, in which case the field is the seed — that is how a start you like
  is reproduced)

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
- **Write:** `build/layout/interactive-<name>.json` (untracked output). Applying
  to a board writes `build/layout/interactive.kicad_pcb` and runs DRC.
- **Write (tracked):** `hardware/layout_poc/params.json`, the engine tuning —
  the one file in `hardware/` this UI changes, on purpose
  ([ADR-0010](../../../docs/decisions/0010-placement-params-source-of-truth.md)).
- Replacing the tracked board / `gen_pcb.py` still needs an ADR — see
  `docs/decisions/0009-interactive-placement.md`.

## Files

| File | Role |
| --- | --- |
| `web/server.mjs` | dependency-free Node HTTP server: UI, graph, seeds, params, vendor, save/apply |
| `web/public/index.html` | page + import map |
| `web/public/app.js` | scene, drag/pin, d3-force integration, metrics |
| `web/public/style.css` | panel + board styling |
| `params.json` | the tracked engine tuning, edited from the Engine panel |
