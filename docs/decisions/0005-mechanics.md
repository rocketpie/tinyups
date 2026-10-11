# 0005 – Mechanical form factor and pack construction

- Status: accepted

## Context

The whole module — pack plus PCB plus connectors — must occupy the space where
an ATX PSU would normally sit, so it is a self-contained drop-in for the PSU
bay rather than a board plus an external battery.

## Decision

- Fit a **standard ATX bay: 150 × 86 × 140 mm**. The cells are Topband
  33138-HE, **33 × 140 mm** each; a 2×2 arrangement measures ~66 × 66 × 140 mm.
  Because the cell length equals the bay depth, orient the cells with their
  long axis along the **150 mm** dimension — a single row of 4 is
  140 × 132 × 33 mm — leaving clearance for terminals, insulation and the PCB.
- **4-layer PCB.**
- **Spot-welded 4S1P pack with a lead harness** to board terminals (rather than
  holders + bolted busbars).
- **XT60 input** on the panel and a **fixed 12 V output pigtail** (≈14 AWG) to
  the picoPSU, both rated for the ~13–15 A continuous current.
- **Fanless**: heat is spread into the PCB and enclosure.
- **LEDs** (mains / battery / charge / fault) and a **reset button** are
  accessible; everything else is reported over USB.

## Consequences

- The host keeps its existing picoPSU on the ATX header; only the 12 V feed
  comes from the UPS, which lives in the former PSU bay.
- Welded pack + harness is compact but not field-serviceable at cell level.
- Thermal design must remove the buck-boost/charger losses without forced air.
- Related requirements: FR-13, NFR-3, NFR-4, NFR-7, NFR-9, NFR-10, IF-5.
