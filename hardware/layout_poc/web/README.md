# Interactive placement (browser UI)

A drag-and-drop placement board for TinyUPS. It draws the **placement graph**
from `extract.py` (components = courtyard rectangles, nets = current-coloured
edges) over the 150 × 140 mm outline and runs a **live d3-force** simulation that
you tune from the left-hand panel.

```sh
make place            # -> http://localhost:4097/   (node web/server.mjs)
```

Start point is the adopted baseline (`build/layout/leg-gv-sfdp.json`); the seed
drop-down loads any `leg-*` / `pos-*` / `raw-*` file from `build/layout/` plus
every placement saved into [`placements/`](placements/) (tracked).

## What it does

| | |
| --- | --- |
| **Drag a part** | pins it (`fx`/`fy`) — the engine treats it as fixed and solves the rest around it |
| **Right-click a part** | pin ↔ unpin |
| **Click a part** | inspect it (value, footprint, nets + currents, pads, and **which IC it belongs to**). The selection is an outline and a dashed line to its host; hover is what dims the rest, so a click never leaves the board faded |
| **Click empty space / Esc** | clear the selection |
| **Drag empty space / wheel** | pan / zoom |
| **Solve** | reheat the engine (alpha = 1) |
| **Scatter** | **random** start: uniform over the whole board, a *fresh* seed on every click, written back into the `SEED` field. Tick **reuse SEED** to re-run the same start (reproducibly) |
| **Reset** | restore the seed positions, keep only the terminals pinned |
| **Drag a parameter row** (by its `⠿` grip) | reorder the Engine panel — your important knobs on top. `↕ Default order` restores the built-in order |
| **Save** | write `hardware/layout_poc/placements/<name>.json` (**tracked**) |
| **Apply to board + DRC** | `apply.py` → `kicad-cli pcb drc` on the saved file, into `build/layout/` (untracked) |

The two power terminals (`1J1`, `5J2`) are always pinned (`anchor` in the graph).
Live metrics reproduce `render.py`'s set: HPWL, weighted HPWL, drawn wirelength,
courtyard **overlaps**, off-board count, power-path length, straightness, flow
`axisR`, and the input/output distances.

## Where the tuning and the placements live

| State | Lives in |
| --- | --- |
| Parameter **values** and the parameter **row order** | **`hardware/layout_poc/params.json`** — tracked in git, written by this UI on every change ([ADR-0010](../../../docs/decisions/0010-placement-params-source-of-truth.md)) |
| A **placement you save** (positions, pins, the seed and the params it ran with) | **`hardware/layout_poc/placements/<name>.json`** — tracked in git ([ADR-0011](../../../docs/decisions/0011-placements-are-tracked.md), [`placements/README.md`](../placements/README.md)) |
| View toggles, the seed you were last on, the save name | your browser (`localStorage`, key `tinyups.place.ui.v1`) |
| Graph, engine outputs, boards, DRC reports | `build/layout/` — **untracked** (generated) |

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

Saved sessions appear in the seed drop-down (marked `saved`, they win over a
same-named engine output) and can be loaded again — that is the way to resume a
placement, pins included.

## The model, and A/B testing it

The force model, the parameter defaults, the host assignment, the scatter
generator and the metric set live in **one module**,
[`web/public/model.js`](public/model.js) — imported by this UI *and* by the
headless A/B runner, so a number produced by one is produced by the other
(ADR-0013). `app.js` is the view: scene, interaction, persistence.

```sh
make ab                                             # 3 scatter seeds, host off vs 1.5/5
make ab AB='--runs 5 --config "a:D0=3" --config "b:D0=6"'
make ab AB='--start build/layout/pos-gv-sfdp.json --config "a:HOST_STR=0"'
node web/../ab.mjs --help                           # all options
```

It starts from a **neutral** state — a scatter (the UI's own generator, so a
headless start *is* a UI **Scatter**) or an engine output — because a hand
placement is half-solved by a human and its pins encode that intent; the runner
warns if you point it at `placements/` and ignores a start file's pins unless you
pass `--keep-pins`. Each config runs over N seeds and the table shows the
min–max range: overlapping ranges mean "run more seeds", not "no difference".

