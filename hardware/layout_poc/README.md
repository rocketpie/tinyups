# Auto-placement PoC — deriving placement from a layout engine

> **Status: concluded.** The graph-derived placer beats the hand floorplan and
> is adopted as the **baseline layout** for the next phase.

## Result

**Adopted: graphviz `sfdp`** → `fitpos.py` (free-orientation search) →
`legalize.py` (rotation, de-overlap, grid snap).

| | hand floorplan | **sfdp (adopted)** |
| --- | --- | --- |
| HPWL (pre-route) | 8304 mm | **3295 mm (−60 %)** |
| courtyard overlaps (KiCad DRC) | — | **0** |
| board-edge violations (KiCad DRC) | — | **0** |
| parts off-board | — | **0** |
| power-path ordering (`axisR`) | n/a | +0.59 |

```sh
make layout            # 7 engines -> fit -> legalise -> renders + score table
make baseline          # materialise the adopted placement
                       #   -> build/layout/baseline.kicad_pcb   (124 parts)
```

* The baseline board is DRC-checked by KiCad itself: **0 courtyard overlaps,
  0 board-edge issues.** The remaining DRC items are pre-existing and unrelated
  to placement (289 unconnected — nothing is routed; `5U1`'s own pads at
  0.15 mm; silkscreen cosmetics).
* **Visual verdict** (maintainer, own eyes): sfdp has the cleanest main path —
  no crossings, no zig-zag, visible branching. neato is second; the layered
  engines (dagre/dot/ELK) and the d3-force variants are behind.
* The reusable half is **`legalize.py`**, not the engine: engines give
  *structure*, and a placement only becomes legal after rotation + de-overlap +
  grid snap. That applies to any engine, including whatever comes next.
* `make layout` still runs all 7 engines so the comparison stays honest; sfdp
  merely wins it.

### What we did *not* solve

1. **Every number here is a pre-route proxy.** HPWL and `axisR` say nothing
   about routability. The field's standard is routed wirelength, via count and
   DRV count (FreeRouting + KiCad DRC) — we own both tools (`route.py`,
   `routing_report.py`) and have not run them on the baseline. **This is the
   main open question**, and NS-Place's published −10 % routed wirelength /
   −18 % vias vs manual is the number to beat.
2. **Rotation is decided after placement**, in the legaliser. The state of the
   art (Cypress) optimises position and orientation jointly; NS-Place lists
   orientation optimisation as future work. This is a known gap, not a solved
   problem.
3. **Signal parts are only loosely constrained** — a decoupling cap is pulled
   toward its net's centre, not toward its IC.
4. **Residual overlaps on tight engine layouts** (dagre 20, dot 16, elk 11):
   local de-overlap has nowhere to push in a compressed layout.
5. **Touching `gen_pcb.py`**: the PoC writes only into `build/layout/`. Wiring
   the pipeline in needs an ADR.

### A bug worth recording

Validating the baseline against KiCad's DRC caught a genuine bug: the
legaliser and renderer rotated parts in the **math (Y-up) convention**, while a
KiCad board is **Y-down**. Identical for a symmetric courtyard, *mirrored* for
an asymmetric one — `TO-252-2`'s courtyard sits 0.84 mm off-centre, which is why
two courtyard overlaps (`4Q1↔4Q2`, `2Q3↔2Q4`) slipped past our own metric while
KiCad found them. Fixed in `legalize.py` + `render.py`; the baseline went from 2
overlaps + 1 edge violation to **0 + 0**. Lesson: our internal metrics are not a
substitute for running the real DRC.

---

**Question:** instead of hand-tuning the power-first placement algorithm in
`gen_pcb.py`, can we build a *graph* (components → nodes, nets → edges) and let
an existing, battle-tested layout engine place the parts?

**Answer: yes for the global structure, no as a drop-in.** Force-directed
engines produce usable coordinates directly; layered engines (dagre, ELK, dot)
produce excellent *ordering* but degenerate coordinates. Either way the result
is not a legal PCB placement until a legalisation pass runs. That pass is the
real work, and it is engine-independent — it is the piece worth keeping.

---

## Field overview — prior art

This is a **known, active problem, and nobody has closed it.** The best paper at
ISPD 2025 spends a slide on what the state of the art *cannot* do; NS-Place's own
conclusion lists two unsolved items; realistic open benchmarks only appeared
recently. The field's one settled convention is the **yardstick**: route the
board (FreeRouting) and report **routed wirelength, via count and DRV count** in
KiCad — which is exactly the validation we still owe ourselves.

