# 0013 – Declaring the plane layer (type power) silently disables vias

**What:** to keep freerouting off the GND plane
([0012](0012-gnd-return-does-not-carry-20a.md)), `route.py` rewrote the Specctra
layer type of the plane layer to `(type power)`. It worked — 0 tracks on
`In1.Cu` (was 177) — and broke everything else:

| | before | `(type power)` |
| --- | --- | --- |
| tracks on `In1.Cu` | 177 | **0** |
| **vias** | 237 | **0** |
| unconnected | 15 | **97** |

**Why:** KiCad exports exactly one via padstack — the through via `Via[0-3]`,
spanning all four layers. Freerouting builds its via rules from the *signal*
layers, so a through via that spans a `power` layer is unusable: no vias, so no
layer changes, so 97 connections cannot fit on `F.Cu`.

**Three mechanisms, same failure — none is a fix:**

| mechanism | tracks on `In1.Cu` | vias | unconnected |
| --- | --- | --- | --- |
| none | 177 | 237 | 15 |
| layer type `(type power)` | 0 | 0 | 97 |
| `plane_as_obstacle=true` | 0 | 0 | 100 |
| `(wire_keepout …)` (the rule area) | 0 | 0 | 106 |

**Correction:** KiCad *does* export rule areas to Specctra, as
`(wire_keepout "" (polygon In1.Cu …))`. A first grep for `(keepout` missed it, so
the guard looked invisible when it was there all along.

**Where the fix is:** not in `route.py` — it must leave the layer type and
`plane_as_obstacle` alone. Any guard needs a via padstack that skips the plane (a
through via with an antipad), or must be scoped to a corridor. Until then the
plane is *measured* (`power_report.py`'s min cut), not forbidden.

**Lesson:** a setting that "fixes" the thing you are looking at by zeroing it is
not a fix — the via count was in the same report.
