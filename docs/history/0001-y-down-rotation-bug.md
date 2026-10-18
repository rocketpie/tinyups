# 0001 – legaliser/renderer rotated in the wrong Y convention

- **What:** the placement PoC's `legalize.py` and `render.py` rotated component
  offsets using the **math (Y-up)** convention, but a KiCad board is **Y-down**.
- **Why it matters:** the two forms are identical for a symmetric courtyard but
  **mirrored** for an asymmetric one, so a placement that looked legal to our own
  overlap metric overlapped in KiCad.
- **Status:** fixed in `legalize.py` + `render.py`; baseline went from 2
  overlaps + 1 edge violation to **0 + 0** (KiCad DRC).

*(Moved here from the PoC README; the fix itself predates the
interactive-placement work.)*

## The bug

Rotation by `a` in a Y-down frame is
`(x, y) → (x·cos a + y·sin a, −x·sin a + y·cos a)`; the textbook Y-up form is its
inverse. `TO-252-2`'s courtyard sits 0.84 mm off-centre, which is why exactly the
pairs `4Q1↔4Q2` and `2Q3↔2Q4` slipped past our internal courtyard-AABB metric
while KiCad's DRC found them.

## Lesson

**Our internal metrics are not a substitute for running the real DRC.** The
pre-route proxy (HPWL) and our own courtyard bbox check both missed a genuine,
ground-truth violation that `kicad-cli pcb drc` caught immediately.

## References

- [`ui/placement/legalize.py`](../../ui/placement/legalize.py) — `rot()` documents the Y-down form
- [`ui/placement/render.py`](../../ui/placement/render.py) — `rot()` matches it
- [`docs/history/layout_poc/README.md`](layout_poc/README.md) (archived PoC)
