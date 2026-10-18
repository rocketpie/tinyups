# 0005 – The netlist cannot hold a small part beside its IC

**What:** in a hand placement the controllers sat where the user wanted them (at
the periphery), but their attached passives drifted inward and crowded the
middle — `5U1` (LM5176): 20 of 23 small parts on the centre side, mean **29 mm**,
inward bias **+0.57**.

**Why (measured, not guessed; `placements/try3.json`, its own params):**

| hypothesis | test | result |
| --- | --- | --- |
| pull to board centre | force decomposition | `(centre−x)·CENTER_X` is 0.3–0.7 force units against 30–110 from the net links — innocent |
| the clique's *far* members | range-limited links (R = 1.5/2/3) | HPWL 3888 → 4193/4020/4079, satellites *farther* (29.1 → ~33 mm), an overlap at R=3 — rejected |

The netlist is what is missing. A part's membership in an IC rides on a
*specific* net, but the parts that drift have only **`GND` (a dropped plane) + a
wide rail** (`5C1`, `3C2`, `6C4` are `GND + VIN_SYS[k=12]`). A clique pulls a
part toward the net's **centroid**, and a 12-pad rail's centroid is where the
power parts are — the middle. No clique knob, weight split or range limit can
express "this cap belongs to *that* IC".

**Fix:** an explicit, derived ownership — a "belongs-to" (host) ring force
(`HOST_STR`/`HOST_D`, condensed in
[0016](0016-placement-ui-decisions.md)). Host = the IC with the most *specific*
shared net (`1/(k−1)`, so a 2-pad boot cap scores 1.0 and a 12-pad rail 0.09),
ties by proximity; only the small part moves.

**Measured** (`try3`, same keep-in `BOUND=400`, host off → on): HPWL 3821 →
**3799**, wire 3940 → **3871**, overlaps 1 → **0**, 5U1 satellites 28.7 → 26.1 mm
(bias 0.53 → 0.37), 6U1 24.2 → 21.0 mm. Every metric improves.

**Gotcha:** with the placement's own `BOUND=1` the ring around an edge-placed
controller pushes 1–3 parts past the board edge — raise `BOUND` (order 100–400)
before judging one.
