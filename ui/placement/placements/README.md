# Saved placements

Every **Save** in the interactive placement UI (`make place`) writes one file
here: `<name>.json` — the position of every part, the pins you set, the seed it
started from, and the tuning (`params`) it ran with. The shape is the engine
output's, so `render.py`, `apply.py`, `place-render` and `place-apply` accept it
directly, and the UI lists it in the *start from* drop-down, marked `saved`.

`main.json` is not a hand save: it is a snapshot of the tracked board
(`make place-seed`, `from_board.py`) and the UI's default start, so a session
begins from exactly what `hardware/tinyups.kicad_pcb` is now.

- **Tracked on purpose.** This is your work product, not generated output, so it
  is reviewable and `git checkout` / `git revert` undoes an experiment. See
  [history 0016](../../../docs/history/0016-placement-ui-decisions.md).
- Nothing **generated** lives here: the graph, the engine outputs, the boards and
  the DRC reports are in `build/layout/` (untracked).
- A file here wins over a same-named file in `build/layout/` when loading.
- Files carry no timestamp, so re-saving an unchanged placement is a no-op diff.
- Delete a file when the experiment is done — nothing in the build depends on it.

Load one again with the seed drop-down, or from the command line:

```sh
make place-render   F=ui/placement/placements/main.json
make place-legalize F=ui/placement/placements/main.json   # -> build/layout/leg-main.json
make place-apply    F=build/layout/leg-main.json
```

`place-legalize` is the step in between: a saved placement is advisory
(position-only), and the legaliser is what guarantees 0 courtyard overlaps — but
it **honours the pins** in the file (`anchor` fixes, never relocates; a rotation
that would collide two fixed parts is not applied).
[ADR-0014](../../../docs/decisions/0014-pins-are-authoritative.md)
