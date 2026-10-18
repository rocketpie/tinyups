# 0009 – Interactive placement UI (browser, d3-force)

- Status: accepted

## Decision

1. **A browser UI on port 4097** (`make place`, `ui/placement/`), served by a
   dependency-free Node server. It draws the placement graph (courtyards +
   current-coloured net edges) over the board outline.
2. **The engine is d3-force, run in the browser** so it simulates *while* you
   drag. It is the right engine for interaction: incremental, pins parts
   natively (`fx`/`fy`), and its parameters are the physical knobs. Layered
   engines (dagre/ELK/graphviz) are batch and ignore pins.
3. **A dragged part is pinned** (`fx`/`fy`); right-click releases it. The two
   terminals (`1J1`/`5J2`) stay pinned.
4. **All engine parameters are exposed and editable**, with the same key names
   the model uses. d3 caches force accessors, so the UI re-sets them on every
   change to make sliders effective mid-run.
5. **Fix the link model and clamp velocity.** Wire
   `forceLink.distance()/.strength()` as intended and clamp to `MAX_V` (default
   3 mm/tick); without the clamp the wired rest lengths diverge from a dense
   start. This is a behaviour change to the engine, not just the UI.
6. **Source of truth: the board.** The UI starts from a snapshot of
   `hardware/tinyups.kicad_pcb` (`placements/main.json`, `make place-seed`) and,
   on apply, writes only `build/layout/board.kicad_pcb` + DRC. The tracked board
   is never modified by the UI.
7. **Scope: position only.** Rotation comes from the seed; snapping and the full
   legalisation pass are left to `legalize.py`. Overlap is reported live and
   fought by a rectangular collision force, but the tool does not itself
   guarantee DRC legality.

## Consequences

- The placement route exists: board snapshot → drag/tune → save → render/DRC, via
  `make place` and the `place-render` / `place-apply` targets.
- Port 4097 is added to `.devcontainer/devcontainer.json`; a running container
  must be recreated for the published port to take effect.
- Interactive legality is *advisory*: `kicad-cli pcb drc` on the applied board is
  the gate, and `legalize.py` is the piece that guarantees 0 overlaps.
- Requirements: FR-1, FR-3, NFR-1, NFR-9.

> The PoC engines' `d3-force` scores predate the link-model fix
> ([history 0002](../history/0002-d3force-inert-link-params.md)); the engines were
> retired with the PoC ([history 0015](../history/0015-placement-cleanup.md)).