#### NS-Place (UC San Diego, arXiv 2210.14259) — the closest work to ours

Read in full. Its flow is strikingly similar to this PoC:

* collapse the netlist hypergraph with the **clique model** (what we do);
* initialise with **Laplacian eigenvectors** — their answer to the
  initialisation instability measured in `experiments/sfdp_seeds.py`;
* gradient descent on weighted-average wirelength + density + a **net-separation
  (max-margin / SVM) term**;
* **MILP legalisation** with relative-position constraints;
* validate with **FreeRouting + KiCad DRC** — the same two tools we have.

14 real PCBs, 8-1570 components, 1-4 layers. Results vs manual placement:
~80 % fewer DRVs/unrouted nets, **-10 % routed wirelength**, **-18 % vias**.

What it does *not* achieve, in its authors' own words and tables:

* the **MILP legaliser fails outright** - "-", no feasible solution in 4 h - on
  **7 of 14 designs**;
* it **loses to manual on high-utilisation boards** (PCB2, only ~20 % whitespace);
* **rotation is future work**: "we plan to investigate methods to optimize
  component orientation during the net separation minimization" - orientation is
  only *enumerated* at initialisation;
* *"optimal solutions are not guaranteed and initialization remains an open
  problem"*;
* 3-6 k s runtime on a 3.4 GHz i7; and it notes that vanilla **RePlAce "fails to
  find good solutions for multi-layer designs with diversely sized components"**.

#### Cypress (Cornell + NVIDIA, ISPD 2025 **Best Paper**)

`csl.cornell.edu/~zhiruz/pdfs/cypress-ispd2025.pdf` — VLSI-style and
GPU-accelerated. Bi-level optimisation of **position and orientation** plus
legalisation, with PCB-specific cost functions. Target scale is **>10 000
components** (modern HPC/AI boards). Reported: 1-5.9x routability, up to
**1-19.7x shorter routed track lengths**, up to 492x faster than SA-PCB and 4.3x
faster than NS-Place; minutes rather than hours. They also had to **publish an
open-source benchmark suite** because none existed.

Their state-of-the-art comparison slide is the clearest statement of what is
still unsolved: existing tools "do not model routing conflicts", "lack support
for orientation/rotation", are "slow (1-2 hours)" and "small (<500 components)"
- and, tellingly, *"even with stronger legalization, NS-Place+ still fails in
most cases"*.

*Source note: the PDF is not fetchable from here (content type), so the above
comes from the ISPD 2025 slides and the ISPD programme abstract. Worth a proper
read of the paper before leaning on the specifics.*

#### SA-PCB (OpenROAD, BSD-3)

`github.com/The-OpenROAD-Project/SA-PCB` — C++ simulated annealer for polygonal
components; 90/45 rotation supported (free rotation "in progress"), HPWL cost,
R-tree overlap queries, multi-start. Its own README is candid: *"Algorithm very
sensitive to parameters"* and *"Broken support for weighted modules/nets"*. The
obvious strength for PCB work is that annealing handles **rotation and irregular
shapes natively** - i.e. the very thing we currently do as a separate
legalisation step.

#### Two papers that do what we do

* **Modern Automatic PCB Placement With Complex Constraints** (IEEE 2025) - an
  SA-based pad-alignment step, then **"a force-directed global placement guided
  by anchor points extracted from power circuit flows"**, then window-based
  legalisation. That is our approach *and* the "stronger pull on the power
  terminals" idea, published.
* **CadMust-Neo** - a **KiCad Action Plugin** doing simulated-annealing placement
  that respects board boundaries, courtyard overlaps and keep-out zones, with a
  wirelength cost. Worth reading (and possibly borrowing from) before writing
  more of our own.

#### The recipe the field converges on

1. **Analytical global placement** - quadratic / weighted-average wirelength plus
   a density or repulsion term (mPL, ePlace, RePlAce, DREAMPlace).
2. **A routability term** - NS-Place separates nets by maximising the margin
   between net convex hulls (an SVM-like regulariser). Cheap to borrow.
3. **Legalisation is a distinct, hard step** - MILP (NS-Place) *fails on half the
   benchmarks*; they fell back to relative-position constraints; others use
   window-based legalisation or annealing.
4. **Rotation as a first-class variable** - Cypress does, NS-Place does not (its
   stated gap).
5. **Validation by routing**, never by HPWL alone.

#### Other leads