Per config it reports HPWL, drawn wire, courtyard overlaps, off-board, power-path
length, flow `axisR`, and the **fan statistics per controller**:

| column | meaning | want |
| --- | --- | --- |
| `d` | mean distance from the controller to its attached small parts | small — they belong together |
| `bias` | mean cosine of "part → controller" against "controller → board centre" | ~0; +1 = every part on the centre side (dragging to the middle) |
| `sp` | mean nearest-neighbour distance among those parts | up — they need room to fan out |

The same three numbers are in the UI's Metrics panel, so a session and a run can
be compared directly.

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

**Belongs-to** — a custom force, not a d3 one
- `HOST_STR` (0 = off, default 1.5) — every small part (`R/C/D/L`) is pulled onto
  a ring around the IC it belongs to. The host is derived from the netlist at
  load: the IC with the most *specific* shared net (`1/(k−1)` per net — a 2-pad
  boot cap scores 1.0, a 12-pad rail 0.09), ties broken by proximity; a part with
  no IC on any kept net takes the nearest IC. The inspector shows the choice
  (`belongs to 5U1 (net score 1.25)`) and a selected part draws a dashed line to
  its host; `place.assignHosts()` re-derives it after a big rearrangement.
- `HOST_D` ring radius in mm (default 5) — closer and the part is pushed out,
  farther and it is pulled in. **One-sided**: only the small part moves, so a
  controller keeps the position you gave it while its parts fan around it.
- `HOST_POWER` (default **off**) — off, only passives that are *not* on the power
  path get a ring; on, every small passive does, including the parts the power
  chain runs through. Measured on neutral starts: ringing those bends the
  input→output path (flow `axisR` 0.76 → 0.33) — see
  [`docs/history/0006`](../../../docs/history/0006-host-force-on-neutral-starts.md).

  This is the answer to "why do a controller's caps drift to the middle": the net
  links pull a part toward its *net's centroid* (a wide rail's centroid is where
  the power parts are), and `GND` — the one net that would tie every decoupling
  cap to its IC — is dropped, being a plane. Measurements, the rejected
  alternatives (centre pull, range-limited cliques) and the numbers:
  [`docs/history/0005`](../../../docs/history/0005-the-netlist-cannot-hold-satellites.md),
  [ADR-0012](../../../docs/decisions/0012-belongs-to-force.md).

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

- **Read:** `build/layout/graph.json` + a seed position file in `build/layout/`
  (`leg-gv-sfdp.json` = the adopted baseline by default) or in `placements/`.
- **Write (generated, untracked):** `build/layout/interactive.kicad_pcb` + DRC on
  demand. Nothing else in `build/` is read back by the UI.
- **Write (tracked, on purpose):**
  - `hardware/layout_poc/params.json` — the engine tuning
    ([ADR-0010](../../../docs/decisions/0010-placement-params-source-of-truth.md));
  - `hardware/layout_poc/placements/<name>.json` — one file per **Save**
    ([ADR-0011](../../../docs/decisions/0011-placements-are-tracked.md)).
- Replacing the tracked board / `gen_pcb.py` still needs an ADR — see
  `docs/decisions/0009-interactive-placement.md`.

## Files

| File | Role |
| --- | --- |
| `web/public/model.js` | **the model**: defaults, geometry, every force, host assignment, scatter, metrics — shared with `ab.mjs` |
| `web/server.mjs` | dependency-free Node HTTP server: UI, graph, seeds, params, placements, vendor, save/apply |
| `web/public/index.html` | page + import map |
| `web/public/app.js` | the view: scene, drag/pin, params panel, metrics table, persistence |
| `ab.mjs` | headless A/B runner over neutral starts (owns the model, not a copy of it) |
| `web/public/style.css` | panel + board styling |
| `params.json` | the tracked engine tuning, edited from the Engine panel |
| `placements/` | the tracked placements you save (one `<name>.json` each) |
