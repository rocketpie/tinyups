# 0014 – A pin is authoritative in the legaliser

- Status: proposed

## Context

A positions file has three ways to say "leave this part where it is":

| field | means |
| --- | --- |
| `anchor` (from the graph) | the part is a **terminal** — it must stay fixed |
| `pin: true` (from the source file) | **this** seed/file fixed the part, by hand or by an engine |
| neither | the solver/legaliser is free to place it |

The interactive UI worked that out in ADR-0009 and
[`docs/history/0004`](../history/0004-anchored-terminals-snap-back-on-load.md):
an anchor means *pinned*, the file says where, and the graph anchor is only the
fallback for a seed that has no position for that part. The legaliser never got
the same memo: it kept forcing anchored parts to the graph anchor and re-derived
the rotation of *every* part.

On the first hand placement to go through it (`placements/try5.json`) that
produced three courtyard overlaps between parts the legaliser is not allowed to
move — a state its own hard pass cannot repair, because it refuses to move a
fixed part ([`docs/history/0007`](../history/0007-legalizer-overruled-pins.md)).

The root question is what a pin *means*. A pin is the strongest statement a
positions file makes about a part; a legaliser that overrules it is not
legalising, it is re-solving. That is defensible for an engine output (where the
pin is the engine's, and `fitpos.py` has already snapped the terminals) and
wrong for a hand placement, where the pin is the work product.

## Decision

1. **`anchor` fixes a part, it never relocates one.** The source file says where
   the part is. Engine outputs already carry the anchored coordinates
   (`fitpos.py` snaps the connectors to the anchor), so dropping the override
   changes nothing for them — it only stops the legaliser from dragging an
   interactive placement's terminals back to the hand floorplan. This is the
   same rule the UI follows (history 0004).
2. **A rotation is a proposal, not an order.** The rotation step still picks the
   0/90/180/270 orientation that points a part's pads at its nets' centroids, but
   a rotation that would make **two fixed parts collide** is not applied — the
   seed angle is kept instead. The hard pass can never undo it (it does not move
   fixed parts), so without this rule the legaliser can emit overlaps it cannot
   fix, and does so precisely where it matters: on a hand placement every part is
   fixed.
3. **A collision the human pinned is reported, not hidden.** If two fixed parts
   already overlap at their seed angles, `legalize.py` says so and moves on.

## Consequences

- `legalize.py` is now incapable of producing an overlap between two fixed
  parts; the 3 residual overlaps on `try5` are gone and the hand-placed terminals
  survive at (35.5, 5.0) / (125.0, 132.0).
- All seven engine baselines reproduce `build/layout/leg-*.json` **byte for
  byte**: the rule only becomes visible on a placement that has pins, which is
  exactly the case it exists for.
- Rotation is still *after* placement and still applies to every part the source
  did not pin — the PoC's gap ("orientation is a separate step") is unchanged.
- Related requirements: FR-1, FR-3 (placement quality), NFR-1 (the board routes
  and is manufacturable), NFR-9 (fab tier); via ADR-0009/0011, which make the
  saved placement the reviewable work product this rule protects.
