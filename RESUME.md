# RESUME — TinyUPS

**Start here in a fresh session.** Handoff: what changed
this session, the plan, current numbers, and how to continue. 

## 1. Last's sessions focus
The immediate focus is finding a
working **PoC for sane power-component placement** — that's section 3.


## 2. Status at a glance

| Area | State |
| --- | --- |
| Schematic | ✅ generated, **ERC-clean** (129 symbols, 115 nets) |
| Placement | 🔄 **power-first, staged** (`PCB_STAGE=1/2/3`); power placement is a PoC, still overflowing |
| Routing | ⬜ not routed (rebuild in progress) |
| Power / ampacity | ❌ 10/10 nets FAIL (`make power`) — no pours yet |
| Fabrication / DVT | not started |

Board 150×140 mm · 124 footprints · 115 nets. Reference designators are
**block-flow numbered**: leading digit = position in the power flow, then type +
per-block counter — `1F1` (input fuse), `2R1` (charger R), `3Q1` (priority path),
`4Q1` (BMS FET), `5R7` (output-regulation R), `6U1` (RP2040). Connectors keep
their `J` numbers (`1J1` XT60, `5J2` XT30, `4J6` PACK, `4J7` CELLS).

## 3. Focus: the power-placement PoC

**Goal:** place the power-handling parts sensibly along a reserved power path,
not by shelf-packing. 26 "power" parts (defined by `power_map.py`).

### The reserved corridor

The pour needs width — IPC-2221, 10 °C rise: **20 A ≈ 19 mm on 1 oz outer
copper, ≈ 10 mm on 2 oz**. `blocks.CORRIDOR_TARGET_MM = 20` is drawn as a
silkscreen box down the middle; **parts stay out of it**. Parts are assigned a
side: **left = blocks 1,3,5,6** (input protection, priority, output regulation,
control), **right = blocks 2,4** (charger, BMS).

### The algorithm (`gen_pcb.py`, `STAGE >= 2`)

1. Place the fixed connectors (`ANCHORS`).
2. Order the power parts: **BFS from `1J1` over shared power nets**.
3. **Rotate** each part (snapped to 90°): the pad on a **rail net** faces the
   corridor; a pad on a **local node** points *up* (toward its partner part).
4. Place each part, then **hill-climb** its position: step along the grid, keep
   if the routed length (grid A*) improves, else halve; stop at `step < 2 mm`
   or 20 steps; back off on collision.
5. Column = **chain depth from `+12V_IN`** (x), stacked by the BFS order (y).

Parameters (env, PoC-coarse): `PP_GRID PP_CLEAR PP_TARGET PP_MINSTEP PP_BRANCH
PP_MAXSTEPS` (2 mm, branch 10 mm, steps 20) and `COLW = 11 mm`. Runtime ~6–7 s.

### Attempts so far (rows = approach)

| # | Approach | Result | Overflow | Note |
| - | -------- | ------ | -------- | ---- |
| 1 | shelf, one column per side | stacks single-file | **219 mm** | 13 parts/side × ~15 mm |
| 2 | 1-D line search toward the target pad | still stacks | 219 mm | objective pulls each part *up* to the previous |
| 3 | 2-D hill-climb (4 grid dirs) | still stacks | 229 mm | lateral moves don't shorten the chain edge |
| 4 | **two columns per side** + 2-D | **fits** | none | seed alternately inner/outer, then hill-climb |
| 5 | columns = chain depth (from *all* rails) | scattered | 161 mm | depth collapses to 1 for parts between two rails |
| 6 | columns = chain depth from `+12V_IN` | monotonic columns | **182 mm** | current state — see below |

**Current state (attempt 6)** — depth from `+12V_IN` only, first column at the
clearance (off-by-one fixed), depth clamped to 6 (unreached nets like `CELL0`
gave `depth=99` → `x≈1190`). Columns read rail → FET → node → L → node → FET:
- left: `1F1`(col1) `1R1`(2) `1Q1`(3) `1C2/1C3` `3Q1` `5Q1` `5Q2` `5Q3` `5Q4` `5L1` `5C9` `5R3`
- right: `2R2` `2L1` `2Q1` `2Q2` `2Q3` `2Q4` `2R1` `4Q1` `4Q2` `4R1`

