# docs 
- clean up progress.md from comments. data only

# Placement, Routes and Power
- placement affects routing, routing comes after placement and takes time. 
    route problems need to be fixed in placement, but placement does not see routes.
    
    can we make the placement UI inform us about route results?
    eg. Power traces need more space. can we simulate them live in the placement UI?
    I want that feedback loop shorter

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