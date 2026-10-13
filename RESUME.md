# RESUME — TinyUPS

**Start here in a fresh session.** This is a handoff: what's done, what's left, and exactly how to continue.

## Status at a glance

| Area | State |
| --- | --- |
| Schematic | ✅ generated, **ERC-clean** (127 symbols, 115 nets) |
| Placement | ✅ block-aware + decap-aware, board 145×138 mm (fits ATX bay) |
| Routing | ✅ routed (freerouting); **does not yet meet standard 5 mil** |
| DRC (advanced rules) | ✅ **0 / 0** after the manual pass (see below) |
| DRC (**standard 5 mil**) | ⚠️ **524** (446 clearance + 78 width) — the new target |
| Power / ampacity | ❌ **10/10 power nets FAIL** (`make power`) — see "Discovery" |
| Fabrication | not exported yet |
| Bench / DVT | not started (test plan exists) |

## Discovery this session (the important part)

1. **The power path is routed as signal-width hairlines.** `+12V_IN` from the
   XT60 to the 25 A fuse is a single **0.127 mm trace on In2.Cu**; `VIN_SYS`
   (20 A) is **0.095 mm**. Every power net is 0.095–0.127 mm and there is **no
   power pour anywhere**. `power_report.py` sizes each net against its design
   current (IPC-2221): **10/10 FAIL, worst ≈ 46× short** (e.g. a 0.127 mm inner
   trace carries ~0.27 A).
2. **Nothing caught it.** DRC has no ampacity rule, and `routing_report.py`
   only compares against the *fab minimum width* — so it reported "advanced
   PASS" while the power path was fatally undersized. DRC-clean ≠ buildable.
3. **The In1 GND plane is fragmented** into 5 disjoint islands (224 signal
   tracks were routed on In1). The earlier "GND stubs" were really fragment
   gaps and were bridged by hand.
4. **freerouting is not deterministic run-to-run** — a fresh `route.py` from
   the same placement gives a different board. Do not assume a rebuild
   reproduces the accepted board.
5. **F1 is a `Fuse_1206_3216Metric`** (3.2×1.6 mm) labelled "25 A" — a 1206
   fuse physically cannot be 25 A. BOM already flags the value "(verify)".
6. **Fab tier:** the board had been accepted at JLCPCB **advanced** 3.5 mil to
   escape the 0.4 mm-pitch QFNs. We are going back to **standard 5 mil**.

## Decisions taken this session

- **Fab tier → standard 5 mil by default** (NFR-9): min trace/clearance
  **0.127 mm**; advanced 3.5 mil only for a documented geometry that cannot
  meet 5 mil. Enforced now in `.kicad_dru`, the project rules and `gen_pcb.py`.
- **Add a power gate:** `hardware/power_report.py`, wired as `make power` and
  into `make check`.
- **Power-path-first strategy** (see below) — captured as **ADR-0008**
  (proposed).

## The plan (power-path-first layout)

**Strategy:**

1. **Stackup / layer roles — GND on In1.** Keep the **GND plane adjacent to
   the power layer** so the switching converters' hot loops close tightly:
   **F.Cu = power pour (+ signals routed around it) / In1.Cu = GND /
   In2.Cu = signal / B.Cu = signal (+ GND pour)**. Power sits on the top outer
   layer for a direct pad connection (no via bottlenecks) and 1 oz copper.
   (Earlier instinct was F power / B GND / In1+In2 signal — that works but puts
   the power return two layers away and leaves In1 signals without a GND
   reference, so it was dropped.)
2. **Connectors first, fixed:** XT60 input back/centre; XT30 output front/centre;
   USB front, left of XT30.
3. **Power path straight back→front** through A (fuse/TVS/LM5069/sense) →
   priority path → output converter, as a **wide pour**, branching right twice
   (back half → charger; front half → pack/BMS output).
4. **Then the rest** placed around it; RP2040 on the left; signals routed on the
   remaining copper (top layer + inner layers), hopping under the power path
   where needed.

**How this maps onto the tooling:**

| Strategy | Tooling change |
| --- | --- |
| Layer roles / stackup | `gen_pcb.py`: define stackup once; `route.py`: mark power/plane layers in the exported DSN so freerouting confines signals elsewhere |
| Connectors first, fixed spots | `gen_pcb.py`: replace shelf-packing with an **anchored floorplan** (connector anchors); `place_metrics.py`: floorplan-conformance checks |
| Power path straight + branches | `gen_pcb.py`: a **power corridor** + spine order (A → priority → D) and a `pour(net, layer, polygon)` helper; `Power` net class |
| Signals around the path | `route.py` (signals only; power is pours); `routing_report.py` (unrouted); DRC (standard rules) |
| Don't regress | `make power` (done), per-net widths in `routing_report.py`, floorplan checks in `place_metrics.py` |