* **HiePlace** (CUHK, TCAD 2026) - hierarchical PCB placement: irregular
  components, alignment, component priority.
* *An analytical approach and fine-tuning strategy for PCB placement*
  (ScienceDirect 2025) - reports +20 % routing completion and -68 % placement
  runtime vs simulated annealing.
* **Stress majorization** - the principled form of what we do by hand
  (Wikipedia *Force-directed graph drawing*; Brown's *Force-Directed Drawing
  Algorithms* handbook chapter; Dwyer/Koren/Marriott, *Constrained graph layout
  by stress majorization and gradient projection*). Also **Davidson & Harel
  1996**, simulated annealing for graph drawing, and **Cheong et al.**,
  *Force-directed algorithms for schematic drawings and placement: A survey*
  (2020) - directly on point.
* **DREAMPlace / ePlace / RePlAce / mPL** - the analytical placement lineage.
* **Local win worth using:** `elkjs` ships **8 algorithms** (verified by probing
  the installed build): `layered` (the one we used) plus **`force`, `stress`,
  `mrtree`, `rectpacking`, `disco`, `box`** and `random` (`spore` throws). Each
  is a one-line `elk.algorithm` swap.
* Also: **OGDF** (SpringEmbedderKK, StressMinimization, orthogonal layouts),
  **Adaptagrams / libcola** (constraint-based layout with *separation
  constraints* - non-overlap by construction), **graph-tool** (SFDP/ARF/module
  layouts), **igraph** (FR, Kamada-Kawai, Davidson-Harel, DrL, GEM).

#### Where we sit

| | rotation | legalisation | validated on | scale |
| --- | --- | --- | --- | --- |
| **this PoC** | after placement | greedy de-overlap -> **0 overlaps** | KiCad DRC only | 124 parts |
| NS-Place | *future work* | MILP -> **fails 7/14** | FreeRouting + KiCad | 8-1570 |
| Cypress | joint | legalisation step | routed | >10 000 |
| SA-PCB | 90/45 | by construction | - | small |

We are **competitive on pre-route HPWL** (-60 % vs our hand floorplan, with a
genuinely legal placement) and **unproven on routed results**. The cheapest
credible step up is the one the whole field agrees on: route the baseline and
report routed wirelength, vias and DRVs.

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
| force model per net | **clique**, total weight bounded by the net's required width | the textbook HPWL model: no part is special, and a 21-pad supply rail cannot out-gun a 2-pad net. See "Clique, not drop" |
| drawing per net | current-ordered **path** if the net has current carriers, else a **star from the hub** | the solver's clique is too dense to look at, and an MST roots a supply rail at whichever part came first (`2R11`'s degree-12) |
| edge width | **IPC-2221**, 20 A → **18.7 mm** | the only physically meaningful "springiness" |
| **GND** | **dropped** | a plane, not something placement should chase |
| pins | **only `1J1` + `5J2`** | the two power terminals |
| flow position | BFS hops from input / (hops from input + hops from output) | 0 at the input, 1 at the output — used to order *and* to seed the chain |

`extract.py` is deliberately the single source of the graph so every engine is
compared on identical input.

## Results (124 parts, board 150×140 mm)

```
stage  engine                    HPWL    wHPWL    wire  ovl  out   path  axisR    in   out
legal  graphviz:sfdp+legal       3295    11715    3742    0    0    738   0.59    62    16   <<
legal  graphviz:neato+legal      3865    12856    4007    0    0    768   0.53    73    27
legal  d3-force+legal            5840    16839    6100    0    0    999   0.76    44    18
legal  d3-force-incr+legal       5672    17573    6162    1    0    885   0.66    17    16
legal  elk+legal                 4567    15366    5588   11    0    591   0.69    12    45
legal  dagre+legal               5131    15683    6076   20    0    766   0.36    71    78
legal  graphviz:dot+legal        5033    12471    5710   16    0    536   0.67    58     9
--------------------------------------------------------------------------------------------
hand floorplan (RESUME.md): HPWL 8304 · weighted 15476
```

* **`sfdp` still leads on wirelength** (HPWL 3295, -60 % vs the hand floorplan)
  and legalises to zero overlaps.