Still overflows 182 mm (user said *don't* fight overflow yet — wants to see it).

### Open problems / next levers

1. **x and y are decoupled.** `x` = chain depth, `y` = BFS stacking order, so a
   part can be in column 1 yet stacked far down. **Drive `y` from the flow
   order** so the path runs top→bottom.
2. **Columns are wide (11 mm).** A depth-6 part sits ~55 mm from the corridor,
   so the converter loop reads as "spread out". Options: smaller `COLW`, lower
   depth cap, or **per-branch depth** (count each branch's chain from the rail
   it taps, keeping the charger/converter loops compact).
3. **Overflow.** Once the columns are right, the parts need 2–3 abreast per
   branch — the current `y` cursor is per (side, depth) only.
4. **The A\* only routes the one chain edge** and doesn't block earlier edges'
   traces; add that (mark routed cells) so edges don't overlap.
5. **Branch/merge gaps**: currently `PP_BRANCH = 10 mm` when the shared net
   fans out to ≥3 parts. Worth verifying it lands on the right nodes.
6. Then **stage 3**: fill the signal parts around the placed power parts
   (already sketched: shelf into the leftover strips), then **Stage 4: pours**
   (F.Cu power pour sized to current, GND on In1, net classes, `route.py` marks
   the power/plane layers in the DSN, re-route).

### Design notes the PoC depends on

- **Not every power part connects to the pour.** Rail-tapping parts do; series
  parts sit between two local nodes (`2L1` is `SW1↔SW2`, between `2Q1` and
  `2Q2`) — that's why the rotation rule splits on rail vs local nets.
- **Objective must be constrained** — pure "shortest connection" collapses the
  part onto the previous one. Constrain: no clearance violation + stay on side.
- **Routed length is discontinuous** → line/coordinate search with a halving
  step, not a true gradient.
- **Determinism**: fixed grid (2 mm), fixed order, so reruns match.

## 4. Metrics (current)

```
placement: total HPWL 8304 mm · weighted 15476 mm · decap 14.6 mm
           power parts 26 · mean |dx| to centre 12.3 mm · straightness 4.14
power:     10/10 nets FAIL (no pours yet)     gates: ERC 0 · test 6/6
```
`place_metrics.py` scores power parts by distance to the corridor **edge**
(`|dx| − CORRIDOR_MM/2`) and flow straightness. Reproduce: `make erc`,
`make power`, `make render`, `make silk`,
`python hardware/{place_metrics,routing_report,power_map}.py`.

## 5. Staged board generation

```sh
PCB_STAGE=1 python hardware/gen_pcb.py   # connectors + corridor silk box
PCB_STAGE=2 python hardware/gen_pcb.py   # + power components (the PoC)
PCB_STAGE=3 python hardware/gen_pcb.py   # + everything else (fill)
make render                              # -> build/tinyups.png
```
The stage renders are `build/tinyups-stage2.png` (stage 1 dropped on request).

**Rebuild flow (full):**
```sh
make netlist && make bom
python hardware/gen_schematic.py
PCB_STAGE=3 python hardware/gen_pcb.py
python hardware/fill_zones.py
python hardware/power_silk.py
FREEROUTING_JAR=/opt/freerouting/freerouting.jar python hardware/route.py
python hardware/set_sheet.py
```

## 6. Key files

| File | Role |
| --- | --- |
| `hardware/blocks.py` | **single source** of block membership, the ref scheme, `CORRIDOR_MM`/`CORRIDOR_TARGET_MM`, `kind(ref)` |
| `hardware/gen_pcb.py` | board build + **staged placement PoC** (rotation, depth, A*, hill-climb) |
| `hardware/gen_schematic.py` | schematic (applies the ref scheme at build) |
| `hardware/power_spec.py` | design current + rail voltage per net |
| `hardware/power_map.py` | per-component power map → `build/power-map.csv`; "power-handling" definition |
| `hardware/power_silk.py` | marks power parts on F.Silkscreen (`make silk`) |
| `hardware/place_metrics.py` | HPWL, decap, **power-path score** |
| `hardware/route.py` | freerouting flow (Stage 4) |
| `hardware/themes/tinyups-red.json` | red-silk theme for `make silk` |

## 10. First thing next

Pick one lever from §3 and iterate, rendering each time:
**(a)** drive `y` from flow order (x and y coupled), or
**(b)** per-branch depth / smaller `COLW` to compact the converter loops, or
**(c)** verify the branch gaps, then move on to stage 3 + pours.
