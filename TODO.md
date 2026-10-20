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


- Where should the caps sit?
The caps are now electrically decoupled from the pour path, so the pours do not require moving them.
    5C1 (10 µF) is the one worth moving first: it is 46.9 mm from 5Q1 and 52.8 mm from 5U1.
    If it is the HF bypass for 5U1’s VIN_SYS pins, it belongs next to those pins. 
    Its graph current is only 0.793 A, so it is a routed trace, not one of the pours.
    
    3C2 / 3C3 (2 × 470 µF hold-up) are currently 21.6 / 21.8 mm from 1Q1, but 49.4 / 59.6 mm from 5Q1 and similarly far from 5U1. 
    For the converter-input hold-up loop they would ideally sit at the 5Q1 drain / 5U1 VIN_SYS node with a short GND return. Because they are bulk electrolytics
    ESR/ESL dominates and this is second-order; 


- Host-pair spacing
  Targets: 6 mm for signal bypass/gate parts, 15 mm for power-path parts (hold-up caps, shunts, inductors).

  Current worst critical pairs on the main board:
  pair 	distance / target 	
  5C1 → 5Q1 	5.8 / 6 mm 	ok
  3C2 → 5Q1 	12.0 / 15 mm 	ok
  3C3 → 5Q1 	18.8 / 15 mm 	over
  6C3 → 5Q1 	25.6 / 6 mm 	over (12.1 mm from 6U3)
  5C9 → 5J2 	18.4 / 15 mm 	over
  5C10 → 6J5 	32.3 / 6 mm 	over
  4R1 → 4U1 	42.5 / 15 mm 	over — the Kelvin problem
  5L1 → 5U1 	45.2 / 15 mm 	over
  2C2 → 2U1 	9.4 / 6 mm 	over

  Overall: 45 critical pairs, 39 over target, mean 13.5 mm. That is the honest state of the hand placement; the report is a screen, not a gate.

  For best performance the rule is therefore:

      rail bypass / hold-up cap → the switch or connector on that rail,
      boot/charge-pump cap → its controller,
      shunt → its sense controller,
      inductor → its switching node/controller.



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

