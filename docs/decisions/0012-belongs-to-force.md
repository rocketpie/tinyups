# 0012 – A "belongs-to" (host) force for small parts

- Status: proposed
- Extends the force model of [ADR-0009](0009-interactive-placement.md) point 5.

## Context

Placement of the controllers at the periphery worked, but **their small parts
did not stay with them**: in a hand placement (`placements/try3.json`, 5U1 at the
right edge) 20 of the LM5176's 23 attached passives sat *inward* of it at a mean
29 mm, with an inward bias (mean cosine between "part → controller" and
"controller → board centre") of **+0.57**. They crowded the middle instead of
fanning a short distance around their controller.

Two hypotheses were tested against the data before changing anything:

1. **The pull to board centre.** Measured on `try3` as `(centre - x)·CENTER_X`:
   with the user's own tuning (`CENTER_X/Y = 0.01`) it contributes 0.3–0.7 of a
   force unit where the net links contribute 30–110. **Ruled out** — turning it
   down further cannot fix this.
2. **The net cliques, via their far members.** Tested properly: a range-limited
   link model (a link stops pulling beyond `R ×` its rest length, smooth taper,
   re-set per tick) *should* have left each part held only by nearby net-mates.
   It did not: HPWL got worse (3888 → 4193 / 4020 / 4079 mm for R = 1.5/2/3),
   the satellites did not come closer (5U1: 29.1 → 32.9 / 33.0 / 31.9 mm) and
   R = 3 introduced a courtyard overlap. **Rejected.**

What the netlist actually says is the real problem. A part's membership in an IC
is carried by *specific* nets — `5C2` is tied to 5U1 by `N_BOOT1[k=2]`, `6C1` to
6U1 by `N_XIN[k=3]` — but the parts that drift are exactly the ones whose only
nets are `GND` (dropped: it is a plane) plus a wide rail (`3C2`, `5C1`, `6C4` are
`GND + VIN_SYS[k=12]`). A force that follows a net's clique pulls a part toward
that net's **centroid**, and a 12-pad rail's centroid is wherever the power parts
are — the middle. No knob on the clique can invent a locality the graph does not
contain.

## Decision

1. **The model gains a host ("belongs-to") force**, `HOST_STR` / `HOST_D` in the
   UI and `params.json`, default **1.5 / 5 mm** (`HOST_STR = 0` = off).
2. **The host is derived from the netlist once, at load**, by *specificity*:
   every IC sharing a net with the part scores `1/(k-1)` (a 2-pad boot net is
   worth 1.0, a 12-pad rail 0.09); the best score wins, and a tie — the bulk caps
   that share `GND + rail` with all of a rail's ICs equally — goes to the
   **nearest** IC. Parts with no IC on any kept net fall back to the nearest IC.
   Only small passives (`R/C/D/L`) get a host; ICs, connectors, FETs and
   inductors do not.
3. **The force is a ring around the host, and one-sided**: the part is pulled in
   beyond `HOST_D` and pushed out inside it, and *only the part moves*. A
   controller therefore keeps the position the user gave it while its parts
   arrange themselves around it — "fanning a small distance around the entire
   controller".
4. **The clique/link forces are left alone.** They are the right model for the
   power path and the rails; they are simply not an ownership statement.
5. **The assignment is visible**: the inspector shows `belongs to <ref> (net
   score …)`, and a selected part draws a dashed line to its host, so a wrong
   assignment can be seen rather than guessed. `place.assignHosts()` re-derives
   it after a large rearrangement.

## Consequences

- Measured on `try3` (1001 ticks, its own params), host force vs. no host force
  at the same keep-in force (`BOUND=400`): HPWL 3821 → **3799**, drawn wire
  3940 → **3871**, courtyard overlaps 1 → **0**, 5U1 satellites 28.7 → 26.1 mm
  with inward bias 0.53 → 0.37, 6U1 24.2 → 21.0 mm and 0.30 → 0.13, and their
  spacing improved slightly. The force improves every metric we measure,
  including legality — it is not a trade.
- With the placement's own `BOUND=1` the parts can be pushed off-board (1–3
  parts), because a ring around an edge-placed controller reaches the edge: the
  keep-in force has to be doing its job. Documented in
  [`docs/history/0005`](../history/0005-the-netlist-cannot-hold-satellites.md).
- The UI and the headless PoC engine now differ by one force: `engines/d3force.mjs`
  has no host force, so a UI session and a `make layout` run are not the same
  model until the pending engine port (RESUME step 1) carries it over.
- The host assignment is a *heuristic over an under-specified netlist*. It is
  deliberately simple, visible in the UI, and cheap to replace — if it turns out
  that assignment should be per-part editable, that is a follow-up decision.
