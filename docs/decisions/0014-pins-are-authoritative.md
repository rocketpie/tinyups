# 0014 – A pin is authoritative in the legaliser

- Status: accepted

## Decision

A positions file fixes a part three ways: `anchor` (a terminal — always fixed),
`pin: true` (this file fixed it, by hand or by an engine), or neither (free).

1. **`anchor` fixes a part, it never relocates one.** The source file says where
   the part is; engine outputs already carry the anchored coordinates, so this
   only stops the legaliser from dragging an interactive placement's terminals
   back to the hand floorplan
   ([history 0004](../history/0004-anchored-terminals-snap-back-on-load.md)).
2. **A rotation is a proposal, not an order.** The rotation step still picks the
   0/90/180/270 orientation that points a part's pads at its nets' centroids, but
   a rotation that would make **two fixed parts collide** is not applied — the
   seed angle is kept instead. The hard pass cannot undo it (it does not move
   fixed parts).
3. **A collision the human pinned is reported, not hidden.** If two fixed parts
   already overlap at their seed angles, `legalize.py` says so and moves on.

## Consequences

- `legalize.py` is now incapable of producing an overlap between two fixed parts;
  the residual overlaps on the hand placement `try5` are gone and the hand-placed
  terminals survive.
- All engine baselines reproduce `build/layout/leg-*.json` **byte for byte** —
  the rule only bites when a placement has pins, which is the case it exists for.
- Rotation is still *after* placement and still applies to every unpinned part.
- Related requirements: FR-1, FR-3 (placement quality), NFR-1, NFR-9.
