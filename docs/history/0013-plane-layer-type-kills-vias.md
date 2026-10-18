# 0013 – Declaring the plane layer (type power) silently disables vias

**What:** to stop freerouting routing signals through the GND plane
([0012](0012-gnd-return-does-not-carry-20a.md)), `route.py` rewrote the Specctra
layer type of every board-sized zone's layer from `(type signal)` to
`(type power)`. It worked — **0 tracks on `In1.Cu`** (was 177) — and broke
everything else:

| | before | with `(type power)` |
| --- | --- | --- |
| tracks on `In1.Cu` | 177 | **0** |
| **vias** | 237 | **0** |
| tracks on `In2.Cu` / `B.Cu` | 192 / 7 | 4 / 0 |
| tracks on `F.Cu` | 891 | 835 |
| unconnected | 15 | **97** |

**Why:** KiCad exports exactly one via padstack, the through via
`(via "Via[0-3]_600:300_um")`, whose padstack lists all four layers. Freerouting
builds its via rules from the *signal* layers (`LayerStructure.isSignal`,
`containsPlane`, `signalLayerCount`), and a through via that spans a `power`
layer is not usable — so the board came back with no vias at all and everything
that needed a layer change simply stayed unrouted. The router had one layer
(F.Cu) to work with, and 97 connections did not fit.

**Status:** dead end as written. Three mechanisms measured, all with the same
failure mode, and the isolated diff proves the cause is the keepout line and
nothing else:

| mechanism | tracks on `In1.Cu` | vias | unconnected |
| --- | --- | --- | --- |
| none | 177 | 237 | 15 |
| layer type `(type power)` | **0** | **0** | 97 |
| `--router.plane_as_obstacle=true` | **0** | **0** | 100 |
| `(wire_keepout …)` = the rule area | **0** | **0** | **106** |

`diff` of the two DSN structure sections, no-keepout vs keepout, is one line.

**What would make it work:** the guard and the via model are fighting over the
same layer. Freerouting applies a keepout to every object on the layer, and the
only via padstack KiCad emits is a through via spanning all four layers, so
forbidding `In1.Cu` forbids all layer changes — the board collapses to one
routing layer. Two ways out:

1. **Give the DSN a via padstack that skips the plane** — shapes on
   `F.Cu`/`In2.Cu`/`B.Cu`, none on `In1.Cu`. That is what a signal via physically
   is (a through hole with an antipad at the plane), so it is honest; it needs
   the net classes to reference it, and the plane net to keep a via that does
   reach `In1.Cu`.
2. **Scope the guard to a corridor** — protect only where the return needs
   continuous copper, and let the router cut the plane elsewhere. Cheaper, and
   arguably the honest answer, because the 20 A return is carried on the outer
   layer anyway (9.4 mm of 2 oz, of which the plane's 9.38 mm cut contributes
   ~2.4 mm) — so the plane is a contributor, not the path.

Until one of those lands, `gen_pcb.py` leaves the rule area **off**, and the
plane's health is *measured* rather than forbidden: `power_report.py` sizes the
return's min cut (`pour_width`), so a route that cuts the plane too far fails
the gate instead of shipping.

**And a correction to the first reading of this:** KiCad *does* export rule areas
to Specctra — as **`(wire_keepout "" (polygon In1.Cu …))`**, right in the
structure section:

```
    (plane /GND (polygon In1.Cu 0  500 -500 …))
    (wire_keepout "" (polygon In1.Cu 0  500 -500 …))
    (via "Via[0-3]_600:300_um")
```

The first pass over the DSN grepped for `(keepout`, which `(wire_keepout` does
not match, so the guard looked invisible to the router when it was there all
along. Lesson: grep for the *substring*, not the form you expect.

So the whole guard is native: the rule area in `gen_pcb.py` → `wire_keepout` in
the DSN → the router is told, *and* DRC enforces it. `plane_as_obstacle` and the
layer-type rewrite were both unnecessary.

**Where the fix actually is:** nothing in `route.py`. The rule area is the
mechanism; `route.py` only needs to *not* break the vias (i.e. leave the layer
type and `plane_as_obstacle` alone). Whether the remaining 0-via runs were
caused by `plane_as_obstacle` or by the wire keepout itself is what the next run
settles — if a wire keepout also blocks the through via, the fallback is a via
padstack whose layers skip the plane (physically a through via with an antipad,
which is what a signal via is anyway).

**Lesson worth keeping:** a setting that fixes the thing you are looking at by
zeroing it is not a fix. The via count was in the same report and it took a
`routing_report.py` line to notice.
