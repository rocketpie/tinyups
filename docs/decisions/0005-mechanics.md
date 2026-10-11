# 0005 – Mechanical form factor, pack, connectors and cooling

- Status: accepted

## Context

The whole module — pack, PCB, connectors and fan — must occupy the space where
an ATX PSU normally sits, so it is a self-contained drop-in for the PSU bay.
The picoPSU stays on the motherboard and only needs its 12 V feed from this
module. The external 12 V supply comes from outside the case.

## Decision

- **Standard ATX bay: 150 × 86 × 140 mm.**
- **4-layer PCB.**
- **Pack: 4S1P LiFePO₄** (Topband 33138-HE, 33 × 140 mm). Round cells,
  **spot-welded with nickel strips** and a **lead harness** to internal PCB
  terminals (no holders, no external pack connector). Cells are matched and
  rough-balanced before assembly.
- **Input connector:** **XT60** (2-pin, **+12 V / GND**, 60 A peak / ~30 A
  cont.) on the **panel at the ATX AC-inlet location**, on the side with the
  chassis mounting screw holes, so the external supply plugs in from outside.
- **Output connector:** **XT30** (2-pin, 13 A cont.) pigtail, feeding a short
  **XT30 → 5.5 × 2.5 mm barrel-plug** adapter cable into the picoPSU. The
  barrel plug, XT30 and cable are part of the BOM.
- **Cooling:** an **80 mm fan** on the standard mounting pattern, wired to an
  **on-board 4-pin header** (12 V, GND, PWM, tach), temperature-controlled by
  the MCU (FR-16). Ambient inside the server is ~30–35 °C.
- **LEDs** (mains / battery / charge / fault) and a **reset button** are
  accessible; everything else is reported over USB.
- **Chassis grounding:** the picoPSU 12 V input has no dedicated earth return,
  so the module is bonded to the chassis.

## Consequences

- The host keeps its picoPSU on the ATX header; only the 12 V feed comes from
  the UPS, which lives in the former PSU bay.
- Welded pack + harness is compact and low-resistance but not field-serviceable
  at cell level.
- The fan adds a temperature-controlled load on the 12 V rail; on battery it
  must be limited/disabled to protect runtime.
- The XT60 panel connector sets the cutout at the former AC inlet; the output
  XT30 stays inside.
- Related requirements: FR-13, FR-16, NFR-3, NFR-4, NFR-7, NFR-9, NFR-10,
  IF-1, IF-3, IF-5.
