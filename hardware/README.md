# Hardware

The schematic and the board are maintained as KiCad files. There is no
schematic/board generator: the board is placed and tuned by hand in the
interactive [placement UI](../ui/placement/README.md), then checked with the
tools below.

## Files

| File | Role |
| --- | --- |
| `tinyups.kicad_sch` | Schematic (source of truth). |
| `tinyups.kicad_pcb` | Board (source of truth): the adopted `try5` placement. |
| `tinyups.kicad_pro` | KiCad project (netclasses, stackup, rules). |
| `tinyups.kicad_dru` | Custom design rules. |
| `sym-lib-table` | Project symbol table (standard libs + `tinyups`). |
| `libs/tinyups.kicad_sym` | Custom IC symbols (box symbols from the datasheets). |
| `blocks.py`, `power_map.py`, `power_spec.py` | Shared design data: block map, per-part power estimate, per-net current/voltage. |

## Board

`tinyups.kicad_pcb` is the full 124-part design, 150 × 140 mm, 4 layers:

- **Stackup:** `F.Cu` (power pours + signals) / `In1.Cu` = solid GND plane /
  `In2.Cu` = signal / `B.Cu` = signal.
- **Placement:** the `try5` hand-tuned placement (see
  [`ui/placement/placements/try5.json`](../ui/placement/placements/try5.json)).
- **Power:** high-current rails are copper **pours** on `F.Cu`, not signal
  traces (ADR-0008). `hardware/pour_power.py` builds the corridors; the tracked
  board already carries them.
- **Routing:** not routed. `make route` writes the routed board under `build/`
  and never modifies the source board.

## Commands

```sh
make erc        # schematic electrical rule check
make drc        # board DRC (incl. schematic parity)
make render     # 3D PNG render
make svg        # schematic + PCB SVG for review
make route      # FreeRouting + routing/DRC report
make power      # ampacity of the narrowest segment of every power net
make channels   # can each power net be poured at its required width?
make sim        # ngspice simulations in sim/
```

`make place` starts the interactive placement UI (see
[`ui/placement/README.md`](../ui/placement/README.md)).

## Routing

KiCad has no autorouter, so routing uses **freerouting** (Java), driven by
`hardware/route.py`: export Specctra DSN → relax only the trace width to the
JLCPCB standard 5 mil (0.127 mm) floor → route → import the session into the
board → raise any necked trace back to the floor → refill zones → save.

```sh
make route
make route ROUTE_BOARD=build/layout/board.kicad_pcb
```

Two things matter for convergence:

1. **Stackup — signal layers.** Three signal layers + a solid ground is what
   lets it route at 5 mil. A dedicated power plane (VIN_SYS on `In2.Cu`) was
   tried and removed: it cost a signal layer and the router perforated it
   anyway.
2. **Rules.** 5 mil (0.127 mm), JLCPCB standard. The fine-pitch QFN fanout is
   the only place that cannot meet it with plain traces (via-in-pad is the fix);
   `hardware/fanout.py` pre-places a radial escape for those packages.

`make drc` fails until every net is routed (unconnected pads are DRC errors).

## Power

`hardware/power_report.py` finds the **narrowest segment** of every power net
and compares its ampacity (IPC-2221, dT = 10 °C) against the net's design
current from `docs/requirements.md`/`docs/bom.md`. A signal-width trace is not a
power trace.

`hardware/power_channel.py` is the placement-side gate: a pour is ~10 mm of
copper for 20 A on 2 oz, so the placement has to leave that channel between a
net's pads. `make channels` reports it per rail.

```sh
make power
make channels
```

`hardware/routing_report.py` measures the *route*: track/via counts, per-layer
usage, minimum trace width vs the fab rule, completion, and inter-block nets.

## Status

ERC is clean. The board is placed (courtyard-clean) and poured, but **unrouted**
and the power/ampacity gate has not yet been signed off. See
[`RESUME.md`](../RESUME.md) for the current block and
[`docs/history/`](../docs/history/) for the findings behind the power-pour and
fab-tier decisions.
