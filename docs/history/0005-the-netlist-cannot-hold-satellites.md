# 0005 – The netlist cannot hold a small part beside its IC

**What:** In a hand placement the controllers sat where the user wanted them (at
the periphery, "outside" the power components), but their attached passives
drifted inward and crowded the middle: for `5U1` (LM5176) 20 of 23 small parts
sat on the board-centre side of it at a mean **29 mm**, with an inward bias
(mean cosine between "part → controller" and "controller → centre") of **+0.57**.

**Why — measured, not guessed** (all on `placements/try3.json`, 1001 ticks, the
placement's own params: `D0=3 DK=0 POW_STR=35.9 CHARGE=0 CENTER 0.01`):

| hypothesis | test | result |
| --- | --- | --- |
| the pull to board centre | force decomposition at each satellite | `(centre-x)·CENTER_X` is **0.3–0.7** force units against **30–110** from the net links. Innocent — turning it down cannot fix this |
| the clique's *far* members | range-limited links (pull ceases beyond `R ×` rest, smooth taper, re-set per tick) | HPWL 3888 → **4193/4020/4079** for R=1.5/2/3, satellites *farther* (29.1 → 32.9/33.0/31.9 mm), one overlap at R=3. Rejected |

The netlist is what is missing. A small part's membership in an IC rides on a
*specific* net (`5C2` → 5U1 via `N_BOOT1[k=2]`; `6C1` → 6U1 via `N_XIN[k=3]`),
but the parts that drift have only **`GND` (dropped — a plane) + a wide rail**:
`5C1`, `3C2`, `6C4` are `GND + VIN_SYS[k=12]`, `2R6/2R7` are `GND + I2C[k=4]`. A
clique pulls a part toward its net's **centroid**; a 12-pad rail's centroid is
where the power parts are — the middle. No clique knob, weight split or range
limit can express "this cap belongs to *that* IC", because the information is not
in the kept graph.

**Fix:** an explicit, derived ownership — a "belongs-to" (host) ring force
(`HOST_STR`/`HOST_D`, [ADR-0012](../../docs/decisions/0012-belongs-to-force.md)).
Host = the IC with the most *specific* shared net (`1/(k-1)` per net, so a 2-pad
boot cap scores 1.0 and a 12-pad rail 0.09), ties by proximity. Only the small
part moves, so a controller keeps its place and its parts fan around it.

**Measured effect** (`try3`, same keep-in force `BOUND=400`, host off → on
1.5/5 mm): HPWL 3821 → **3799**, wire 3940 → **3871**, overlaps 1 → **0**,
5U1 satellites 28.7 → 26.1 mm (bias 0.53 → 0.37), 6U1 24.2 → 21.0 mm
(0.30 → 0.13), spacing slightly up. Every metric improves, including legality.

**Gotcha found on the way:** with the placement's own `BOUND=1`, the ring around
an edge-placed controller pushes 1–3 parts past the board edge — the keep-in
force was effectively off. Raise `BOUND` (order 100–400) before judging an
edge-placed controller.

**Status:** host force implemented in the UI (`web/public/app.js`), the
assignment is visible per part (inspector + a dashed line to the host) and
`place.assignHosts()` re-derives it. The headless engine does not have it yet —
see RESUME step 1.
