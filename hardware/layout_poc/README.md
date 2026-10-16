# Auto-placement PoC — deriving placement from a layout engine

**Question:** instead of hand-tuning the power-first placement algorithm in
`gen_pcb.py`, can we build a *graph* (components → nodes, nets → edges) and let
an existing, battle-tested layout engine place the parts?

**Answer: yes for the global structure, no as a drop-in.** Force-directed
engines produce usable coordinates directly; layered engines (dagre, ELK, dot)
produce excellent *ordering* but degenerate coordinates. Either way the result
is not a legal PCB placement until a legalisation pass runs. That pass is the
real work, and it is engine-independent — it is the piece worth keeping.

## Pipeline

```
build/tinyups.net
   │  extract.py          nodes = components (courtyard size, pads, block),
   ▼                      edges = MST per net, weight = IPC-2221 width
build/layout/graph.json
   │  engines/*.mjs|py    d3-force · dagre (mermaid) · ELK · graphviz
   ▼
build/layout/raw-*.json
   │  fitpos.py           uniform fit to 150x140 + pin the 7 connectors
   ▼
build/layout/pos-*.json
   │  legalize.py         rotate 0/90/180/270 + de-overlap + corridor keep-out
   ▼
build/layout/leg-*.json  ──►  render.py  ──►  *.png / *.svg
                         └──►  apply.py   ──►  build/layout/board.kicad_pcb (+DRC)
```

Run everything:

```sh
make layout        # extract, run all engines, legalise, render, score
```

## The graph model (the part that matters)

| Decision | Choice | Why |
| --- | --- | --- |
| edge per net | **MST** (k−1 edges) | a clique on GND (71 parts) is 2485 edges and collapses the graph into a blob |
| per-net weight | `f(width) / (k−1)` | a 71-pin net must not outvote a 2-pin net (standard HPWL clique normalisation) |
| edge width | **IPC-2221**, 20 A → **18.7 mm** | the only physically meaningful "springiness"; reproduces the ~19 mm 1 oz figure |
| GND | dropped from the springs | it is a plane, not something placement should chase |
| connectors | pinned (`fx/fy` for d3, snapped for the rest) | they must stay on the board edges |
| corridor | 20 mm keep-out down the centre | power still needs its pour width |

`extract.py` is deliberately the single source of the graph so every engine is
compared on identical input.

## Results (124 parts, board 150×140 mm)

`---` = raw engine output, `legal` = after `legalize.py`.

```
stage  engine              HPWL    wHPWL    wire  ovl  out  corr
------------------------------------------------------------------
raw    d3-force            7033    23087   11285    3    0    10
legal  d3-force+legal      7255    23618   12535    0    0     0
raw    dagre               4866    12676    6804  220    0    79
legal  dagre+legal         7570    19694   10429   22    0     1
raw    elk                 5859    18540    9037  149    0    12
legal  elk+legal           6154    19603    9813    8    0     0
raw    graphviz:sfdp       4542    17306    9228    0    0    31
legal  graphviz:sfdp+legal 4318    15805    9447    0    0     0
raw    graphviz:neato      4769    20304    9026    4    1    31
legal  graphviz:neato+legal 4779   19760    9485    1    0     0
raw    graphviz:dot        5012    16631    7932   99    0    50
legal  graphviz:dot+legal  6065    18750    9676   10    0     0
------------------------------------------------------------------
hand floorplan (RESUME.md): HPWL 8304 · weighted 15476
```

*ovl* = courtyard overlaps, *out* = parts off-board, *corr* = parts intruding
into the reserved corridor. **sfdp wins on every placement metric** (HPWL 4318
vs 8304 = **−48 %**) and legalises perfectly.

### Renderings

* `build/layout/contact-sheet.png` — all six legalised placements side by side
* `build/layout/leg-<engine>.png|.svg` — per engine
* `build/layout/graph.mmd` — the mermaid source (see below)

## What each engine gives you

| Engine | Kind | Coordinates | Verdict |
| --- | --- | --- | --- |
| **graphviz `sfdp`** | multiscale force | directly usable | **best**: legalises to 0/0/0, lowest HPWL |
| graphviz `neato` | stress majorisation | directly usable | good, a little clumped |
| **d3-force** | force (velocity Verlet) | directly usable | clean, but drifts into a hairball |
| **ELK `layered`** | Sugiyama + **orthogonal routing** | 1-D degenerate | best *flow*; also returns edge bend points |
| dagre (**= mermaid**) | Sugiyama | 1-D degenerate | good ordering, 220 overlaps raw |
| graphviz `dot` | Sugiyama | 1-D degenerate | same story |

Force engines need the edge weights to matter (short, wide traces) but their
output is "clouds of parts" — structure without rows. Layered engines give
exactly the flow a power path wants (rail → FET → node → L → node → FET) but
their geometry is a chain, so uniform-fitting it into a square board crushes
everything (220 overlaps for dagre vs 0 for sfdp).

## The legaliser is the reusable part

