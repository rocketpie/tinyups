# 0004 – Anchored terminals snapped back to the hand floorplan on every load

**What:** The interactive UI forced `1J1`/`5J2` to the graph's `anchor` position
whenever a seed was loaded, discarding the position saved in the file. A
placement that put the XT60 at (35.5, 5.0) and the XT30 at (125.5, 132.1) —
`placements/try3.json`, the diagonal input→output arrangement the whole layout
was built around — came back with both at `x = 75`, mid-board, every time.

**Why:** `anchor` is not a mechanical requirement of the *board*: it is the
**hand floorplan's** connector position, taken from `gen_pcb.py`'s

```python
ANCHORS = {"J1": (BOARD_W / 2, 11.0),   # XT60 input  — back centre
           "J2": (BOARD_W / 2, BOARD_H - 11.0), …}
```

and exported by `extract.py` (`anchors = {label(k): v … if k in PINNED}`). The UI
read it as "the terminals are *here*" instead of "the terminals are *pinned*",
and `loadSeed()` overwrote the file's coordinates with it.

**Consequences found while measuring:** because the override moves the two
biggest connectors mid-board, the UI also reported **5 courtyard overlaps that do
not exist** in the file — `1J1↔1R3`, `1J1↔1R5`, `5J2↔6D4`, `5J2↔6R1`,
`5J2↔6R7`. `render.py` (and any DRC on the saved board) uses the file's
positions and reported **0**. So the picture and the PNG disagreed, and the
overlaps one saw were an artefact of the load path.

**Status:** fixed. An anchor now means *pinned*; the seed says where, and the
graph anchor is only the fallback for a seed that has no position for that part
(which is what engine outputs are: they already contain the anchored
coordinates). `resetToSeed()` follows the same rule. Dragging a terminal still
works and is still saved — a terminal must always stay fixed, so `unpin()`
refuses to release an anchor.

**Note for the board, not the tool:** whether the XT60 *should* move is a
mechanical question (enclosure cutouts) that the tool does not decide. The
anchors in `gen_pcb.py` are the hand floorplan's answer; a graph-derived
placement is allowed to disagree, which is the whole point of placing it
interactively.
