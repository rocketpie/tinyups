# RESUME — TinyUPS

**Start here in a fresh session.** Handoff: what changed
this session, the plan, current numbers, and how to continue. 

## 1. Where we are

The **placement problem** now has a working PoC, measured harness. 
The hand-written power-first placer in `gen_pcb.py` is still what builds
the board — the new work lives beside it in `hardware/layout_poc/` and has **not**
been wired in yet.

| Area | State |
| --- | --- |
| Schematic | ✅ generated, **ERC-clean** (124 parts, 115 nets) |
| Placement | 🔄 **two tracks**: the old staged hand-placer (`gen_pcb.py`, `PCB_STAGE=1/2/3`) and the new **graph-derived PoC** (`hardware/layout_poc/`, best candidate: **graphviz sfdp**) |
| Routing | ⬜ not routed |
| Power / ampacity | ❌ unchanged — still `make power` FAIL, no pours yet |
| Test plan / DVT | not started |

**Board:** 150×140 mm, 124 footprints, 115 nets. The board on disk
(`hardware/tinyups.kicad_pcb`) is the **stage-2** build (30 footprints) and is
untouched by the PoC — the PoC writes only into `build/layout/`.

Commands added this session:

```sh
make layout     # netlist -> graph -> 7 engines -> fit -> legalise -> render + score
make mermaid    # render the graph as a real mermaid flowchart (SVG)
```

## 2. The new approach in one paragraph

Build a **graph** (components → nodes, nets → edges) and let an existing layout
engine place the parts, then **legalise** the result into a real PCB placement.
The reusable half is the legaliser, not the engine: engines give *structure*, and
a placement only becomes legal after rotation + de-overlap + grid snap.

```
build/tinyups.net
   │ extract.py        nodes = components (courtyard size, pads, block, flow pos)
   ▼                   edges = per-net CLIQUE, weight = IPC-2221 width
build/layout/graph.json
   │ engines/*         d3-force · d3-force-incr · dagre (mermaid) · ELK · graphviz
   ▼
raw-*.json  →  fitpos.py (orient + fit)  →  legalize.py (rotate, de-overlap, snap)
   ▼
pos/leg-*.json  →  render.py (PNG/SVG + metrics)  ·  apply.py (→ real board + DRC)
```

## 3. Results (124 parts, 150×140 mm, GND dropped)

```
stage  engine                    HPWL    wHPWL   wire  ovl  out  axisR    in   out
--------------------------------------------------------------------------------------------
legal  graphviz:sfdp+legal       3288    11435   3703    0    0   0.59    62    16   << winner
legal  graphviz:neato+legal      3861    12855   4006    0    0   0.53    73    27
legal  d3-force+legal            5840    16839   6100    0    0   0.76    44    18
legal  d3-force-incr+legal       5672    17573   6162    1    0   0.66    17    16
legal  elk+legal                 4398    15234   5520    9    0   0.74    23    45
legal  dagre+legal               5115    15672   6031   20    0   0.59    58    78
legal  graphviz:dot+legal        4983   12425   5699   16    0   0.67    58     9
--------------------------------------------------------------------------------------------
hand floorplan (prior state):    8304    15476
```

* `HPWL` = Σ per-net pad bounding-box (w+h). `ovl` = courtyard overlaps,
  `out` = off-board, both must be 0.
