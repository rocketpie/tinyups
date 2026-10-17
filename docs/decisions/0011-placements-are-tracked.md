# 0011 – Saved placements are tracked artifacts

- Status: proposed
- Amends [ADR-0009](0009-interactive-placement.md) point 6 and
  [ADR-0010](0010-placement-params-source-of-truth.md) point 4 ("only this
  file"), both of which assumed the UI writes exclusively to `build/`.

## Context

ADR-0009 made the UI write **only** into `build/layout/` (untracked): the
board, the DRC reports and the engine outputs are *generated*, and generated
things do not belong in git. Saving an interactive placement was filed under the
same rule — `build/layout/interactive-<name>.json`.

That is wrong for the same reason the tuning was wrong in ADR-0010: the saved
placement is not generated, it is **the human's work product**. It is the result
of an hour of dragging, pinning and eyeballing, and it cannot be recomputed from
anything in the repository. In practice it was invisible: `build/` is in
`.gitignore`, so `git status` never showed it, and a `git checkout` could not
bring it back. A saved placement that git cannot see is a placement nobody can
review, share or recover.

The distinction that matters is **generated vs. authored**:

| artifact | who makes it | tracked |
| --- | --- | --- |
| netlist, graph, engine outputs (`leg-*`/`pos-*`/`raw-*`), board, Gerbers, DRC/ERC reports | a tool, from the schematic + engines | no (`build/`, `reports/`, `gerbers/`) |
| the engine tuning | you, from the Engine panel | yes — `params.json` (ADR-0010) |
| a placement you dragged together | you, from the board | **yes — this ADR** |

## Decision

1. **`hardware/layout_poc/placements/<name>.json`** is where **Save** writes,
   tracked in git, one file per placement (`<name>` is the string in the save
   box). The shape is unchanged (engine-output: `engine`, `seed`, `params`,
   `pinned`, `positions`) so `render.py`, `apply.py`, `place-render` and
   `place-apply` accept it directly.
2. **No timestamp in the file.** `savedAt` is dropped: a tracked artifact whose
   every save rewrites a date is diff noise. Re-saving an unchanged placement is
   now a byte-identical, no-op diff; git commit dates carry the chronology.
3. **The UI lists them.** `/api/seeds` merges the tracked placements with the
   `build/layout/` engine outputs and marks the tracked ones `saved`; a load
   looks in `placements/` first, so a saved file wins over a same-named engine
   output. `/api/apply` accepts a path from either directory and nothing else.
4. **`params` stays in the saved file** (as it already was): a placement records
   the tuning it was made with, so a file is reproducible even if
   `params.json` has moved on since.
5. **Everything generated stays in `build/`,** exactly as ADR-0009 says. This
   ADR moves one *authored* artifact out of it and changes nothing else — the
   board, `gen_pcb.py` and the tracked `.kicad_pcb` are still out of reach of
   the UI.

## Consequences

- A placement you save is reviewable, diffable, shareable and revertable
  (`git checkout hardware/layout_poc/placements/<name>.json`), and it survives a
  wiped `build/`.
- The repository can accumulate experiment files. That is the intended trade:
  delete them (or `git rm` them) when an experiment is done — nothing in the
  build depends on them. `build/layout/` keeps the throwaway churn out of git.
- The write targets are still hard-coded in the server (no user-supplied path),
  so the two write endpoints can only ever touch `params.json` and
  `placements/*.json`.
- Names are sanitised to `[A-Za-z0-9._-]` on both sides and resolved inside the
  fixed directory; a name that would escape it is rejected.
- The interactive `interactive-<name>.json` convention inside `build/layout/`
  is superseded by the directory, but the server still *lists* — and can still
  load — any that are lying around.
