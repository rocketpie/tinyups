# Interactive placement (browser UI)

A drag-and-drop placement board for TinyUPS. It draws the **placement graph**
from `extract.py` (components = courtyard rectangles, nets = current-coloured
edges) over the 150 × 140 mm outline and runs a **live d3-force** simulation that
you tune from the left-hand panel.

This is the only placement tool in the project: start from the main board's
placement, tune the forces, and save when the result is good. Everything after
placement is the normal flow — `make drc`, `make render`, `make route`, `make
sim`.

```sh
make place            # -> http://localhost:4097/   (node ui/placement/server.mjs)
```

The start point is `placements/main.json` — a snapshot of the main board, taken
with `make place-seed` — so the simulation begins from exactly what
`hardware/tinyups.kicad_pcb` is now. The seed drop-down also loads any `leg-*` /
`pos-*` / `raw-*` file from `build/layout/` plus every placement saved into
`placements/` (tracked).

## What it does

| | |
| --- | --- |
| **Drag a part** | pins it (`fx`/`fy`) — the engine treats it as fixed and solves the rest around it. While **Paused** the solver does not run: the dragged part moves and nothing else |
| **Right-click a part** | pin ↔ unpin |
| **Pin selected / Unpin selected** | fix or release the selected part **in place** — a click-and-button, no drag, so the position does not change |
| **Engine heading ▾** | collapse / expand the whole Engine body (view toggles, parameter list, notes); the state is remembered |
| **pad-level nets** | draw the real ratsnest — an MST over the **pads** of every net, coloured by current and sized by the required 2 oz width — instead of the force model's part-centre links. Off = the abstract part links |
| **mark parts too close** | amber courtyard outline = a different-net pad is inside the 0.2 mm rule; red = the courtyard overlaps another part. Off = no warning outlines |
| **Route legend rows** | click a row to show / hide that marker class on the board |
| **Click a part** | inspect it (value, footprint, nets + currents, pads, and **which IC it belongs to**). The selection is an outline and a dashed line to its host; hover is what dims the rest, so a click never leaves the board faded |
| **Click empty space / Esc** | clear the selection |
| **Drag empty space / wheel** | pan / zoom |
| **Pause** | freeze the solver. Nothing advances it — dragging a part, pin/unpin or a parameter change only takes effect where you touched it. **Solve**, **Scatter** and **Reset** are explicit starts and clear the pause |
| **Solve** | reheat the engine (alpha = 1) |
| **Scatter** | **random** start: uniform over the whole board, a *fresh* seed on every click, written back into the `SEED` field. Tick **reuse SEED** to re-run the same start (reproducibly) |
| **Reset** | restore the seed positions, keep only the terminals pinned |
| **Drag a parameter row** (by its `⠿` grip) | reorder the Engine panel — your important knobs on top. `↕ Default order` restores the built-in order |
| **Save** | write `ui/placement/placements/<name>.json` (**tracked**) |
| **Apply to board + DRC** | `apply.py` → `kicad-cli pcb drc` on the saved file, then `route_feedback.py` → `build/layout/route-feedback.json`, into `build/layout/` (untracked); the tracked `hardware/tinyups.kicad_pcb` is never modified. The `hardware/tinyups.kicad_dru` rules are copied next to the saved board (`build/layout/board.kicad_dru`) — KiCad only reads custom rules from a sidecar named after the board. The Routing panel refreshes from that file |

The two power terminals (`1J1`, `5J2`) are always pinned (`anchor` in the graph).
The board can draw two net views. **Part links** (the default in older sessions)
is the force model's abstract MST: a line between part centres, sized by the
1 oz model width. **Pad-level nets** is the router's view: an MST over the
**pads** of each net, so the line ends where copper ends, coloured by the net
current and sized by the required **2 oz** width. It is display-only — the
solver keeps the part-level springs — and it reproduces the DRC's unrouted
pairs pad-for-pad.

Live metrics reproduce `render.py`'s set: HPWL, weighted HPWL, drawn wirelength,
courtyard **overlaps**, off-board count, power-path length, straightness, flow
`axisR`, and the input/output distances. Two placement-side route proxies sit
beside them: **minimum pad-to-pad clearance** (different nets, 0.2 mm design
rule) and the number of parts below it. The inspector shows the same per part,
the selected part's nearest offender, and the net's **required** 2 oz width
(9.4 mm for 20 A, `required` in the graph) next to the force model's width.

## Route feedback

`make route` ends with `hardware/route_feedback.py`, which reads the routed
board plus its DRC report and writes `build/layout/route-feedback.json`. The
server exposes it as `/api/route-feedback`; the **Routing** panel reads it and
draws the last route's verdict on the placement:

| Marker | Meaning |
| --- | --- |
| red dashed line | an **unrouted connection** (`unconnected_items`) between the two DRC items |
| amber line | a **clearance violation**, with required/actual in the tooltip |
| magenta ring | a high-current net whose measured pour **channel** is narrower than its IPC-2221 width (`power_channel.py`) |

The panel summarizes tracks, vias, min trace, unrouted and clearance counts, and
lists each power rail's measured channel against its requirement. The three
legend rows are clickable, so on a fully unrouted board the 284 red lines can be
hidden to see the clearance or channel markers underneath. Items that
name a part/pad are anchored to that pad, so they move with the placement; track
items keep their absolute coordinate. A moved placement needs a fresh
`make route` — the panel says so instead of pretending the old route is live.

