# 0002 – d3-force link parameters were inert

- **What:** `engines/d3force.mjs` (and `d3force_incremental.mjs`) never applied
  their own link force parameters; every headless `d3-force` run used d3's
  defaults instead.
- **Why it matters:** `D0`, `DK`, `DMAX`, `SIG_STR`, `POW_STR`, `WREF` had **no
  effect** — the "a 20 A net pulls ~50× harder than a signal net" model was not
  running.
- **Status:** fixed in the interactive UI
  ([`web/`](../../hardware/layout_poc/web/), ADR-0009). **Not yet ported** into
  the headless engines.

## The defect

`engines/d3force.mjs` builds each link with a per-link `distance` and `strength`:

```js
const links = G.edges.map((e) => ({
  source: e.source, target: e.target, width: e.width, current: e.current,
  distance: Math.min(DMAX, D0 + DK * (e.width / WREF)),
  strength: per * (SIG_STR + (POW_STR - SIG_STR) * (e.width / WREF) ** 1.2),
}));
```

…and then:

```js
d3.forceLink(links).id((d) => d.id).iterations(2)   // no .distance()/.strength()
```

d3-force **ignores** the `link.distance` / `link.strength` *properties*. Without
the setter it keeps its cached defaults: `distance = constant(30)` (mm) and
`strength = 1 / min(degree)`
(`node_modules/d3-force/src/link.js`, lines 16–19). So the per-link values were
dead data. Only `CHARGE`, `CHARGE_SIZE`, `CENTER_X/Y`, `BOUND`, `ITERS`, `SEED`
did anything.

It went unnoticed because the output still *looked* plausible (HPWL 5840 for
`d3-force` in the PoC table) and nothing asserted on the force parameters.

## The fix, and why it needs a velocity clamp

Wiring it correctly is **not** a drop-in:

- the intended rest lengths are 2–26 mm, and
- a two-part net gets clique weight 1 with up to `POW_STR` (= 10),

so `forceLink`'s `(l − distance)/l` term blows up when the dense start (the
legalised baseline) puts two linked parts closer than the rest length — the
simulation diverges to `~1e109` within ~4 ticks.

Two changes make it stable and *better*:

1. call `.distance()`/`.strength()` (and re-set the accessors on every parameter
   change — d3 caches them), and
2. clamp velocity each tick `MAX_V` (default 3 mm/tick).

## Numbers (from the legalised baseline, ~2000 ticks)

| engine / config | HPWL (mm) | overlaps | axisR |
| --- | --- | --- | --- |
| PoC `d3-force` (link params inert) | 5923 | 0 (after legalise) | 0.66 |
| wired + rect-collide (UI default) | **≈ 4000** | **0** | **0.87** |
| wired + d3 circle-collide | ≈ 4430 | 1 | 0.63 |

The un-wired engine was leaving ~25–30 % on the table, and the power flow
(`axisR`) is clearly better once the width-weighted link force actually runs.

## Gotchas learned here

- **d3-force caches force accessors.** `strength`/`distance`/`radius` are
  evaluated once in `initialize()` and stored. Changing a parameter means
  re-calling the setter (`.strength(fn)`, `.distance(fn)`, …) or the change is
  silently ignored mid-run.
- **`forceLink` ignores `link.distance`/`link.strength` properties.** They are
  only read if you pass an accessor.
- **Headless Chrome throttles `requestAnimationFrame`.** Timing a solve by
  wall-clock in Puppeteer under-counts ticks — a 26 s wait reported HPWL 8232
  (unconverged) while driving `sim.tick()` 2000× gave 4000. Judge convergence by
  `alpha`, or tick explicitly.
- **`exec node server.mjs` in a background shell dies with the harness session.**
  Detach long-running servers with `setsid`/`nohup`.
- **`devcontainer.json` is JSONC** (comments allowed), but a running container
  does not pick up `runArgs` changes — recreate it. See
  [`.devcontainer/PORTS.md`](../../.devcontainer/PORTS.md).

## Follow-up (still open)

1. Port the `.distance()`/`.strength()` wiring + `MAX_V` clamp into
   `engines/d3force.mjs` and `engines/d3force_incremental.mjs`.
2. `make layout` + refresh the score table in
   [`hardware/layout_poc/README.md`](../../hardware/layout_poc/README.md).
3. Route the baseline (FreeRouting) and report **routed wirelength / vias /
   DRVs** — the field's yardstick, still unrun.

## References

- [`docs/decisions/0009-interactive-placement.md`](../decisions/0009-interactive-placement.md)
- [`hardware/layout_poc/web/README.md`](../../hardware/layout_poc/web/README.md)
- [`hardware/layout_poc/engines/d3force.mjs`](../../hardware/layout_poc/engines/d3force.mjs)
- `node_modules/d3-force/src/link.js`