* `axisR` = corr(part's flow position, position along the input→output axis).
  Higher = the power parts walk input→output in electrical order.
* `in`/`out` = distance from the first/last power part to its terminal.

**sfdp wins**: lowest HPWL (**−60 % vs the hand floorplan**), legalises to zero
overlaps, and — per the maintainer's own eye — has the cleanest main path, no
crossings, visible branching. **neato** is second. The d3-force variants are the
only ones with a strong flow ordering, but their wirelength is ~1.7× worse.

Reproduce: `make layout`, then `python hardware/layout_poc/compare.py`.
Renders: `build/layout/contact-sheet.png` (all 7) and `<engine>.png|.svg`

## 4. Decisions made (and why)

| Decision | Reason |
| --- | --- |
| **GND dropped from the graph** | it is a plane; as a 71-part net it glued everything into a hairball |
| **No power-corridor keep-out** | the corridor belongs to the hand floorplan, not a graph-derived placement |
| **Only `1J1` (XT60 in) + `5J2` (XT30 out) pinned** | the two terminals of the power path; all other connectors move freely |
| **Per-net cliques, not an MST** | a net is electrically one node, so *any* spanning tree is valid — and an MST rooted `+3V3` at `2R11`, which *looked* like the part had 12 connections. Clique = textbook HPWL model, no fake hub, total weight bounded by the net's required width |
| **Edge weight = connection current, not net current** | `5U1`'s pins on `N_CS`/`SW1_OUT` (17 A) are *sense* pins — the chip carries milliamps. `min(conducted(a), conducted(b))`, with `conducted()` = rail current for series elements/shunts, ripple RMS for caps, 0.1 A for IC/diode/bias, and `power_map.OVERRIDES` for the fan/cell-sense headers |
| **Free-orientation search in `fitpos.py`** | stress/layered engines don't know which end is the input; their orientation is free. Try the 8 orientations, keep the best `axisR`. Flipped sfdp −0.76 → +0.75 |
| **Two graphs: clique for solving, path/star for drawing** | the clique is too dense to look at; drawing uses the current-ordered path, or a star from the hub (largest part) for pure distribution rails |

## 5. Rejected / tried and dropped

* **Staging** (solve the power parts only, freeze them, fit the rest around them).
  Implemented as a generic two-pass wrapper for *every* engine. Didn't do much, for lots of complexity. reverted.
* **Dropping `+3V3`** it is a 1 A distribution rail and needs routing. Dropping it buys ~nothing and would strand `6C4`. Adopted clique instead.

## 6. Legality: verified against KiCad's own DRC

```sh
python hardware/layout_poc/apply.py build/layout/leg-gv-sfdp.json
```

builds the full board into `build/layout/board.kicad_pcb` and runs
`kicad-cli pcb drc` on it: **0 courtyard overlaps, 0 board-edge issues.** The
remaining items are pre-existing and unrelated to placement (289 unconnected —
nothing is routed; `5U1`'s own pads at 0.15 mm; `1J1`'s pad vs the edge).

Note the legaliser must use the **courtyard** bbox (`fp.GetCourtyard`), not the
body bbox, or DRC still finds overlaps.

## 7. Key files

| File | Role |
| --- | --- |
| `layout_poc/extract.py` | netlist → `graph.json`: courtyard sizes, pads, flow position, cliques, IPC-2221 widths, connection currents |
| `layout_poc/engines/d3force.mjs` | d3-force, width-weighted links |
| `layout_poc/engines/d3force_incremental.mjs` | adds power parts one at a time in flow order |
| `layout_poc/engines/dagre.mjs` | dagre = the mermaid flowchart engine |
| `layout_poc/engines/elk.mjs` | elkjs layered + orthogonal edge routing |
| `layout_poc/engines/graphviz.py` | dot / neato / fdp / sfdp / osage (the **winner**) |
| `layout_poc/fitpos.py` | free-orientation search + fit to the board + pin connectors |
| `layout_poc/legalize.py` | rotation from pad centroids, de-overlap, worst-first hard pass, grid snap |
| `layout_poc/render.py` | SVG/PNG renders (2×, mnemonic labels, legend) + metrics |
| `layout_poc/compare.py` | the score table |
| `layout_poc/apply.py` | write a placement into a real board and DRC it |
| `layout_poc/README.md` | the full write-up |
| `layout_poc/mermaid.py`, `render_mermaid.sh` | flowchart source + real render |
| `layout_poc/experiments/sfdp_seeds.py` | the (refuted) seeding experiment |
| `hardware/gen_pcb.py` | **unchanged** — the hand placer that still builds the board |

Environment added (and mirrored in `.devcontainer/Dockerfile`): graphviz +
`libgvplugin-neato-layout8`, nodejs/npm, and the python deps
`networkx grandalf pydot shapely scipy matplotlib`. The JS deps live in
`hardware/layout_poc/package.json` and install on demand (`make layout`).

## 8. Next levers

In rough priority order:

1. **Residual overlaps on tight engine layouts** (dagre 20, dot 16, elk 9) — the
   local de-overlap has nowhere to push in a compressed layout.
   Needs a global spreading term.
   analyze de-overlap and Make sure it does not mess up layout engine results.
2. **Signal parts are unconstrained** — decoupling-cap ↔ its IC proximity is only
   implicit. The cliques give each cap a pull toward its net's centre, not toward
   its IC. Investigate and analyze.
   adding clique regressed sfdp performance
   legal  graphviz:sfdp+legal       2929    11094    2705    0    0    660   0.75    59    53   << prior
   legal  graphviz:sfdp+legal       3288    11435    3703    0    0    700   0.59    62    16   << now using cliques
   constrain to +3V3? revert?
3. **sfdp's weak spot is the chain endpoints** (`in 62 / out 16` mm). Try a much
   stronger pull on the two power terminals, or seed them.
4. **Adopt, Route it and find out for real**
   Use the best candidate, currently sfdp, 
   Wire `extract → sfdp → fitpos → legalize` into `gen_pcb.py`
   behind a flag (e.g. `PCB_PLACE=layout`) until proven.
   HPWL is a proxy; `sfdp`'s −60 % may not
   survive routing. `hardware/route.py` already drives freerouting — route the
   sfdp board and compare against the hand floorplan (tracks, vias, completion,
   `routing_report.py`).
5. **Best-of-N per engine** — reseeding drastically changes grpahs.
   moves `|axisR|` by 0.2–0.3 and HPWL by a few percent, so best-of-5 might be worth the effort.

## 9. Ideas on the list (next sessions)

### A. Anchor the layout to the two terminals (decaying pull)

*Proposed:* give every part an extra **tether** toward the nearest terminal, with
the strength cut by ~20 % per graph hop from it:

```
strength(part) = T0 * 0.8 ** hops(part, terminal)
```

So parts electrically close to the input hang near the input, the chain is
anchored at *both* ends, and the middle stays free. This directly targets the
weak spot in §3: sfdp's chain endpoints sit **62 mm / 16 mm** from their
terminals. Cheap to try as a custom d3 force; in a quadratic placer (§B) it is
just a linear term.

### B. Force model — what are we actually using?

Current: d3's `forceLink` (linear spring: `.distance()` + `.strength()`) plus
`forceManyBody` + `forceCollide`. That is the *ad-hoc* end of force-directed
layout. Options, roughly in order of principle:

| model | what it is | why / where |
| --- | --- | --- |
| **d3-force link options** | the link-force demo: `.distance()`, `.strength()` (e.g. `1/min(degree)`), `.iterations()` | cheapest experiments — e.g. make `distance` a function of width *and* hop distance, degree-based strength |
| **quadratic placement** | minimise `Σ w_ij (x_i−x_j)²` (+ y), terminals fixed → **sparse linear solve** | deterministic, fast, no iteration tuning; natural home for §A. Known flaw: collapses to the centroid without a density term |
| **electrostatic / density penalty** (ePlace/RePlAce/DREAMPlace) | quadratic + density forces (= modifying the linear system's RHS) | modern state of the art; overkill, but see §C |
| **simulated annealing** (OpenROAD SA-PCB) | stochastic moves | handles **rotation and irregular shapes natively** — i.e. our separate legalisation step |

### C. Prior art — we are not the first (verified leads)

* **Cypress** — "VLSI-Inspired PCB Placement with GPU Acceleration", Cornell,
  ISPD 2025 (`csl.cornell.edu/~zhiruz/pdfs/cypress-ispd2025.pdf`). Closest thing
  to this exact task.
* **OpenROAD SA-PCB** — open-source simulated-annealing PCB placer, **supports
  component rotation**.
* **HiePlace** — hierarchical PCB placement, TCAD 2026; irregular components,
  alignment, component priority.
* **NS-place** — "Net Separation-Oriented PCB Placement", arXiv 2210.14259;
  validates on **routed** wirelength with an open-source router — the validation
  method we still owe ourselves (§8 lever 4).
* **DREAMPlace / ePlace / RePlAce / mPL** — the analytical placement lineage.
* **Stress majorization** — Wikipedia "Force-directed graph drawing"; Brown's
  *Force-Directed Drawing Algorithms* handbook chapter; Dwyer/Koren/Marriott,
  "Constrained graph layout by stress majorization and gradient projection".
* **Davidson & Harel 1996** — simulated annealing for graph drawing.
* **Survey**: Cheong et al., *Force-directed algorithms for schematic drawings
  and placement: A survey* (2020) — directly on point.
* **Local win:** `elkjs` ships **8 algorithms** (verified by probing the
  installed build): `layered` (the one we used) plus **`force`, `stress`,
  `mrtree`, `rectpacking`, `disco`, `box`** and `random` (`spore` throws). Each
  is a one-line `elk.algorithm` swap — the cheapest experiment available.
* Also worth a look: **OGDF** (SpringEmbedderKK, StressMinimization, orthogonal
  layouts), **Adaptagrams / libcola** (constraint-based layout with *separation
  constraints* — non-overlap by construction), **graph-tool** (SFDP/ARF/module
  layouts), **igraph** (FR, Kamada-Kawai, Davidson-Harel, DrL, GEM).

### D. Power-components-only pass, per model

Run every engine on the **power subgraph alone** (26 parts + the 2 terminals) and
render/measure it. Rationale: (i) simple enough to judge by eye; (ii) isolates
the force model from the 98 signal parts; (iii) it is the stage-1 diagnostic that
the rejected staging approach never showed on its own. `extract.py` already has
everything needed (power flag, flow position) — a power-only graph is a filter
away (that is all the removed `stage.py` did).

## 10. First thing next

Cheapest first experiments: **§C's `elk.algorithm` swaps** and **§D's
power-only pass** — both are configuration, not new code.
