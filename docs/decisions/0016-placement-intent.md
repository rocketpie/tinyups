# 0016 – Placement intent is explicit design data

- Status: accepted

## Decision

1. **A part's function and its placement limits are written down**, not
   inferred from the netlist.  `hardware/placement_spec.py` holds, for every
   footprint on the board, a role and either one or more `Limit`s (host,
   `min_mm`/`max_mm`, measure, reason, requirement) or an explicit entry in
   `FREE`/`ANCHORS` with the reason it has none.
2. **Three measures are defined** and a limit names one: `pad` (copper edge on
   the functional net), `edge` (body/courtyard gap, for thermal/EMI), and
   `board_edge` (body to outline, for connectors).
3. **One consumer, one source.**  `proximity_report.py` measures the board
   against the spec; `ui/placement/extract.py` writes the same limits into
   `graph.json`, and the UI's belongs-to force uses the spec host/ring.  There
   is no netlist-scoring fallback for a current graph.
4. **Coverage is a gate.**  A footprint without a role, a limit for a missing
   part, a host that does not exist, or a part that is neither constrained nor
   declared free fails the report (exit 2).
5. **Targets are families, not per-part inventions**: 3 mm pad for a
   high-di/dt pin loop, 5 mm for a filtered sense/feedback node, 10 mm for a
   bias/divider and for a switching cell or Kelvin shunt, 15 mm for bulk
   hold-up, 4 mm edge for an electrolytic near heat, 10–20 mm edge for an
   analog IC/crystal/USB/harness near a switching inductor, 0.5–3 mm body to
   the outline for a connector.  The full table and the datasheet basis are in
   [`docs/placement.md`](../placement.md).

## Rationale

A net is connectivity, not function.  On a wide rail such as `VIN_SYS` many
parts tie on every candidate host, so an inferred model cannot distinguish a
converter input ceramic from a 470 µF hold-up or a regulator bypass; it also
cannot express a 3 mm pin loop or a 20 mm analog keep-away, because one global
6/15 mm bin has no room for either.  The design already knows each part's role
and its loop — the missing piece was writing it down.  The defect that exposed
this is in [history 0030](../history/0030-placement-intent.md).

## Consequences

- Placement work starts from a design contract; the report names the violated
  rule and its source (`why`, `src`, `req`).
- A schematic change that adds or removes a part fails `make proximity` until
  the spec is updated — the intended forcing function.
- The spec is a gate on **coverage**, not on the current placement: the hand
  layout was never designed against these limits, so the report is a backlog.
  The baseline numbers are in history 0030.
- The UI metric is an approximation (centroid distance vs a pad/edge limit);
  `make proximity` on the board remains authoritative.
- Requirements: FR-1…FR-16, NFR-1/NFR-3/NFR-11, IF-1…IF-5.  History: 0030
  (the defect), 0028 (the previous inference model).
