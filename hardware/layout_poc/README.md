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
legal  graphviz:sfdp+legal       3018    13050    2866    0    0    659  -0.76   104   116
legal  graphviz:neato+legal      3490    14903    3451    0    0    852  -0.06    99    73
legal  d3-force+legal            6079    19632    6212    0    0    836   0.70    28    34
legal  d3-force-incr+legal       5745    18432    6214    1    0    955   0.48    16    16   <<
legal  elk+legal                 6721    24854    7567    6    0    894   0.44    68    70
legal  dagre+legal               5279    18718    5527   13    0   1001  -0.24     9   123
legal  graphviz:dot+legal        3911    16109    4014    9    0    696  -0.47   127    53
--------------------------------------------------------------------------------------------
hand floorplan (RESUME.md): HPWL 8304 · weighted 15476
```

* **`d3-force` / `d3-force-incr` are the only engines that get the power flow
  ordered** (`axisR +0.70` / `+0.48`) and the only ones whose chain ends sit at
  the two terminals (16-28 mm vs 99-127 mm).
* **`sfdp` still wins wirelength** (HPWL 3018, -64 % vs the hand floorplan) and
  legalises perfectly - but it has the *worst* flow order (`axisR -0.76`).

### What a link *means* (why 5Q2 -> 5U1 is thin, not red)

An edge's weight is the current that flows **through that connection**, not the
whole rail's design current:

```
connection_current(a, b) = min(conducted(a, net), conducted(b, net))
```

`conducted()` says what a part actually carries on that net:

| part | conducted current on the net |
| --- | --- |
| FET, inductor, fuse, connector | the net's design current (series element) |
| resistor < 1 ohm | the net's design current (shunt) |
| capacitor | its ripple RMS, from `power_map`'s impedance model |
| IC, diode, bias resistor | `0.1 A` — a sense/supply pin carries milliamps |
| `power_map.OVERRIDES` | fan header 0.2 A, cell-sense header 0.01 A |

This fixed two bugs the renders exposed:

1. **The whole net's current was applied to every part on it.** `5U1` (LM5176)
   has pins on `N_CS` and `SW1_OUT` (17 A each), but they are the current-sense
   and switch-node *sense* pins. The chip got a fat 17 A link **and** a
   100:1-strength spring dragging it into the power cluster.
2. **The MST linked a FET to the chip rather than to the neighbouring FET.** The
   tree was built on a size-based pseudo-distance, so only **2 of 197** edges
   came out >= 15 A. Ordering candidates by connection current first makes the
   tree link the current carriers — now **16** thick edges forming a proper
   input -> fuse -> shunt -> FETs -> inductor -> FETs -> output spine.

### The force model (why the first version scattered the power parts)

Three bugs made the first round wrong; all are now fixed in the d3 engines:

| Symptom | Cause | Fix |
| --- | --- | --- |
| power parts formed a **ring** around the outside | `distance = D0 + DK*sqrt(width)` gave a 20 A net a **17 mm** rest length vs 7 mm for a signal — the wide nets literally asked to be *spread apart* | `D0 + DK*(width/WREF)` → signal 2 mm, power 4 mm. Wide traces need *width*, not *length* |
| power traces refused to get shorter | strength was only ~**5:1**. There are far fewer power edges than signal edges, so the aggregate signal pull won | signal `0.1` vs power `10` → **100:1 per edge** |
| big power parts pushed each other away | repulsion scaled with part size, so a 15 mm FET repelled ~10× a 1 mm cap | constant repulsion (`CHARGE 4`); **collision** does the spacing |
| knobs had no effect / forces went inert | d3 decays `alpha` to ~0 after ~300 ticks, so most iterations did nothing | `alphaDecay` tied to the iteration count; the incremental engine re-heats per phase |

Plus a stronger pull to the centreline (`CENTER_X 0.15`) — both terminals are on
the centreline, so the design should compact around it.

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
* **d3 decays `alpha` to ~0 after ~300 ticks**, so every later addition was
  inert. The engine re-heats `alpha` per phase now.

### Renderings

* `build/layout/contact-sheet.png` — all seven legalised placements side by side
* `build/layout/<engine>.png|.svg` — per engine, 2× (≈3500 px) so the reference
  designators are readable
* `build/layout/graph.mmd`, `mermaid.svg|png` — the flowchart

### Reading a render

Two **different** scales are in play, which is worth knowing before the colours
look inconsistent:

* a part's **fill** says what the part *is* — red = power-handling, blue =
  signal, purple = connector, yellow = pinned terminal;
* a **trace's** colour and width say what its *net* carries — grey → yellow →
  orange → red for 0 → 1 → 5 → 17 A, i.e. by IPC-2221 width.

So a *red trace between two parts* does not mean they are power parts: it means
that connection carries ≥ 15 A, i.e. **both** parts conduct that current on the
shared net. `5Q1`↔`5Q2` share `SW1_OUT` (17 A) and both are FETs, so their link
is red. `5Q2`↔`5U1` share `N_CS` too, but `5U1`'s pin is a *sense* input, so
`min(17 A, 0.1 A)` = 0.1 A and the link is thin — see "What a link means".

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
