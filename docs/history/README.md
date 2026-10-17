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
