# 0002 – d3-force link parameters were inert

- **What:** the headless d3-force engines never applied their own per-link
  `distance`/`strength`; every run used d3's defaults instead.
- **Why it matters:** `D0`, `DK`, `DMAX`, `SIG_STR`, `POW_STR`, `WREF` had **no
  effect** — the width-weighted link model was not running.
- **Status:** fixed in the UI model
  ([`ui/placement/public/model.js`](../../ui/placement/public/model.js)); the
  headless engines were retired with the PoC.

d3-force **ignores** the `link.distance` / `link.strength` *properties*. Without
the `.distance()` / `.strength()` accessors it keeps its cached defaults (30 mm,
`1/min(degree)`), so the per-link values were dead data. It went unnoticed
because the output still looked plausible and nothing asserted on the parameters.

Wiring it correctly is not a drop-in: the intended rest lengths are 2–26 mm and a
two-part net gets clique weight 1 with up to `POW_STR`, so the `(l − distance)/l`
term diverges to `~1e109` within a few ticks from a dense start. The fix adds a
**velocity clamp** (`MAX_V`, default 3 mm/tick).

| config (legalised start, ~2000 ticks) | HPWL (mm) | overlaps | axisR |
| --- | --- | --- | --- |
| link params inert | 5923 | 0 | 0.66 |
| wired + rect-collide (UI default) | **≈4000** | **0** | **0.87** |
| wired + d3 circle-collide | ≈4430 | 1 | 0.63 |

**Gotchas:** d3-force caches force accessors, so a parameter change must re-set
them or it is silently ignored mid-run; headless Chrome throttles
`requestAnimationFrame`, so judge convergence by `alpha` or tick `sim.tick()`
explicitly rather than by wall-clock.
