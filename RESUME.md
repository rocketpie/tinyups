# RESUME — TinyUPS

**Start here in a fresh session.** This is a handoff: what the project is,
what's done, what's left, and exactly how to continue.

## Status at a glance

| Area | State |
| --- | --- |
| Schematic | ✅ generated, **ERC-clean** (127 symbols, 115 nets) |
| Placement | ✅ block-aware + decap-aware, DRC-clean, board 145×138 mm (fits ATX bay) |
| Routing | ✅ routed (freerouting), **JLCPCB advanced tier** (min 0.095 mm) |
| DRC | ⚠️ **1 dangling via + 4 unconnected** (see "Open work") |
| Fabrication | not exported yet |
| Bench / DVT | not started (test plan exists) |

## Key files & how things are generated

Everything is scripted and reproducible — **edit the scripts, not the outputs**.

| Script | Produces |
| --- | --- |
| `hardware/gen_schematic.py` | `hardware/tinyups.kicad_sch` (+ `libs/tinyups.kicad_sym`) |
| `hardware/gen_pcb.py` | `hardware/tinyups.kicad_pcb` (4-layer, placed, GND plane, nets) |
| `hardware/fill_zones.py` | fills the copper zones (planes) |
| `hardware/fanout.py` | *experimental* radial QFN fanout (see progress.md) |
| `hardware/route.py` | full routing flow (export DSN → freerouting → import → refill) |
| `hardware/set_sheet.py` | moves board onto the A4 sheet + title block |
| `hardware/place_metrics.py` | placement metrics (HPWL, decap distance) |
| `hardware/routing_report.py` | routing metrics (widths, vias, fab tier, completion) |

**Rebuild flow:**
```sh
make netlist && make bom            # from the schematic
/opt/eda/venv/bin/python hardware/gen_schematic.py
/opt/eda/venv/bin/python hardware/gen_pcb.py
/opt/eda/venv/bin/python hardware/fill_zones.py
FREEROUTING_JAR=/opt/freerouting/freerouting.jar \
    /opt/eda/venv/bin/python hardware/route.py
/opt/eda/venv/bin/python hardware/set_sheet.py
```

**Checks:**
```sh
make erc        # schematic ERC (0 violations expected)
make drc        # PCB DRC (currently 1 + 4 items, see below)
make test       # pytest toolchain smoke (6/6)
```

## Open work — do this next

### 1. Finish the last 5 DRC items (manual, ~5 min in the KiCad GUI)

`make drc` reports **1 `via_dangling` + 4 `unconnected_items`**:
- **3 GND stubs** (short `/GND` tracks not tied to the In1 ground plane)
- **`ILIM_HIZ`** (U3 pin 6 → R13 pin 1) — the one net freerouting left unrouted
- **1 dangling via** on `/N_COMP2`

In Pcbnew: `Inspect → Design Rules Checker → Run DRC`, then click each entry to
zoom to it:
- **GND stubs:** select the stub, `Place → Via` (or press **V**) at its dangling
  end → a GND via to the In1 plane.
- **`ILIM_HIZ`:** press **X**, click U3 pad 6, route to R13 pad 1 (press **V**
  to hop to B.Cu, which is nearly empty). 
- **dangling via:** select and **Del** (net is otherwise connected).
- Re-run DRC → aim for 0/0, save (**Ctrl+S**).

⚠️ **Caveat:** the PCB is *generated*; re-running `gen_pcb.py`/`route.py` wipes
manual fixes. Record them, or fold them into the scripts (e.g. move `R13`
beside `U3` so freerouting routes `ILIM_HIZ` itself).

### 2. (optional) Get to standard 5 mil
The only sub-5-mil feature is the **QFN fanout** (0.4 mm pitch: RP2040,
BQ25720, LM5176, BQ76942). Options: hand-fanout in the GUI, or HDI. We
**accepted the advanced tier** for now (see `docs/progress.md`).

### 3. Then
- Export fabrication (`make fab`, `make pos`), review gerbers.
- Start the DVT per `docs/test-plan.md`.

## How to open KiCad (GUI)

The dev container now has the **desktop-lite** feature (port 6080):
1. Open **http://localhost:6080** (noVNC). Password: **`vscode`**.
2. In that desktop's terminal:
   ```sh
   export DISPLAY=:1
   pcbnew /tinyups/hardware/tinyups.kicad_pcb
   ```
   (workspace is bind-mounted at `/tinyups`; also `/workspaces/tinyups`)

Or just open the project with KiCad on the host (it's a normal bind mount).

## Metrics (current — regenerate with the scripts)

```
placement: total HPWL 4978 mm · weighted 12274 mm · power 1459 mm · decap 21.2 mm
routing:   1315 tracks · 288 vias · min trace 0.095 mm
           standard 0.127 -> FAIL (78, all QFN fanout) | advanced 0.09 -> PASS
           inter-block 8 nets, internal 107
gates:     ERC 0 · test 6/6 · DRC 1 + 4
```

## Toolchain (all in the dev container)

`kicad-cli` 9.0.8 · KiBot 1.9.1 · KiUtils · ngspice 45.2 · `pypdf` ·
Java + **freerouting** (`/opt/freerouting/freerouting.jar`, env `FREEROUTING_JAR`) ·
pytest · sigrok-cli. Python venv: `/opt/eda/venv` (on `PATH`).
Version detail: `docs/toolchain.md`.

## Gotchas learned

- KiCad has **no autorouter** and `kicad-cli` can't build a PCB from a netlist
  — use `pcbnew` Python + freerouting (Specctra DSN/SES).
- freerouting runs headless only with `{ "gui": { "enabled": false } }` in
  `freerouting.json` (the native `freerouting-cli` build crashed).
- The board must sit **inside the sheet border** (`set_sheet.py`).
- `SW1`/`SW2` were merged between charger and output (caught by metrics) —
  fixed to `SW1_OUT`/`SW2_OUT`.
- A dedicated power plane hurt; `F.Cu / GND / signal / signal` routes at 5 mil.
- `ZONE_FILLER` on a freshly-built in-memory board segfaults — fill from a
  loaded board (`fill_zones.py`).

**where we left off**
> That's a ~5-minute manual pass in the KiCad GUI for someone at the keyboard 
walk me through.
any way i can access kicad in the container?

(desktop-lite add, container restart, here) 
