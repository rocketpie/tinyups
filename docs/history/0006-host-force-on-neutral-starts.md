# 0006 – The belongs-to ring on a neutral start: HPWL/wire down, flow order pays

**What:** the (now archived) A/B runner on neutral scatter starts, 3 seeds from
20260101, base tuning, on the belongs-to force
([0016](0016-placement-ui-decisions.md)) — which in the hand placement `try3` had
improved *every* metric:

| config | HPWL mm | wire mm | ovl | off | path mm | axisR | 5U1 d/bias | 6U1 d | 4U1 d |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| host off | 4325 (4134–4444) | 4943 | 0 | 1 | **645** | **0.76** | 34.0/−0.14 | 30.3 | 29.5 |
| host on, all passives | 4274 (4133–4354) | 4758 | 0 | 0 | 658 | **0.33** | 24.0/0.35 | 24.8 | 17.7 |
| host on, non-power passives | **4158 (3871–4345)** | **4450** | 0 | 0 | 817 | 0.61 | 23.8/0.14 | 20.4 | 19.1 |

**Why:** the fan works everywhere (a controller's small parts come 6–10 mm
closer, HPWL and drawn wire follow them down). The cost shows up only where the
**power chain runs through the part**: a sense resistor or snubber that gets
yanked onto a ring around its IC bends the input→output power path, which is what
`axisR` measures (0.76 → 0.33 when every small passive is ringed) and what the
power-path length partly measures. Restricting the ring to passives that are not
on the power path keeps most of the fan (5U1 34.0 → 23.8 mm) and recovers most of
the flow order (0.61), at the price of a longer power path (645 → 817 mm).

**Status:** `HOST_POWER` (= "ring power-flagged passives too") defaults to
**off**; it is a knob, not a verdict. Two caveats from the same table:

- the HPWL ranges **overlap** across configs (3871–4345 vs 4134–4444), so 3 seeds
  cannot establish the HPWL difference — `wire`, the fan distances and `axisR`
  separate cleanly, HPWL does not;
- **none of this is a routing result.** Per the RESUME plan the yardstick is
  routed wirelength, vias and DRVs on a real board (`route.py` +
  `routing_report.py`); pre-route HPWL and `axisR` are proxies that have already
  been wrong once.

Re-run with:

```sh
make ab AB='--runs 5 --config "off:HOST_STR=0" \
  --config "all:HOST_STR=1.5,HOST_D=5,HOST_POWER=1" \
  --config "non-power:HOST_STR=1.5,HOST_D=5"'
```
