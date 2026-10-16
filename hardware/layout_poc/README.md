# Auto-placement PoC — deriving placement from a layout engine

**Question:** instead of hand-tuning the power-first placement algorithm in
`gen_pcb.py`, can we build a *graph* (components → nodes, nets → edges) and let
an existing, battle-tested layout engine place the parts?

**Answer: yes for the global structure, no as a drop-in.** Force-directed
engines produce usable coordinates directly; layered engines (dagre, ELK, dot)
produce excellent *ordering* but degenerate coordinates. Either way the result
is not a legal PCB placement until a legalisation pass runs. That pass is the
real work, and it is engine-independent — it is the piece worth keeping.

## Ground rules (v2)

Decided with the maintainer after the first round:

| Rule | Why |
| --- | --- |
| **GND is dropped from the graph entirely** | it is a plane; its "traces" carry no placement signal, and as a 71-part net it glues everything into a hairball |
| **No power-corridor keep-out** | the corridor is part of the hand floorplan, not of a graph-derived placement |
| **Only `1J1` (XT60 in) and `5J2` (XT30 out) are pinned** | they are the two terminals of the power path; USB/SWD/PACK/CELLS/fan headers are free to move |
| **The power path must run input → output** | see `d3-force-incremental` and the `axisR` metric |

## Pipeline

```
build/tinyups.net
   │  extract.py          nodes = components (courtyard size, pads, block),
   ▼                      edges = MST per net, weight = IPC-2221 width,
                          + flow position (input->output) per part
build/layout/graph.json
   │  engines/*.mjs|py    d3-force · d3-force-incr · dagre (mermaid) · ELK · graphviz
   ▼
build/layout/raw-*.json
   │  fitpos.py           uniform fit to 150x140 (layered engines only — the
   ▼                      force engines already work in board mm)
build/layout/pos-*.json
   │  legalize.py         rotate + de-overlap + worst-first hard pass
   ▼
build/layout/*.json  ──►  render.py  ──►  *.png / *.svg
                     └──►  apply.py   ──►  build/layout/board.kicad_pcb (+DRC)
```

```sh
make layout        # extract, run all engines, legalise, render, score
make mermaid       # the flowchart render
```

## The graph model (the part that matters)

| Decision | Choice | Why |
| --- | --- | --- |
| edge per net | **MST** (k−1 edges) | a clique on a big net is quadratic and collapses the graph |
| per-net weight | `f(width) / (k−1)` | a many-pin net must not outvote a 2-pin net (standard HPWL clique normalisation) |
| edge width | **IPC-2221**, 20 A → **18.7 mm** | the only physically meaningful "springiness" |
| **GND** | **dropped** | a plane, not something placement should chase |
| pins | **only `1J1` + `5J2`** | the two power terminals |
| flow position | BFS hops from input / (hops from input + hops from output) | 0 at the input, 1 at the output — used to order *and* to seed the chain |

`extract.py` is deliberately the single source of the graph so every engine is
compared on identical input.

## Results (124 parts, board 150×140 mm)

```
stage  engine                    HPWL    wHPWL    wire  ovl  out   path  axisR    in   out
--------------------------------------------------------------------------------------------
legal  graphviz:sfdp+legal       3259    12653    3053    0    0    699  -0.71    97   104
legal  graphviz:neato+legal      3536    16968    3511    0    0    920   0.16   114    55
legal  d3-force+legal            6702    23743    6983    0    0   1281   0.49    69    16
legal  d3-force-incr+legal       6515    24945    6733    0    0   1697   0.61    16    16   <<
legal  elk+legal                 4887    16300    5513    3    0    592   0.31    68    40
legal  dagre+legal               5234    14207    5672   13    0    785  -0.37    51    88
legal  graphviz:dot+legal        4670    15080    4581    3    0    596  -0.70   128    81
--------------------------------------------------------------------------------------------
hand floorplan (RESUME.md): HPWL 8304 · weighted 15476
```

* **`sfdp` wins on wirelength** (HPWL 3259, −61 % vs the hand floorplan) and
  legalises perfectly — but it has the *worst* flow order (`axisR −0.71`).
* **`d3-force-incr` wins on the power path**: `axisR 0.61` and the chain's two
  ends sit **16 mm from the input and 16 mm from the output**. Every other
  engine leaves the first power part 51–128 mm from the input — that is exactly
  the "1R7, wired straight to the input, ends up at the bottom" problem.
* So it is a genuine trade-off: wirelength vs. a readable power flow.

### The flow metric

`axisR` = correlation between a part's **flow position** (0 at the input, 1 at
the output; from the rail graph) and where it sits **along the input→output
axis**. `1.0` means the power parts walk input→output in electrical order;
`~0` means flow and geometry are unrelated; **negative** means the path is
roughly *reversed* — which is what `dot`/`sfdp` produce and what the maintainer
spotted by eye.

## The new engine: `d3-force-incremental`

Instead of relaxing the whole graph at once — which lets the power path wander —
grow the placement along the flow:

1. **Both terminals are pinned** (input top, output bottom): they are the poles
   the chain spans between.
2. **The ends of the chain are pinned too**: the power part electrically closest
   to the input, and the one closest to the output.
