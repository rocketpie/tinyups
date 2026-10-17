# 0013 – One model, shared; A/B on neutral starts

- Status: proposed

## Context

Two things went wrong in the same way, twice, in one session:

1. The PoC's headless engine (`engines/d3force.mjs`) and the browser UI were two
   *copies* of one model. The copies drifted: the engine never called
   `forceLink.distance()/.strength()`, so its published numbers described a
   different force model than the UI's
   ([`docs/history/0002`](../history/0002-d3force-inert-link-params.md)).
2. To judge the new belongs-to force (ADR-0012) a *third* copy was written — a
   throwaway harness — which had to be checked against `render.py` before any
   number from it could be believed. (It also had a bug, `e.source.id` on an
   unresolved link endpoint, that silently disabled the force under test.)

At the same time, force-model questions were being answered on a **hand
placement**: `placements/try3.json` is half-solved by a human, and its 21 pins
encode that human's intent. A force change that "wins" from there may simply
agree with the human. The measurements that mattered (a range-limited clique
makes HPWL *worse*; the belongs-to ring helps) could only be trusted because they
were run from a neutral start, and even then the run-to-run spread was large
enough that several seeds are needed before a difference is real.

## Decision

1. **The model lives in exactly one module**: `hardware/layout_poc/web/public/model.js`.
   It owns the parameter defaults, the geometry, every force (link, charge,
   centre pull, keep-in, collision, velocity clamp, belongs-to ring), the host
   assignment, the scatter generator and the metric set. It takes `params`
   explicitly and reads it live.
   - the browser UI imports it as `./model.js` (the page's import map resolves
     `d3-force`, so no server change was needed);
   - node tools import it by path, resolving `d3-force` through
     `hardware/layout_poc/node_modules`.
2. **The UI is a view of that model, not a second implementation.** `app.js`
   keeps the scene, the interaction and the persistence; the UI's parameter
   `defaults` come from `model.js` (`d: DEFAULTS.KEY`), so a value cannot differ
   between the UI and a tool.
3. **`hardware/layout_poc/ab.mjs` is the A/B runner** (`make ab`): one row per
   config, N seeds, merged into the same table by the same code that produced the
   numbers. It reports HPWL, drawn wire, courtyard overlaps, off-board, power-path
   length, flow `axisR` **and the per-controller fan statistics** (mean distance
   of a controller's small parts, their inward bias, their spacing) — the metric
   the belongs-to force exists for.
4. **Neutral starts by default.** The runner starts from a scatter (the UI's own
   generator, so a headless start equals a UI *Scatter*) or from an engine output
   (`build/layout/pos-*`, `raw-*`, `leg-*`). It **warns** when pointed at a file
   under `placements/`, and it ignores a start file's pin flags unless
   `--keep-pins` is given — a hand placement's pins are exactly the bias to avoid.
5. **A difference is not a result until it survives the seeds.** The runner prints
   the min–max range per config; overlapping ranges mean "run more seeds", and
   the routing yardstick (ADR-0009 / the RESUME plan) still outranks every
   pre-route proxy here.
6. **The headless engine is expected to import the same module** when it is
   ported (RESUME step 3): that is what retires copy #1 for good.

## Consequences

- A model change is now visible in one diff, testable in one command, and
  reproducible in the UI. `make ab` needs no build step, no browser and no
  network.
- The UI gained the fan metrics (per controller, in the Metrics panel), because
  they are the *goal* of the belongs-to force and were previously invisible.
- `render.py` remains a second (python) implementation of the metric set for the
  rendered boards. The duplication is deliberate — it is the independent check
  that caught the Y-convention bug
  ([`docs/history/0001`](../history/0001-y-down-rotation-bug.md)) — and the A/B
  runner is anchored to it at t=0 (same HPWL/wire/overlaps on a given start).
- The first thing the runner found is in
  [`docs/history/0006`](../history/0006-host-force-on-neutral-starts.md): the
  belongs-to ring pays for its HPWL/wire win with power-path length and flow
  order when it is applied to the parts the power chain runs through, which is
  why `HOST_POWER` defaults to off.
