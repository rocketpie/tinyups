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

- apply fixed4 new Charger components placement

# UI
- works with json. a board is .kicad_pcb.
- data extraction and re-integration stays python (`extract.py`, `apply.py`,
  `route_feedback.py`); the UI reads `graph.json` + `route-feedback.json` and
  posts saved placements. Workflow: `make place` → tune → Save → Apply to board
  + DRC (writes `build/layout/board.kicad_pcb` and `route-feedback.json`).
- Route feedback is in the panel/overlay: unrouted connections, clearance
  violations, measured power-channel shortfall. Next: launch `make route` as an
  async job from the UI and refresh the same feedback when it lands.
- A/B testing: on model change, run all metrics, record update in progress.md

