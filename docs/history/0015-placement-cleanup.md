# 0015 — placement cleanup: `try5` adopted, the PoC archived

**What:** the placement toolchain was reduced to one tool and the adopted board
promoted to the design.

- **Board:** `hardware/tinyups.kicad_pcb` is now the `try5-poured` board (124
  parts, 150 × 140 mm, power pours, unrouted). Its project file was identical to
  the tracked one bar the filename.
- **UI:** the interactive browser UI moved from `hardware/layout_poc/web/` to
  `ui/placement/` and is the only placement tool. The rest of the PoC — the
  graphviz/dagre/ELK/d3 engines, `fitpos`/`compare`/`contact_sheet`/`mermaid`,
  the A/B runner — is archived under
  [`layout_poc/`](layout_poc/).
- **Removed:** `gen_schematic.py`, `gen_pcb.py`, `set_sheet.py`,
  `place_metrics.py`, and the `layout` / `mermaid` / `baseline` / `ab` Makefile
  targets. `blocks.py`, `power_map.py` and `power_spec.py` survive as shared
  design libraries (`routing_report.py`, `power_silk.py`, `extract.py` use them).

**Why:** Simplyfy. The engine comparison was finished — `try5` (hand-tuned in the UI) is
the board, and the open problems (pour clearance, routing) are not solved by
another global placer. Keeping the engine zoo meant a maintenance surface and a
second source of truth for placement.

**Status / workflow:** the placement route is now one step — `make place` starts
the UI from `placements/main.json`, a snapshot of the board taken with
`make place-seed`; tune the force simulation, save, and apply to
`build/layout/board.kicad_pcb`; everything after is `erc` / `drc` / `render` /
`route` / `sim`. `make erc` is clean and the board is courtyard/edge-clean;
power/ampacity is still the open blocker.

The archived folder is read-only history; its README and the ADRs it links to
describe the PoC as it was, not the current flow.
