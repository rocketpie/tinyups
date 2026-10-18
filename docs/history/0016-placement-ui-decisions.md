# 0016 – Placement UI: tracked state and the belongs-to force

Condensed from ADRs 0010–0012 when the placement PoC was retired
([0015](0015-placement-cleanup.md)); these are properties of `ui/placement/`, not
open decisions.

**Tracked tuning.** Every engine parameter is editable, and the values are not
throwaway: `SIG_STR`/`POW_STR`/`D0`/`DK`/`DMAX`/`MAX_V` decide whether the power
path collapses into a spine or a ring. They live in the tracked
`ui/placement/params.json` (values + the panel's row order), written by the UI on
every change. Precedence: built-in defaults < `params.json` < a deliberately
loaded seed's own `params`; `git checkout` undoes an experiment.

**Tracked placements.** A placement you dragged together is *authored*, not
generated, so **Save** writes `ui/placement/placements/<name>.json` in git. No
timestamp — a re-save is a byte-identical, no-op diff. The shape is the
engine-output shape, so `render.py`/`apply.py` accept it directly. Generated
output (graph, boards, DRC reports) stays in `build/`.

**Belongs-to force.** A part's membership in an IC rides on a *specific* net, but
the parts that drifted in a hand placement had only `GND` (a dropped plane) plus a
wide rail, and a clique pulls toward the net's **centroid** — the middle. No
clique knob can express "this cap belongs to *that* IC"
([0005](0005-the-netlist-cannot-hold-satellites.md)). The model therefore gained a
host force (`HOST_STR`/`HOST_D`, default 1.5 / 5 mm): the host is the IC with the
most *specific* shared net (`1/(k−1)`), ties broken by proximity, and the ring is
one-sided — only the small part moves, so a controller keeps the position it was
given. The assignment is visible in the inspector. It improves every metric
measured (hand placement `try3`, host off → on: HPWL 3821 → 3799, wire
3940 → 3871, overlaps 1 → 0).
