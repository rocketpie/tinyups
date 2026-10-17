# 0010 – The placement tuning lives in a tracked file

- Status: proposed
- Amends [ADR-0009](0009-interactive-placement.md) point 6 ("`hardware/` and the
  tracked board are not touched"), for one file only.

## Context

ADR-0009 built the interactive placement UI with *every* engine parameter
editable, and left the values nowhere durable: a run was configured by sliders
in the tab, and only a "Save" of the *positions* recorded them (inside
`build/layout/interactive-<name>.json`, which is untracked). Nothing said which
knobs a human had actually decided on, and no tuning could be reviewed, compared
or reverted.

The values are not throwaway. `SIG_STR`/`POW_STR`/`D0`/`DK`/`DMAX`/`MAX_V`
decide whether the power path collapses into a spine or a ring — that is a
*design* input to the board, not a view setting. The PoC's numbers were produced
by a config that exists only as inline `env` assignments in `run_all.sh`
(`ITERS=1200 CHARGE=30 node engines/d3force.mjs …`), so a tuning cannot be
reproduced from the repository alone. The engine reads its parameters from the
environment under exactly the names the UI uses — the two are already the same
vocabulary, they just have no shared home.

Constraints that shaped the answer:

- The tuning must be **reviewable and revertable** — a file in git, not browser
  storage: `git checkout` must undo a bad experiment, and `git diff`/`git log`
  must show what changed and when.
- It must be **editable where the experiment happens** (the UI), not only by
  hand — a tuning that has to be copied between a tab and an editor will drift.
- It must stay **engine-neutral**: the same keys must work for the headless
  PoC engine, and for whatever replaces it.
- It must not become a second source of truth for the placement itself.

## Decision

1. **`hardware/layout_poc/params.json` is the placement tuning**, tracked in
   git, with the engine's own parameter names as keys:

   ```json
   { "_comment": "…", "params": { "SIG_STR": 0.1, "POW_STR": 10, … },
     "order": ["POW_STR", "SIG_STR", …] }
   ```

   `params` holds values, `order` the panel's row order (which is how "these are
   the knobs that matter" gets recorded) and is **absent while it is the default
   order**. A key may be omitted to fall back to the built-in default, so the
   file can shrink to exactly the tuned knobs; the UI writes the full set it is
   running. `_comment` is free text and is preserved on writes.

2. **The UI is its editor, and it writes the file.** The Engine panel PUTs to
   `/api/params` (dependency-free handler in `web/server.mjs`; key names and
   value types are validated) on every change — debounced 700 ms, flushed with
   `sendBeacon` when the tab goes away. Writing is what makes the tuning durable;
   there is no separate "commit my tuning" step, because git already is the undo
   button.

3. **Precedence.** Built-in defaults < `params.json` < a *deliberately* loaded
   seed file's own `params` (`pos-*.json`, `interactive-*.json`) <. A seed's
   params are a session override: they are not written back until a parameter is
   changed, at which point the file records what is actually being run.

4. **Only this file, and only for tuning.** The rest of ADR-0009 point 6 stands:
   the UI still reads `build/layout/` and writes only `build/layout/*`
   (untracked). `params.json` is *not* part of the board; the board and
   `gen_pcb.py` stay untouched, and swapping them in still needs its own ADR.

5. **The file is not yet wired into the headless engine.** `engines/d3force.mjs`
   still takes its values from the environment (or its defaults). Making it read
   this file is part of the engine work in
   [`docs/history/0002-d3force-inert-link-params.md`](../history/0002-d3force-inert-link-params.md)
   and the RESUME plan, because porting it changes the PoC's scores and the
   published table.

## Consequences

- The tuning has a history: `git log -p hardware/layout_poc/params.json` is the
  record of which parameters turned out to matter, and a clobbering experiment is
  undone with `git checkout`.
- A running UI can now write a **tracked file** as a side effect of dragging a
  slider. That is deliberate but worth knowing: a slider you nudge and forget is
  a diff. Anything that would be noise (the position files, the board, the DRC
  reports) still goes to `build/`.
- The repo path is hard-coded in the server (there is no user-supplied path), so
  the write endpoint cannot be pointed elsewhere; it only ever touches
  `hardware/layout_poc/params.json`.
- Two stores remain, by design: the tuning (repo file, shared) and view state
  (localStorage, per browser: toggles, the seed you were on, the save name).
- Until point 5 lands, a UI tuning and a `make layout` run can disagree. The file
  is the human's intent; the engine's env defaults are still what CI uses.