**Staged:**

1. **Floorplan only** — encode anchors + corridor in `gen_pcb.py`, keep the
   current stackup, re-measure. Isolates the floorplan effect.
2. **Stackup + pours** — GND adjacent to power, power pours, net classes, DSN
   layer roles; re-route; read DRC / routing / power.
3. **MCU + signals** — RP2040 left; confirm the remaining layers carry all
   signals; iterate.

## Open questions

- **Topology:** does the charger branch and the pack branch tap the same rail
  node, or different points on the spine? (ADR-0002: input → protection →
  {priority path, charger}; pack → priority path → converter.)
- **Fuse:** pick a footprint that can actually carry the rated current.
- **QFN fanout at 5 mil:** radial escapes (perpendicular, outward) are the way;
  the earlier *scripted* radial attempt failed at package corners — needs
  careful per-side geometry or via-in-pad.

## Metrics (current — regenerate with the scripts)

```
placement: total HPWL 4978 mm · weighted 12274 mm · power 1459 mm · decap 21.2 mm
routing:   1339 tracks · 290 vias · min trace 0.095 mm
           standard 0.127 -> FAIL (78) | advanced 0.09 -> PASS
           unconnected 0 · nets 115 (inter-block 8, internal 107)
power:     10/10 nets FAIL  (worst ~46x short)
gates:     ERC 0 · test 6/6 · DRC 524 under standard rules (0/0 under advanced)
```

Reproduce: `make erc`, `make drc`, `make power`,
`/opt/eda/venv/bin/python hardware/{place_metrics,routing_report,power_report}.py`.

## Rebuild flow

```sh
make netlist && make bom
/opt/eda/venv/bin/python hardware/gen_schematic.py
/opt/eda/venv/bin/python hardware/gen_pcb.py
/opt/eda/venv/bin/python hardware/fill_zones.py
FREEROUTING_JAR=/opt/freerouting/freerouting.jar \
    /opt/eda/venv/bin/python hardware/route.py
/opt/eda/venv/bin/python hardware/set_sheet.py
```

⚠️ Re-running `gen_pcb.py`/`route.py` **wipes** the manual DRC fixes currently
in `hardware/tinyups.kicad_pcb` (3 GND-fragment bridges + the `ILIM_HIZ` route
+ the deleted dangling via) and the plane fragmentation returns.

## How to open KiCad (GUI)

The container's **desktop-lite is already running** (TigerVNC on `:1`, noVNC on
**6080**) — no rebuild needed:

1. VS Code → **Ports** → **6080** → *Open in Browser* (or `http://localhost:6080`).
   **No password** (VNC runs with `-SecurityTypes None`).
2. From your container terminal (`DISPLAY=:1` is already set):
   ```sh
   pcbnew /workspaces/tinyups/hardware/tinyups.kicad_pcb
   ```

## Toolchain (all in the dev container)

`kicad-cli` 9.0.8 · KiBot 1.9.1 · KiUtils · ngspice 45.2 · `pypdf` · Java +
**freerouting** (`/opt/freerouting/freerouting.jar`, env `FREEROUTING_JAR`) ·
pytest · sigrok-cli. Python venv: `/opt/eda/venv` (on `PATH`).
`kicad-cli` needs `KICAD9_FOOTPRINT_DIR=/usr/share/kicad/footprints` (set in the
Makefile + Dockerfile) or DRC emits ~120 bogus `lib_footprint_issues`.

## Gotchas learned

- KiCad has **no autorouter**; `kicad-cli` can't build a PCB from a netlist —
  use `pcbnew` Python + freerouting (Specctra DSN/SES).
- freerouting runs headless only with `{ "gui": { "enabled": false } }` in
  `freerouting.json`; it is **non-deterministic run-to-run**.
- The board must sit **inside the sheet border** (`set_sheet.py`).
- `ZONE_FILLER` on a freshly-built in-memory board segfaults — fill from a
  loaded board (`fill_zones.py`).
- A plane **pour with signals routed through it fragments** it; bridge the
  islands or keep the pour clear.
- **DRC cannot see current.** Always run `make power`.
