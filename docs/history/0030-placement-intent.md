# 0030 – the host-pair metric still guessed, so four VIN_SYS caps became "5Q1's"

**What:** the proximity report's host was inferred from net specificity and a
nearest-Q tie-break.  On `VIN_SYS` (14 members, 20 A) every candidate ties, so
`5C1`, `3C2`, `3C3` and `6C3` — four capacitors with four different jobs — were
all reported against `5Q1`.  `6C3` is **12.1 mm** from `6U3`, its actual 3.3 V
buck input pin, but was reported as **25.6 / 6 mm** from `5Q1` because the
rail-bypass rule excluded `U` hosts.  `3C3` at 18.8 mm looked "over" a 15 mm
target that did not describe its loop.

**What changed:** [ADR-0016](../decisions/0016-placement-intent.md).  Every
footprint now has a role and explicit limits in
`hardware/placement_spec.py`: host, `min_mm`/`max_mm`, measure (`pad`, `edge`,
`board_edge`), reason and requirement.  The report (`make proximity`) measures
those limits; the UI graph carries the same data.  The four caps now read:
`5C1` → input ceramic at `5Q1`/`5U1` (3 mm), `3C2`/`3C3` → converter-input
hold-up (`5U1` 15 mm, `5Q1` 10 mm, ≥ 4 mm off the heat), `6C3` → `6U3` (3 mm).

**Numbers (current hand placement, spec v1):** 124 parts, 236 limits, 195 rule
groups; 1 too close, 101 too far.  Worst reach `5C3 → 5Q4` 36.8 mm (bootstrap
loop, limit 3).  Only `3C2/3C3 vs 5Q1` is too close at 3.2 mm (limit 4).  The
old report's 45 critical pairs / 39 over understated this because its 6/15 mm
bins could not express a 3 mm pin loop or a 20 mm AFE keep-away.

**Status:** the baseline is now a design contract, not a placement score.
Re-placement against the spec is the next step; the report is the backlog.
