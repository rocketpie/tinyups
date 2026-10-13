# RESUME — TinyUPS

**Start here in a fresh session.** 
This is a handoff: what's done, what's left, and exactly how to continue.


**Where we are**
I'm taking a look around - and i'm obviously not an expert - so help me out here: is +12V_IN connected to a 25A fuse via In2.Cu?
that looks like a hairline trace

Yes. I traced it — and you're right to flag it: it's a 5 mil hairline carrying the full input current. Here's the exact path:

J1 (XT60 solder-wire, PTH)  pad 1  (35.265, 31.298)
   → In2.Cu  0.127 mm   (40.383,31.298) → (52.815,43.73)
   → via (52.815,43.73)
   → F.Cu    0.127 mm   → F1 pad 1 (53.81, 44.725)     [the 25 A fuse]

Every segment is 0.127 mm (5 mil), and it's mostly on an inner layer.

Why that's a problem
Ampacity (IPC-2221, 1 oz copper, 10 °C rise):
width 	outer layer 	inner layer
0.127 mm (5 mil) 	~0.54 A 	~0.27 A
0.20 mm 	~0.74 A 	~0.37 A

So that trace is good for well under 1 A, while the input is specified as 12 V / up to ~20 A (requirements.md §, BOM "up to ~20 A (load + charge)"). To carry 20 A at 10 °C rise you'd need roughly 19 mm of 1 oz outer copper (or ~9 mm of 2 oz) 

Every power net is routed as hairline:

/+12V_IN   all 6 tracks 0.127    /VBAT    0.095–0.127
/N_AF      all 12 tracks 0.127   /VOUT12  all 0.127
/VIN_SYS   0.095–0.127           /VSYS    0.095–0.127
/SW1, /SW2, /SW1_OUT, /SW2_OUT   all 0.095–0.127

There is no wide copper anywhere — the only zone on the board is the GND plane on In1. So there are no power pours; the autorouter used the 5 mil minimum for everything.

Why the checks didn't catch it
    DRC has no ampacity rule — it checks clearances/width-minimums, not current.
    routing_report.py only compares against the fab minimum width, so it happily said "advanced PASS".

One more thing 

F1 is a Fuse_1206_3216Metric — a 3.2 × 1.6 mm SMD fuse. A 1206 package physically can't be a 25 A fuse (they're typically ≤5 A). The BOM already flags the value as "(verify)". So the footprint and the rating disagree too.
Where this came from

gen_pcb.py/route.py set the router to the 5 mil minimum and there are no net classes for power

Fixing it is a real design change (needs an ADR + requirement refs), roughly: power net classes with wide widths and/or high-current nets routed as pours/planes stitched with vias (2 oz copper on the outer layers), fix the fuse footprint, and add an ampacity check to the tooling so it can't silently regress.

Want me to start with the tooling piece — a power_report.py (or extend routing_report.py) that computes per-net current capacity vs the requirement, so we can quantify every power net before touching the layout? That also gives us the numbers for the ADR.

# Last prompt
before that, make a change to the fab requirements. we didn't want to go advanced unless required. I think we should try default again and add more tooling. 
before we make a change, run the power report and add it to progress as baseline (failing).

my intuition tells me to make F the 'power path layer' and B GND, leaving In1 and In2 for signalling.
we put the external connectors first. xt60 input center 'top' / back, xt30 and usb 'bottom' / front. usb left, xt30 center.
then we lay the power path, 'straight across the board from back (input) to front (output)' 

important components first: connector, fuse, whatever lm5069 does, then a wide pour down the board to the buck-boost output. branching right twice: once in the back half to the charger, once in the front half to the bms output (or do both connect at the same time?).
then we can put the rp2040 on the left side of the board and run traces to wherever we need through In1 and 2. 

how do we translate this strategy into the tooling?