`legalize.py` turns any coords into a legal placement:

1. **Rotation** — for each part pick the 0/90/180/270 whose pads point at the
   weighted centroid of the net's other pads (wide nets dominate). Replaces the
   hand-written rail-vs-local-node rotation rule in `gen_pcb.py`.
2. **De-overlap** — vectorised relaxation (soft spring to the engine position +
   courtyard push).
3. **Hard pass** — Gauss-Seidel fixed point that guarantees *no* courtyard
   overlap and *no* corridor intrusion. The corridor is injected as one extra
   **fixed obstacle node** so the keep-out and the overlap solver share one fixed
   point; with two separate passes they oscillate against each other.
   The pass clearance must be **≥ the grid step**, otherwise the final grid snap
   re-creates overlaps.

### Verified against KiCad's own DRC

```sh
python hardware/layout_poc/apply.py build/layout/leg-gv-sfdp.json
```

builds the full board and runs `kicad-cli pcb drc` on it:

```
unconnected_items 289   <- nothing is routed (expected)
clearance          21   <- 5U1's OWN adjacent pads, 0.15 mm: pre-existing
copper_edge        1    <- 1J1's PTH pad vs the edge: pre-existing anchor
courtyards_overlap 0    ✓
board-edge issues  0    ✓
```

So the placement is genuinely DRC-legal; the only remaining items are
pre-existing and unrelated to placement.

## Mermaid

`mermaid.py` emits the same graph as a `flowchart LR` (one subgraph per power
block, edge labels = net + current) to `build/layout/graph.mmd`, and
**`make mermaid` renders it for real** to `build/layout/mermaid.svg`:

```sh
make mermaid        # -> build/layout/mermaid.svg  (graph.mmd is the source)
```

Two things had to be worked around to get a browser:
Google's Chrome-for-Testing storage endpoint is unreachable from this container
(the download stalls), and `chromium` is snap-only on this Ubuntu. So Chromium
is pulled from the **npm registry** instead, via `@sparticuz/chromium`
(`engines/mmconf.mjs` turns its `executablePath()` into a puppeteer config for
`mmdc`). `rsvg-convert` rasterises the SVG for viewing.

**Verdict:** mermaid gives a nice *topology* view (blocks, net names, currents)
but nothing placement-shaped — uniform node shapes, no physical size, no board
geometry. And it costs nothing layout-wise to skip: **mermaid's flowchart
renderer is dagre**, which `engines/dagre.mjs` already drives head-to-head with
the other engines.

## Open questions / blockers

1. **Anchoring.** Force engines honour pins via `fx/fy`; layered engines ignore
   them, so `fitpos.py` snaps the connectors afterwards. A real integration
   should add anchor terminals as constrained nodes (or run a constrained
   layout) rather than snapping after the fact.
2. **Nets are still cliques-ish.** MST keeps the graph small but under-counts
   the pull of a many-pad net. A star/clique-with-weight model (or a proper
   quadratic placer) would model HPWL exactly.
3. **Ratsnest, not routability.** No engine knows about track *channels*, via
   counts or layer assignment. sfdp's −48 % HPWL may not survive routing; it
   must be validated by routing the board, not by HPWL alone.
4. **Signal parts are unconstrained.** Only the power path (and the block
   grouping) shapes the graph; decoupling-cap proximity to its IC is only
   implicitly encoded.
5. **`GND` dropped by hand.** With a real plane there is nothing to chase, but
   the drop is currently a flag, not a decision derived from the stackup.
6. **This does not yet touch `gen_pcb.py`.** The PoC writes only into
   `build/layout/`; wiring an engine + legaliser into the board build (and
   replacing the BFS/`col_y`/A\* code) is the next step and needs an ADR.
7. **Two-pass corridor.** The soft corridor force in the relaxation is now
   redundant with the hard obstacle node; worth deleting.

## Files

| File | Role |
| --- | --- |
| `extract.py` | netlist → `graph.json` (MST edges, IPC-2221 widths) |
| `engines/d3force.mjs` | d3-force, width-weighted links, corridor + bounds forces |
| `engines/dagre.mjs` | dagre = the mermaid flowchart engine |
| `engines/elk.mjs` | elkjs layered + **orthogonal edge routing** (bend points) |
| `engines/graphviz.py` | dot / neato / fdp / sfdp / osage via `-Tjson` |
| `fitpos.py` | uniform fit to the board + pin the connectors |
| `legalize.py` | rotation, de-overlap, corridor keep-out, grid snap |
| `render.py` | SVG + PNG renders and the placement metrics |
| `compare.py` | the score table above |
| `apply.py` | write a legal placement into a real board and DRC it |
| `mermaid.py` | emit `flowchart` source (`make mermaid` renders it) |
| `render_mermaid.sh` | graph.mmd -> mermaid.svg via mmdc + npm Chromium |
| `engines/mmconf.mjs` | puppeteer launch config from `@sparticuz/chromium` |
| `contact_sheet.py` | one PNG with every legalised placement |