The channel number is measured, not simulated: the UI does not rasterise the
board every tick. The live clearance row is the cheap proxy for the same
question, and the Python measurement remains the authority.

## Where the tuning and the placements live

| State | Lives in |
| --- | --- |
| Parameter **values** and the parameter **row order** | **`ui/placement/params.json`** — tracked in git, written by this UI on every change ([history 0016](../../docs/history/0016-placement-ui-decisions.md)) |
| A **placement you save** (positions, pins, the seed and the params it ran with) | **`ui/placement/placements/<name>.json`** — tracked in git ([history 0016](../../docs/history/0016-placement-ui-decisions.md), [`placements/README.md`](placements/README.md)) |
| View toggles, the seed you were last on, the save name | your browser (`localStorage`, key `tinyups.place.ui.v1`) |
| Graph, boards, DRC reports | `build/layout/` — **untracked** (generated) |

Parameter values are resolved as **built-in defaults < `params.json` < the
`params` of a seed you pick deliberately** (drop-down, **Load**, `?seed=`).
A seed's params are a session override — they reach the file only once you change
a parameter. `↺ Default values` resets the values and writes that; `↕ Default
order` drops the `order` override.

Writes are debounced (700 ms) and flushed when the tab closes. Because the file
is tracked, an experiment is undone with `git checkout
ui/placement/params.json`, and `git log -p` on it is the record of which knobs
turned out to matter. A key may be deleted from the file to fall back to its
built-in default; `_comment` is preserved.

Saved sessions appear in the seed drop-down (marked `saved`, they win over a
same-named engine output) and can be loaded again — that is the way to resume a
placement, pins included.

## The model

The force model, the parameter defaults, the host assignment, the scatter
generator and the metric set live in **one module**,
[`public/model.js`](public/model.js) — imported by the UI and by `render.py`'s
metric expectations. `app.js` is the view: scene, interaction, persistence.

## Which placement engine, and why d3-force
`d3-force 3.0.0` is vendored (`node_modules/`, served to the browser through an
import map) and it is **the** interactive choice: it is a tick-by-tick
simulation, so it can run while you drag, and its parameters are exactly the
physical knobs a layout needs (link force, link distance, repulsion, collision,
centring). Batch solvers (dagre, ELK, graphviz) cannot run live; they are
archived with the rest of the old PoC in
[`docs/history/layout_poc/`](../../docs/history/layout_poc/).

The server only hosts files + a save/apply API; the solver runs in the tab, so
the same `node ui/placement/server.mjs` also works headless server-side if you
ever want batch runs.

## Parameters

Every slider maps to a force in `public/model.js`.

**Links** — `forceLink`
- `SIG_STR` signal trace link force — strength for a zero-width net
- `POW_STR` power trace link force — strength reached at a full `WREF`-wide trace
- `WREF` reference width (mm) — the force model's "full power" width, the 1 oz
  IPC-2221 width of a 20 A net (18.71 mm). The board is 2 oz, so its real
  requirement is 9.4 mm; the graph carries that separately as `required` and the
  inspector shows it
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
  [`docs/history/0006`](../../docs/history/0006-host-force-on-neutral-starts.md).

  This is the answer to "why do a controller's caps drift to the middle": the net
  links pull a part toward its *net's centroid* (a wide rail's centroid is where
  the power parts are), and `GND` — the one net that would tie every decoupling
  cap to its IC — is dropped, being a plane. Measurements, the rejected
  alternatives (centre pull, range-limited cliques) and the numbers:
  [`docs/history/0005`](../../docs/history/0005-the-netlist-cannot-hold-satellites.md),
  [history 0016](../../docs/history/0016-placement-ui-decisions.md).

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
start.

## Source of truth, and where edits go

- **Read:** `build/layout/graph.json` (built from **the board's footprints** by
  `extract.py` — the board, not the netlist, is the component source of truth)
  plus a seed position file in `build/layout/` or `placements/`.
- **Write (generated, untracked):** `build/layout/board.kicad_pcb` + DRC on
  demand. Nothing else in `build/` is read back by the UI.
- **Write (tracked, on purpose):**
  - `ui/placement/params.json` — the engine tuning
    ([history 0016](../../docs/history/0016-placement-ui-decisions.md));
  - `ui/placement/placements/<name>.json` — one file per **Save**
    ([history 0016](../../docs/history/0016-placement-ui-decisions.md)).
- **Applying a placement** writes a copy under `build/layout/`; promoting it to
  `hardware/tinyups.kicad_pcb` is a deliberate `cp` after reviewing the DRC.

## Files

| File | Role |
| --- | --- |
| `public/model.js` | **the model**: defaults, geometry, every force, host assignment, scatter, metrics |
| `server.mjs` | dependency-free Node HTTP server: UI, graph, seeds, params, placements, vendor, save/apply |
| `public/index.html` | page + import map |
| `public/app.js` | the view: scene, drag/pin, params panel, metrics table, persistence |
| `public/style.css` | panel + board styling |
| `extract.py` | board footprints + nets → placement graph (`build/layout/graph.json`) |
| `from_board.py` | snapshot the main board as `placements/main.json` (`make place-seed`) |
| `legalize.py` | rotation, de-overlap, hard pass, grid snap (optional, CLI) |
| `apply.py` | write a saved placement onto the main board + DRC |
| `render.py` | SVG + PNG render of a saved placement |
| `params.json` | the tracked engine tuning, edited from the Engine panel |
| `placements/` | the tracked placements you save (one `<name>.json` each) |
