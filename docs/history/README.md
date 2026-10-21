# History — findings, fixes, gotchas, reverts

This folder is the **append-only journal** of point-in-time knowledge:

- bugs found and how they were fixed,
- gotchas and traps that cost real time,
- approaches tried and **reverted**,
- one-off measurements that are not a documented capability.

Everything here describes *what happened*, not *how the project is*. It is
allowed and expected to age, to be superseded, and to be wrong in the future.

## What does **not** belong here

| Doc | Holds | Does not hold |
| --- | --- | --- |
| `README.md`, `AGENTS.md` | how to build/run/contribute, invariants | bug stories, status, dates |
| `docs/requirements.md`, `docs/architecture.md` | the design contract | findings, fixes |
| `hardware/**/README.md` | how a component works | "was broken, now fixed" |
| `docs/decisions/*` (ADR) | a decision + its rationale | changelogs; link here instead |
| `RESUME.md` | current session state | long narratives; link here |
| **`docs/history/`** | **all of the above that is time-bound** | — |

## Convention

- One finding per file: `NNNN-<slug>.md` — the same fixed-width counter as the
  ADRs (`0001`, `0002`, …). Take the next free number.
- **No dates in names or filenames** — git holds the chronology.
- Start with a one-line **What / Why / Status**; then the detail, the numbers,
  and the follow-up.
- Link to it from the timeless docs; do not copy the content there.
- **Do not rewrite** a past entry — add a new one that supersedes it.

## Entries

- [0001 – legaliser/renderer rotated in the wrong Y convention](0001-y-down-rotation-bug.md)
- [0002 – d3-force link parameters were inert](0002-d3force-inert-link-params.md)
- [0003 – a live `POST /api/save` silently overwrote a saved placement](0003-save-endpoint-clobbered-a-placement.md)
- [0004 – anchored terminals snapped back to the hand floorplan on every load](0004-anchored-terminals-snap-back-on-load.md)
- [0005 – the netlist cannot hold a small part beside its IC](0005-the-netlist-cannot-hold-satellites.md)
- [0006 – the belongs-to ring on a neutral start: HPWL/wire down, flow order pays](0006-host-force-on-neutral-starts.md)
- [0007 – power pads, not copper, limit the rails](0007-power-pads-limit.md)
- 0008 – the first route: `try5` routes, but only at 3.5 mil
- 0009 – freerouting necks traces below the class width
- 0010 – three footprints have no 3D model in the shipped library
- [0012 – the GND return does not carry 20 A](0012-gnd-return-does-not-carry-20a.md)
- [0013 – declaring the plane layer (type power) silently disables vias](0013-plane-layer-type-kills-vias.md)
- 0014 – a swept corridor is the wrong primitive for a power pour
- [0015 – placement cleanup: `try5` adopted, the PoC archived](0015-placement-cleanup.md)
- [0016 – placement UI: tracked state and the belongs-to force](0016-placement-ui-decisions.md)
- [0017 – DRC rules do not follow a board copy](0017-drc-rules-do-not-follow-a-board-copy.md)
- [0018 – placement UI: route feedback, pad nets](0018-ui-feedback-loop.md)
- [0019 – board fixup: stale parts, power nets](0019-board-fixup.md)
- [0020 – FET drain and source are reversed on the board](0020-fet-pin-mapping.md)
- [0021 – UI: zoom, pin outline, pour overlay](0021-ui-zoom-and-pin-outline.md)
- [0022 – board fixup: power pours, charger input, CELL0](0022-board-fixup.md)
- [0025 – current-sense loops were not gated](0025-sense-gate.md)
- [0026 – pads are copper, not holes](0026-pads-are-copper.md)
- [0027 – power pours take a trunk, not a chain through every pad](0027-pour-taps.md)
- [0028 – a rail bypass belongs to a switch, not to the nearest controller](0028-host-pair-metric.md)
- [0030 – the host-pair metric still guessed, so four VIN_SYS caps became "5Q1's"](0030-placement-intent.md)
- [0029 – power pours are full Voronoi cells](0029-round-pad-ends.md)


