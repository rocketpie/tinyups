# docs 
- clean up progress.md from comments. data only

# Placement, Routes and Power
- placement affects routing, routing comes after placement and takes time. 
    route problems need to be fixed in placement, but placement does not see routes.
    
    can we make the placement UI inform us about route results?
    eg. Power traces need more space. can we simulate them live in the placement UI?
    I want that feedback loop shorter

- 2R1 2U1 pour: "Connect VBUS to the intended feed (VIN_SYS or the ORing element) in the schematic before the next route."
- N_PACKMID: connected, but not wide enough
  N_PACKMID carries 17 A → 7.5 mm of 2 oz copper.
  The two facing source pads are 1.45 mm apart → ~5–6 A of copper.
  A 0.127 mm trace connects them electrically, but not at 17 A.
  Moving them ~6 mm apart opens room for a 7.5 mm pour. A wide copper bar/via on another layer could also do it, but the F.Cu channel is what the placement gate measures.
  
  the terminals sit right opposite each other, how would spacing them make the power transfer any better?


- Where should the caps sit?  **Resolved** — design intent, not a guess:
  `docs/placement.md` + `hardware/placement_spec.py`. `5C1` is the output
  stage's 3 mm input ceramic (`5Q1`/`5U1`); `3C2`/`3C3` are converter-input
  hold-up (`5U1` 15 mm, `5Q1` 10 mm, ≥ 4 mm off the heat); `6C3` is the 3.3 V
  buck's input bypass at `6U3` (3 mm). `make proximity` is the backlog:
  102 violations on `fixed5`; the gate loops (`5Qx→5U1` 24–38 mm, limit 5) and
  the BMS gates (`4Qx→4U1` ~40 mm, limit 10) come first.

  Current hand placement, measured against the new spec:

    195 rule groups
    1 too close — 3C2/3C3 vs 5Q1, 3.2 mm (limit 4)
    101 too far
    worst: 5C3 → 5Q4 36.8 mm (bootstrap loop, limit 3)
    next obvious: 5Q4 → 5U1 37.8, 4Q1/4Q2 → 4U1 ~41/39, 5C2 → 5Q1 28.2, 6C4 → 6U3 41.6



# UI
- add proximity metric display 
- works with json. a board is .kicad_pcb.
- data extraction and re-integration stays python (`extract.py`, `apply.py`,
  `route_feedback.py`); the UI reads `graph.json` + `route-feedback.json` and
  posts saved placements. Workflow: `make place` → tune → Save → Apply to board
  + DRC (writes `build/layout/board.kicad_pcb` and `route-feedback.json`).
- Route feedback is in the panel/overlay: unrouted connections, clearance
  violations, measured power-channel shortfall. Next: launch `make route` as an
  async job from the UI and refresh the same feedback when it lands.
- A/B testing: on model change, run all metrics, record update in progress.md

