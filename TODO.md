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
- data extraction and re-integration is python right now. how to integrate?
    (Added from_board.py + make place-seed, which snapshots the board to placements/main.json; server.mjs now defaults to it. Workflow: make place → tune → Save (placement JSON) → Apply to board + DRC (build/layout/board.kicad_pcb).
 
- A/B testing: on model change, run all metrics, record update in progress.md