3. **Power components are added one at a time** in flow order, each seeded at its
   flow position along the axis and beside its already-placed neighbours, with a
   short relax after every addition — so a part only meets the graph once its
   upstream neighbour is on the board.
4. Everything else joins afterwards, then the whole design relaxes freely.

Two bugs worth recording, because both silently produced a "worst of both"
layout:

* **d3 caches force strengths at `initialize()`.** Gating charge/collision on a
  per-node `active` flag froze *every* strength at its all-inactive value (0), so
  the chain collapsed into a 9 mm-wide column and the `CHARGE` knob did nothing.
  Re-assigning the forces after each activation fixes it.
* **A spring tree folds, it does not stretch.** Pinning only the two ends left
  everything piled near the input with a gap in the middle. Seeding each part at
  its *flow position* on the axis is what makes the chain span the board.

### Renderings

* `build/layout/contact-sheet.png` — all seven legalised placements side by side
* `build/layout/<engine>.png|.svg` — per engine
* `build/layout/graph.mmd`, `mermaid.svg|png` — the flowchart

## The legaliser is the reusable part

`legalize.py` turns any coords into a legal placement:

1. **Rotation** — for each part pick the 0/90/180/270 whose pads point at the
   weighted centroid of the net's other pads (wide nets dominate). This replaces
   the hand-written rail-vs-local-node rotation rule in `gen_pcb.py`.
2. **De-overlap** — vectorised relaxation (soft spring to the engine position +
   courtyard push), then a **worst-first Gauss-Seidel hard pass**.
3. **Grid snap** (0.5 mm) — the hard pass clearance is deliberately kept above
   the grid step, otherwise the snap re-creates overlaps.

Terminals and engine-pinned parts never move (`pin: true` in a positions file).

**Known limitation:** when an engine hands over a *tight* layout (dagre's chain,
the incremental band before tuning), local pushes have no free space to push
into, and the hard pass leaves a handful of residual overlaps
(dagre 13, elk 3, dot 3; the force engines reach 0). Fixing it needs a global
spreading term, not more local iterations.

### Verified against KiCad's own DRC

```sh
python hardware/layout_poc/apply.py build/layout/leg-gv-sfdp.json
```

builds the full board and runs `kicad-cli pcb drc` on it: **0 courtyard
overlaps, 0 board-edge issues.** The only remaining items are pre-existing and
unrelated to placement (289 unconnected — nothing is routed; `5U1`'s own pads at
0.15 mm; `1J1`'s pad vs the edge).

## Mermaid

`mermaid.py` emits the graph as a `flowchart LR` (one subgraph per power block,
edge labels = net + current) and `make mermaid` renders it for real
(`build/layout/mermaid.svg`) — Google's Chrome-for-Testing endpoint is
unreachable here and `chromium` is snap-only, so Chromium is pulled from the npm
registry via `@sparticuz/chromium` (`engines/mmconf.mjs`).

**Verdict:** mermaid gives a topology view, not a placement — uniform shapes, no
physical size, no board geometry. And it costs nothing layout-wise to skip:
**mermaid's flowchart renderer is dagre**, which `engines/dagre.mjs` already
drives head-to-head with the others.

## Open questions / blockers

1. **Anchoring.** Force engines honour pins natively; layered engines ignore
   them, so `fitpos.py` snaps the connectors afterwards. A real integration
   should model anchors as constrained nodes.
2. **`axisR` is a proxy, not the goal.** It measures flow *readability*; the
   thing that actually matters is that the board routes. `sfdp`'s −61 % HPWL may
   or may not survive routing.
3. **Residual overlaps** for tight engine layouts (see above).
4. **Nets are still MST-approximated.** A star/clique-with-weight model (or a
   real quadratic placer) would model HPWL exactly.
5. **Signal parts are unconstrained.** Decoupling-cap proximity to its IC is only
   implicitly encoded via the block structure.
6. **Not wired into `gen_pcb.py`.** The PoC writes only into `build/layout/`;
   replacing the BFS/`col_y`/A\* code needs an ADR.

## Files

| File | Role |
| --- | --- |
| `extract.py` | netlist → `graph.json` (MST edges, IPC-2221 widths, flow positions) |
| `engines/d3force.mjs` | d3-force, width-weighted links |
| `engines/d3force_incremental.mjs` | **the power-order growth described above** |
| `engines/dagre.mjs` | dagre = the mermaid flowchart engine |
| `engines/elk.mjs` | elkjs layered + **orthogonal edge routing** (bend points) |
| `engines/graphviz.py` | dot / neato / fdp / sfdp / osage via `-Tjson` |
| `engines/mmconf.mjs` | puppeteer launch config from `@sparticuz/chromium` |
| `fitpos.py` | uniform fit to the board (layered engines only) |
| `legalize.py` | rotation, de-overlap, hard pass, grid snap |
| `render.py` | SVG + PNG renders and the metrics (incl. `axisR`) |
| `compare.py` | the score table above |
| `apply.py` | write a legal placement into a real board and DRC it |
| `mermaid.py`, `render_mermaid.sh` | flowchart source + render |
| `contact_sheet.py` | one PNG with every legalised placement |
