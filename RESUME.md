# RESUME — TinyUPS

**Start here in a fresh session.**

## Status

| Area | State |
| --- | --- |
| Schematic | ✅ ERC-clean (124 parts, 115 nets), maintained in KiCad |
| Placement | ✅ `fixed5` promoted; DRC 0 courtyard / 0 clearance / 0 short |
| Placement intent | 🟡 spec v1 covers all 124 parts (236 limits); baseline 102 violations — see `docs/placement.md` |
| Routing | 🟡 1-pass route on `build/layout/tinyups-routed.kicad_pcb`: 800 tracks, 159 vias, 47 unconnected, 0 clearance; 77 signal tracks on `In1.Cu` |
| Power / ampacity | 🟡 high-current rails 16/16 PASS, channels 16/16 ok; `N_VCAP` unrouted, `+3V3` 0.9 of 1.0 A |
| Sense (Kelvin) | ❌ 5/5 still `pour/zone`, 0 mm dedicated tracks |
| Test plan / DVT | not started |

Commands: `make place` (UI) · `make drc` · `make render` · `make route` ·
`make sim` · `make power` · `make channels` · `make sense SENSE_BOARD=…`.

`fixed5` is `fixed4` with `4Q1` moved 6 mm off `4Q2`; the power gates now read
pads as copper (they used to read pad centres as holes), so `N_PACKMID` is
8.8 / 7.5 mm and all channels pass — [history 0026](docs/history/0026-pads-are-copper.md).
`make power` passes every high-current rail. The routed board was made with
`FREEROUTING_PASSES=1 make route`; the stall guard kills the router before it
writes a session, and pass 1 is the best board anyway.

## Next steps

1. **Re-place against the spec** — `make proximity` (102 violations on `fixed5`)
   is the backlog. Start with the gate loops (`5Qx → 5U1` 24–38 mm, limit 5) and
   the BMS gates (`4Qx → 4U1` ~40 mm, limit 10); then the input/output cells.
2. **Tap connectivity** — the pours sweep only series pads, and freerouting
   treats a plane net as connected: 10 `VIN_SYS` taps and the `N_ACN` sense pin
   are left unrouted. A zone branch added islands (47 → 53 unconn); pre-route
   the taps as tracks instead.
3. **GND / vias** — 30 dangling vias and 5 GND pads without a via to the `In1`
   plane (`3U1.2`, `3R1.2`, `6C3.2`, `3C2.2`, `6U1.57`). GND stitching/escape
   is the next fanout item.
4. **Sense** — route the five shunt↔controller pairs as dedicated Kelvin tracks
   from the shunt pads. `4R1`↔`4U1` is 51.3 mm: re-place it, then re-route —
   [0025](docs/history/0025-sense-gate.md).
5. **`+3V3`** — the router's 0.127 mm trace carries 0.9 A of the 1 A estimate;
   widen it where the clearance allows, or confirm the current.
6. **`In1.Cu`** — 77 signal tracks cut the GND return. Every guard (layer type,
   `plane_as_obstacle`, wire keepout) kills the via padstack; a proper fix needs
   a through-via with an antipad or a corridor-scoped keepout —
   [0013](docs/history/0013-plane-layer-type-kills-vias.md).
7. `make check` on the main board still fails on the promised unrouted state
   (261 unconnected, 6 low-current nets without copper); the routed board is
   the artifact. Keep `hardware/tinyups.kicad_pcb` unrouted and consistent with
   `build/layout/tinyups-routed.kicad_pcb`.

## Where things came from

The graph-placement PoC (sfdp/dagre/ELK engines, automatic placement) is
concluded and archived in [`docs/history/layout_poc/`](docs/history/layout_poc/).
The current placement was tuned by hand in the UI; the board itself is the
source of truth.