* **`d3-force` has the most coherent flow** (`axisR 0.76`), and
  **`d3-force-incr` wins the chain *endpoints*** (17/16 mm vs sfdp's 62/16).
* The clique model costs the layered engines some overlap (dagre 20, dot 16) —
  the extra edges pull them tighter before the legaliser runs.

### Orientation: why sfdp's correlation was negative

`axisR` was **negative for sfdp, neato and dot** in the first rounds. The
hypothesis was a seeding artefact, so `experiments/sfdp_seeds.py` re-runs sfdp
with a randomised seed *and* shuffled node/edge order:

```
pass    seed    HPWL   axisR  axisR(mirror)  |axisR|
    0 273470    3830   -0.38           0.38     0.38
    1 677277    3823   -0.71           0.71     0.71
    2 479288    3584   -0.69           0.69     0.69
```

* mirroring flips the sign **exactly** (`corr(f, u) -> corr(f, 1-u) = -corr`);
* the sign **never flips across seeds** — so it is *not* a seeding artefact;
* `|axisR|` *does* move with the seed (0.38-0.71): seeding affects magnitude only.

The real cause is that a layered / stress engine **has no idea which end is the
input** — its orientation is free. So `fitpos.py` now tries the **8 orientations**
(4 rotations x mirror) and keeps whichever maximises `axisR`. That is a generic
post-step, applied to *every* engine (the d3 engines pass `--keep-scale`, since
they already work in board millimetres). Effect: sfdp **-0.76 -> +0.75**, neato
-0.06 -> +0.60, dot -0.47 -> +0.45 — and HPWL improved too.

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

### Clique, not drop: +3V3 and high-fanout nets

`2R11` (= base `R43`, a 10k pull-up) showed nearest-neighbour degree 12, which
looks absurd. It is on `+3V3`, a net with **21 pads across 12 components**. A net
is electrically one node, so *any* spanning tree is valid — the MST just happened
to root `+3V3` at `2R11`. Degree here is **not** connectivity (same for `2U1` 27,
`6U1` 24).

Is `+3V3` "like GND", i.e. droppable? It is a distribution rail (1 A logic), not
a plane, so unlike GND it does need routing. Two things decided against dropping
it:

* **It buys almost nothing.** Net total weight is already proportional to required
  width, so `+3V3` carries `0.39` against the power rails' `10.8` — ~28x weaker.
* **It would strand `6C4`**, the only part connected *solely* to `+3V3`/GND (the
  eight pull-ups all have a signal net too).

So the model is the **clique**: every pair on a net gets an equal share, and the
net's total weight stays bounded by its width. No part is special, so there is no
fake hub, and no supply rail can bundle unrelated components.

Two graphs are emitted and used for different jobs:

| job | decomposition |
| --- | --- |
| solving (force, ranks, ELK priorities) | the **clique** (416 edges), total bounded per net |
| drawing | the current-ordered **path** where the net has current carriers, else a **star from the hub** (the largest part) |

That is why `+3V3` now reads as a fan of thin lines out of `6U1` (the RP2040)
rather than out of a 10k pull-up, and `2R11` has a single drawn edge.

### Deferred: best-of-N per engine

Reseeding sfdp moves `|axisR|` by 0.2-0.3 and HPWL by a few percent
(`experiments/sfdp_seeds.py`), so a best-of-5 run would make the numbers fairer
and less noisy. Deliberately deferred until the large-net decomposition above is
settled, since a graph change invalidates every pass.

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
   should model anchors as constrained nodes — see `RESUME.md` §9A for the
   decaying-tether idea.
2. **`axisR` is a proxy, not the goal.** It measures flow *readability*; the
   thing that actually matters is that the board routes. `sfdp`'s −60 % HPWL may
   or may not survive routing.
3. **Residual overlaps** for tight engine layouts (see above).
4. **The clique is an approximation.** Total per-net weight is bounded by the
   net's width, which is deliberate, but the textbook `1/(k−1)` weighting is
   unbeaten for exact HPWL. See `RESUME.md` §9B for the alternatives
   (stress majorization, quadratic placement).
5. **Signal parts are unconstrained.** Decoupling-cap proximity to its IC is only
   implicitly encoded — a cap is pulled toward its net's *centre*, not its IC.
6. **Staging (solve the power parts first, freeze, fit the rest) was tried and
   rejected.** It shortens the power chain but costs wirelength in every case and
   wrecks the flow. Removed from the tree; do not re-add without a new idea.
7. **Not wired into `gen_pcb.py`.** The PoC writes only into `build/layout/`;
   replacing the BFS/`col_y`/A\* code needs an ADR.

The forward plan, the force-model options and the prior-art reading list live in
[`RESUME.md`](../../RESUME.md) §8–§10.

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
