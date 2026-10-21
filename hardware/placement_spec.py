#!/usr/bin/env python3
"""Placement intent — design limits, not netlist guesses.

`proximity_report.py` and the placement UI used to infer what a part serves:
a cap that shares only `VIN_SYS` + `GND` with a dozen blocks ties on every
candidate, so the nearest Q/J won and four unrelated capacitors were reported
as "5Q1's caps".  That is not a placement rule, it is an artefact.

This module is the rule.  Every footprint on the board has a **role** (what it
does in the circuit), and every part that has a physical placement requirement
has one or more **limits**: a host it belongs to, a minimum and/or maximum
distance, and the reason.  Parts without a proximity requirement are listed in
`FREE` with the reason — never left implicit.

Measurement
-----------
Three measures are defined; a limit says which one it means:

``pad``
    Shortest copper-edge gap between a pad of the part and a pad of the host
    **on the named net** (GND excluded unless named).  This is the trace length
    that matters for a bypass, filter or gate loop.
``edge``
    Courtyard/body gap between the two parts.  Used for thermal and EMI
    keep-aways, where the package, not the copper, is the source.
``board_edge``
    Gap from the part body to the board outline.  Used for connectors and
    panel indicators.

`min_mm` is a keep-away (too close is the violation); `max_mm` is a reach
(too far is the violation).  A limit may have only one of them.

Basis
-----
Numbers are board-level engineering targets derived from the vendor layout
sections, not invented per part:

* the datasheet says "close"/"as close as possible" → 3 mm pad for a
  high-di/dt loop or a pin bypass, 5 mm for a filtered sense/feedback node,
  10 mm for a bias/divider/pull-up;
* a current-sense shunt to its controller → 10 mm with a dedicated Kelvin pair
  (`sense_report.py` checks the tap itself), per LM5069 §11.1, LM5176 §10.1,
  BQ25720 Table 12-1 rule 7, BQ76942 §18.1;
* a switching cell (FETs + inductor + shunts) → 10 mm, per LM5176 §10.1 and
  BQ25720 Table 12-1 rules 2–6;
* bulk electrolytics → 15 mm from their switching stage (loop inductance) but
  ≥ 4 mm body gap from FETs/inductors (electrolyte life, LM74700-Q1 §12.1);
* an analog IC / crystal / USB / cell harness → ≥ 15–20 mm body gap from the
  300–800 kHz inductors and their FETs (radiated field and thermal);
* connectors and LEDs → body 0.5–5 mm from the board outline (mechanical).

Changing a number here changes both the report and the UI (the graph carries
the limits); there is no second copy of the guess.
"""
from __future__ import annotations

from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# limits
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Limit:
    part: str
    host: str
    measure: str                 # pad | edge | board_edge
    min_mm: float = 0.0
    max_mm: float | None = None
    net: str | None = None       # pad measure: the functional net
    why: str = ""
    src: str = ""                # datasheet / layout section
    req: str = ""                # requirement ID
    primary: bool = False        # the part's functional host (UI ring)


def _one(part: str, host: str, measure: str, min_mm: float = 0.0,
         max_mm: float | None = None, net: str | None = None,
         why: str = "", src: str = "", req: str = "",
         primary: bool = False) -> Limit:
    return Limit(part, host, measure, min_mm, max_mm, net, why, src, req,
                 primary)


LIMITS: list[Limit] = []


def add(parts, host, measure="pad", min_mm=0.0, max_mm=None, net=None,
        why="", src="", req="", primary=False):
    """Add the same limit for each part / host pair."""
    if isinstance(parts, str):
        parts = [parts]
    if isinstance(host, str):
        host = [host]
    for p in parts:
        for h in host:
            LIMITS.append(_one(p, h, measure, min_mm, max_mm, net, why,
                               src, req, primary))


def thermal(parts, host, min_mm, why, src="", req=""):
    add(parts, host, "edge", min_mm=min_mm, why=why, src=src, req=req)


# --------------------------------------------------------------------------- #
# roles — every footprint, one line
# --------------------------------------------------------------------------- #
ROLES: dict[str, str] = {
    # A — input protection / hot-swap (LM5069)
    "1J1": "XT60 input connector, 20 A panel feed",
    "1F1": "25 A ATO input fuse (backup to the eFuse)",
    "1D1": "SMBJ15A input TVS, clamps at the connector",
    "1Q1": "LM5069 hot-swap pass FET",
    "1R1": "2.2 mΩ input current-limit shunt (25 A)",
    "1U1": "LM5069 hot-swap controller",
    "1C1": "TMR timer capacitor",
    "1R2": "UVLO divider, high side",
    "1R3": "UVLO divider, low side",
    "1R4": "OVLO divider, high side",
    "1R5": "OVLO divider, low side",
    "1R6": "PWR power-limit set resistor",
    "1R7": "PGD pull-up to the input rail",

    # B — priority power path (LM74700-Q1)
    "3Q1": "LM74700 ideal-diode FET, pack branch",
    "3U1": "LM74700-Q1 ideal-diode controller",
    "3C1": "VCAP charge-pump capacitor",
    "3R1": "IN_VALID pull-down",
    "3C2": "470 µF VIN_SYS hold-up for the input→pack handover",
    "3C3": "470 µF VIN_SYS hold-up for the input→pack handover",

    # C — charger (BQ25720)
    "2U1": "BQ25720 4-switch buck-boost charger",
    "2Q1": "charger input half-bridge, high side",
    "2Q2": "charger input half-bridge, low side",
    "2Q3": "charger output half-bridge, low side",
    "2Q4": "charger output half-bridge, high side",
    "2L1": "2.2 µH charger inductor",
    "2R1": "5 mΩ RAC charger input shunt",
    "2R2": "5 mΩ RSR battery-current shunt",
    "2C1": "BTST1 bootstrap capacitor",
    "2C2": "BTST2 bootstrap capacitor",
    "2C3": "REGN bypass",
    "2C4": "VDDA bypass",
    "2C5": "COMP1 compensation capacitor",
    "2C6": "COMP2 compensation capacitor",
    "2C7": "PSYS filter capacitor",
    "2C8": "IADPT filter capacitor",
    "2C9": "IBAT filter capacitor",
    "2R3": "CBP divider, high side",
    "2R4": "CBP divider, low side",
    "2R5": "ILIM_HIZ current-limit set resistor",
    "2R6": "I2C SDA pull-up",
    "2R7": "I2C SCL pull-up",
    "2R8": "COMP1 series/filter resistor",
    "2R9": "IADPT series/filter resistor",
    "2R10": "IBAT series/filter resistor",
    "2R11": "CHGOK pull-up",
    "2R12": "PROCHOT pull-up",

    # E — battery AFE (BQ76942)
    "4U1": "BQ76942 battery AFE",
    "4R1": "1 mΩ pack-current shunt (coulomb counter)",
    "4Q1": "pack charge-protection FET",
    "4Q2": "pack discharge-protection FET",
    "4J6": "PACK+/PACK− pack terminal",
    "4J7": "CELL0…CELL4 cell-sense header",
    "4C1": "REG18 bypass",
    "4C2": "REG2 bypass",
    "4C3": "REG1 bypass",
    "4C4": "PACK+ supply bypass",
    "4C5": "CP1 charge-pump capacitor",
    "4C6": "VC0 input filter capacitor",
    "4C7": "VC1 input filter capacitor",
    "4C8": "VC2 input filter capacitor",
    "4C9": "VC3 input filter capacitor",
    "4C10": "VC4 input filter capacitor",
    "4R9": "VC0 cell-input filter resistor",
    "4R10": "VC1 cell-input filter resistor",
    "4R11": "VC2 cell-input filter resistor",
    "4R12": "VC3 cell-input filter resistor",
    "4R13": "VC4 cell-input filter resistor",
    "4R2": "TS1 cell/pack NTC",
    "4R3": "TS2 cell/pack NTC",
    "4R4": "TS3 cell/pack NTC",
    "4R5": "ALERT pull-up",
    "4R6": "RST pull-up",
    "4R7": "CFETOFF pull-up",
    "4R8": "DFETOFF pull-up",

    # D — output converter (LM5176)
    "5U1": "LM5176 4-switch buck-boost output controller",
    "5Q1": "output buck high-side FET",
    "5Q2": "output buck low-side FET",
    "5Q3": "output boost low-side FET",
    "5Q4": "output boost high-side FET",
    "5L1": "1.0 µH output inductor",
    "5R3": "1 mΩ output current-sense shunt",
    "5C1": "10 µF VIN_SYS ceramic bypass at the output stage",
    "5C2": "BOOT1 bootstrap capacitor",
    "5C3": "BOOT2 bootstrap capacitor",
    "5C4": "SS soft-start capacitor",
    "5C5": "COMP compensation capacitor",
    "5C6": "SLOPE slope-compensation capacitor",
    "5C7": "DITH dither capacitor",
    "5C8": "VCC bypass",
    "5C9": "220 µF VOUT12 bulk output capacitor",
    "5C10": "10 µF VOUT12 ceramic output capacitor",
    "5R1": "FB divider, high side",
    "5R2": "FB divider, low side",
    "5R4": "RT 300 kHz frequency-set resistor",
    "5R5": "MODE set resistor",
    "5R6": "COMP zero resistor",
    "5R7": "EN divider, high side",
    "5R8": "EN divider, low side",
    "5R9": "PGOOD pull-up",
    "5J2": "XT30 output connector, 17 A peak",

    # F — control / host link / UI
    "6U1": "RP2040 telemetry and safety MCU",
    "6U2": "W25Q128 QSPI flash",
    "6U3": "3.3 V buck regulator",
    "6Y1": "12 MHz crystal",
    "6C1": "XIN load capacitor",
    "6C2": "XOUT load capacitor",
    "6C3": "10 µF VIN_SYS input bypass at the 3.3 V buck",
    "6C4": "10 µF +3V3 decoupling at the MCU",
    "6C5": "1 µF DVDD bypass",
    "6R1": "RUN pull-up",
    "6R2": "LED1 series resistor",
    "6R3": "LED2 series resistor",
    "6R4": "LED3 series resistor",
    "6R5": "LED4 series resistor",
    "6R6": "USB D− 27 Ω series termination",
    "6R7": "USB D+ 27 Ω series termination",
    "6R8": "fan tach pull-up",
    "6D1": "LED1 status indicator",
    "6D2": "LED2 status indicator",
    "6D3": "LED3 status indicator",
    "6D4": "LED4 status indicator",
    "6J3": "USB-C host link (data only)",
    "6J4": "SWD programming header",
    "6J5": "4-pin fan header (12 V / PWM / tach)",
}

# Parts with no meaningful proximity constraint.  The reason is mandatory:
# "not important" is a design statement, not an omission.
FREE: dict[str, str] = {
    "2R6": "I2C pull-up; the bus is a distributed net, any point on it is equivalent",
    "2R7": "I2C pull-up; the bus is a distributed net, any point on it is equivalent",
    "6D1": "panel LED; position set by the enclosure/light pipe, no electrical limit",
    "6D2": "panel LED; position set by the enclosure/light pipe, no electrical limit",
    "6D3": "panel LED; position set by the enclosure/light pipe, no electrical limit",
    "6D4": "panel LED; position set by the enclosure/light pipe, no electrical limit",
}

# Reference parts: their own position is set by their satellites, so they carry
# no outward limit.  The limits live on the parts that must come to them (and on
# the receivers they must stay away from); this keeps the rule on the side that
# actually moves.
ANCHORS: dict[str, str] = {
    "2U1": "charger controller; its gates, filters and shunts carry the limits",
    "5U1": "output controller; its gates, filters and shunt carry the limits",
    "5L1": "switching inductor; keep-away is asserted on AFE/crystal/USB/harness",
}

# --------------------------------------------------------------------------- #
# A — input protection
# --------------------------------------------------------------------------- #
# Fuse and TVS sit at the connector so the unfused/undamped stub is short.
add("1J1", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=3.0,
    why="panel connector body must sit at the outline, not proud of it",
    req="IF-1")
add("1F1", "1J1", "pad", max_mm=10, net="+12V_IN",
    why="fuse is the first element after the connector",
    src="LM5069 §11.1 (input loop)", req="FR-11")
add("1F1", "1R1", "pad", max_mm=10, net="N_AF",
    why="fuse feeds the current-limit shunt directly",
    src="LM5069 §11.1", req="FR-11")
add("1D1", "1F1", "pad", max_mm=10, net="N_AF",
    why="TVS clamps at the fuse output, before the pass FET",
    src="LM5069 §11.1", req="FR-11")
add("1Q1", "1U1", "pad", max_mm=10, net="N_GATE",
    why="gate loop to the hot-swap controller",
    src="LM5069 §11.1", req="FR-1", primary=True)
add("1Q1", "1R1", "pad", max_mm=5, net="VIN_LM",
    why="pass FET source and shunt are one power loop",
    src="LM5069 §11.1", req="FR-11")
add("1R1", "1U1", "pad", max_mm=10, net="VIN_LM",
    why="shunt at the SENSE/VIN pins, Kelvin tap (checked by sense_report)",
    src="LM5069 §11.1", req="NFR-11", primary=True)
add("1R1", "1Q1", "pad", max_mm=5, net="VIN_LM",
    why="shunt in the FET source loop", src="LM5069 §11.1", req="FR-11")
add("1U1", "1Q1", "pad", max_mm=10, net="N_GATE",
    why="controller within one gate-drive loop of its FET",
    src="LM5069 §11.1", req="FR-1")
add("1U1", "1F1", "pad", max_mm=20, net="N_AF",
    why="hot-swap controller sits at the input, not behind the board",
    src="LM5069 §11.1", req="FR-11")
add("1C1", "1U1", "pad", max_mm=3, net="N_TMR",
    why="timer capacitor is a pin bypass", src="LM5069 §11.1", req="FR-11")
for r, net in (("1R2", "N_UV"), ("1R3", "N_UV"),
               ("1R4", "N_OV"), ("1R5", "N_OV")):
    add(r, "1U1", "pad", max_mm=10, net=net,
        why="UVLO/OVLO divider belongs at the controller sense pins",
        src="LM5069 §11.1", req="FR-11")
add("1R6", "1U1", "pad", max_mm=10, net="N_PWR",
    why="power-limit resistor at the PWR pin", src="LM5069 §11.1", req="FR-11")
add("1R7", "1U1", "pad", max_mm=10, net="N_PGD",
    why="PGD pull-up at the status pin", src="LM5069 §11.1", req="FR-11")

# --------------------------------------------------------------------------- #
# B — priority power path
# --------------------------------------------------------------------------- #
# LM74700-Q1 §12.1: ANODE/GATE/CATHODE close to the FET source/gate/drain;
# the VCAP capacitor stays away from the FET (thermal drift of capacitance).
add("3U1", "3Q1", "pad", max_mm=5, net="N_PGATE",
    why="gate pin within one short gate loop of the FET",
    src="LM74700-Q1 §12.1", req="FR-1")
add("3Q1", "3U1", "pad", max_mm=5, net="N_PGATE",
    why="LM74700 gate controller is the FET's functional host",
    src="LM74700-Q1 §12.1", req="FR-1", primary=True)
add("3U1", "3Q1", "pad", max_mm=5, net="VBAT",
    why="ANODE at the FET source", src="LM74700-Q1 §12.1", req="FR-1")
add("3U1", "3Q1", "pad", max_mm=5, net="VIN_SYS",
    why="CATHODE at the FET drain", src="LM74700-Q1 §12.1", req="FR-1")
add("3C1", "3U1", "pad", max_mm=5, net="N_VCAP",
    why="charge-pump capacitor across VCAP and ANODE",
    src="LM74700-Q1 §12.1", req="FR-1")
thermal("3C1", "3Q1", 5,
        why="keep the charge-pump cap off the FET's heat (capacitance drift)",
        src="LM74700-Q1 §12.1", req="FR-1")
add("3R1", "3U1", "pad", max_mm=10, net="IN_VALID",
    why="input-valid pull-down at the controller pin",
    src="LM74700-Q1 §12.1", req="FR-1")
add("3Q1", "4Q2", "pad", max_mm=20, net="VBAT",
    why="pack-branch FET sits between the BMS output and VIN_SYS",
    src="BQ76942 §18.1 (pack path)", req="FR-1")

# The 470 µF pair is input hold-up for the *converter*, not a charger cap:
# during the handover it has to carry the converter input until the pack FET
# takes over.  Electrical reach 15 mm; thermal keep-away from the switching cell.
add(("3C2", "3C3"), "5U1", "pad", max_mm=15, net="VIN_SYS",
    why="hold-up sits at the converter input that must ride through handover",
    src="BOM §2 / sim power-path.cir", req="FR-2")
add(("3C2", "3C3"), "5Q1", "pad", max_mm=10, net="VIN_SYS",
    why="bulk loop closes at the input FET, not through a long rail",
    src="LM5176 §10.1", req="FR-2")
thermal(("3C2", "3C3"), "5Q1", 4,
        why="electrolyte life: keep the can off the FET heat",
        src="LM74700-Q1 §12.1 (thermal), capacitor lifetime", req="NFR-3")
thermal(("3C2", "3C3"), "5L1", 4,
        why="electrolyte life: keep the can off the inductor heat",
        req="NFR-3")

# --------------------------------------------------------------------------- #
# C — charger (BQ25720)
# --------------------------------------------------------------------------- #
# Gate loops and switch-node components: Table 12-1 rules 2–9.
for q, gnet in (("2Q1", "N_G3"), ("2Q2", "N_G4"),
                ("2Q3", "N_G5"), ("2Q4", "N_G6")):
    add(q, "2U1", "pad", max_mm=5, net=gnet,
        why="gate trace is a high-di/dt loop; keep it at the IC",
        src="BQ25720 Table 12-1 rule 9", req="NFR-1", primary=True)
# Switching cell: Q1/Q2 + L1 + Q3/Q4 all within one 10 mm loop.
for q, net in (("2Q1", "SW1"), ("2Q2", "SW1"),
               ("2Q3", "SW2"), ("2Q4", "SW2")):
    add(q, "2L1", "pad", max_mm=10, net=net,
        why="switch node and inductor are one high-di/dt loop",
        src="BQ25720 Table 12-1 rules 2–6", req="NFR-1")
add("2Q1", "2Q2", "pad", max_mm=5, net="SW1",
    why="input half-bridge loop", src="BQ25720 Table 12-1 rule 2", req="NFR-1")
add("2Q3", "2Q4", "pad", max_mm=5, net="SW2",
    why="output half-bridge loop", src="BQ25720 Table 12-1 rule 4", req="NFR-1")
add("2Q1", "2R1", "pad", max_mm=5, net="N_ACN",
    why="RAC in the input loop with Q1/Q2",
    src="BQ25720 Table 12-1 rule 2", req="NFR-11")
add("2Q4", "2R2", "pad", max_mm=5, net="VSYS",
    why="RSR in the battery output loop with Q4",
    src="BQ25720 Table 12-1 rule 5", req="NFR-11")
add("2L1", "2U1", "pad", max_mm=10, net="SW1",
    why="power stage at the controller", src="BQ25720 Table 12-1 rule 6",
    req="NFR-1")
thermal(("2Q1", "2Q2", "2Q3", "2Q4"), "2U1", 3,
        why="controller next to, not under, the hot FETs",
        src="BQ25720 Table 12-1 rule 6", req="NFR-3")

# Shunt Kelvin reach (the tap itself is checked by sense_report.py).
add("2R1", "2U1", "pad", max_mm=10, net="N_ACN",
    why="RAC differential pair to ACP/ACN",
    src="BQ25720 Table 12-1 rule 7", req="NFR-11", primary=True)
add("2R2", "2U1", "pad", max_mm=10, net="VSYS",
    why="RSR differential pair to SRP/SRN",
    src="BQ25720 Table 12-1 rule 7", req="NFR-11", primary=True)

# Pin bypass and filter parts: "close to IC" → 3 mm pad.
for r, net in (("2C3", "REGN"), ("2C4", "VDDA"),
               ("2C6", "N_COMP2"),
               ("2C7", "N_PSYS"),
               ("2R3", "N_CBP"), ("2R4", "N_CBP"), ("2R5", "ILIM_HIZ")):
    add(r, "2U1", "pad", max_mm=3, net=net,
        why="pin bypass / filter capacitor belongs at the pin, not the rail",
        src="BQ25720 Table 12-1 rule 8", req="NFR-1")
for r, net in (("2C1", "N_BTST1"), ("2C2", "N_BTST2")):
    add(r, "2U1", "pad", max_mm=3, net=net,
        why="bootstrap capacitor at the controller and its switch node",
        src="BQ25720 Table 12-1 rule 9", req="NFR-1", primary=True)
# COMP1/IADPT/IBAT have a series resistor; the capacitor sits at the resistor,
# not at the controller pin (the pin sees the filtered node).
add("2C5", "2R8", "pad", max_mm=3, net="N_COMP1B",
    why="COMP1 capacitor at the series resistor", src="BQ25720 §9", req="NFR-1")
add("2C8", "2R9", "pad", max_mm=3, net="N_IADPTB",
    why="IADPT capacitor at the series resistor", src="BQ25720 §9", req="NFR-1")
add("2C9", "2R10", "pad", max_mm=3, net="N_IBATB",
    why="IBAT capacitor at the series resistor", src="BQ25720 §9", req="NFR-1")
for r in ("2C5", "2C8", "2C9"):
    add(r, "2U1", "edge", max_mm=5,
        why="filter network stays beside its controller",
        src="BQ25720 Table 12-1 rule 8", req="NFR-1")
# Bootstrap caps are a two-pad loop: one side at the IC, the other at the switch.
add("2C1", "2Q1", "pad", max_mm=3, net="SW1",
    why="BTST1–SW1 loop", src="BQ25720 Table 12-1 rule 9", req="NFR-1")
add("2C2", "2Q4", "pad", max_mm=3, net="SW2",
    why="BTST2–SW2 loop", src="BQ25720 Table 12-1 rule 9", req="NFR-1")
for r, net, cap in (("2R8", "N_COMP1", "2C5"),
                    ("2R9", "N_IADPT", "2C8"),
                    ("2R10", "N_IBAT", "2C9")):
    add(r, "2U1", "pad", max_mm=3, net=net,
        why="series filter resistor at its controller pin",
        src="BQ25720 Table 12-1 rule 8", req="NFR-1")
    add(r, cap, "edge", max_mm=3,
        why="RC filter pair stays together", src="BQ25720 §9", req="NFR-1")
for r, net in (("2R11", "N_CHGOK"), ("2R12", "N_PROCHOT")):
    add(r, "2U1", "pad", max_mm=10, net=net,
        why="status pull-up at the open-drain pin",
        src="BQ25720 §7", req="FR-7")

# --------------------------------------------------------------------------- #
# E — battery AFE (BQ76942)
# --------------------------------------------------------------------------- #
# §18.1: all cell-filter components at the device, not at the connector; the
# sense shunt gets a Kelvin pair; REG18 bypass as close as possible.
for r, net in (("4C1", "N_REG18"), ("4C2", "N_REG2"), ("4C3", "N_REG1"),
               ("4C4", "PACK+"), ("4C5", "N_CP1"),
               ("4C6", "VC0"), ("4C7", "VC1"), ("4C8", "VC2"),
               ("4C9", "VC3"), ("4C10", "VC4")):
    add(r, "4U1", "pad", max_mm=3, net=net,
        why="cell-input / supply filter at the AFE pin",
        src="BQ76942 §18.1", req="FR-12")
for r, net in (("4R9", "VC0"), ("4R10", "VC1"), ("4R11", "VC2"),
               ("4R12", "VC3"), ("4R13", "VC4")):
    add(r, "4U1", "pad", max_mm=5, net=net,
        why="100 Ω cell filter resistor at the VC pin",
        src="BQ76942 §18.1", req="FR-12")
    add(r, "4J7", "pad", max_mm=30, net=net.replace("VC", "CELL"),
        why="cell tap reaches the harness header",
        src="BQ76942 §18.1", req="FR-12")
add("4R1", "4U1", "pad", max_mm=10, net="CELL0",
    why="1 mΩ shunt Kelvin pair to SRP/SRN",
    src="BQ76942 §18.1", req="NFR-11", primary=True)
add("4R1", "4J6", "pad", max_mm=5, net="CELL0",
    why="shunt sits in the pack return at the terminal",
    src="BQ76942 §18.1", req="FR-12")
for q, gnet in (("4Q1", "N_CHG"), ("4Q2", "N_DSG")):
    add(q, "4U1", "pad", max_mm=10, net=gnet,
        why="gate loop to the AFE charge pump",
        src="BQ76942 §18.1", req="FR-11", primary=True)
add("4Q1", "4Q2", "pad", max_mm=5, net="N_PACKMID",
    why="common-source protection pair", src="BQ76942 §18.1", req="FR-11")
thermal(("4Q1", "4Q2"), "4U1", 5,
        why="AFE next to, not on, the hot protection FETs",
        src="BQ76942 §18.1", req="NFR-3")
add("4Q1", "4J6", "pad", max_mm=10, net="PACK+",
    why="pack protection FETs at the pack terminal",
    src="BQ76942 §18.1", req="FR-11")
add("4Q2", "2R2", "pad", max_mm=15, net="VBAT",
    why="battery sense shunt at the pack output",
    src="BQ25720 Table 12-1 rule 5", req="NFR-11")
add("4J6", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=3.0,
    why="pack terminal is a harness exit at the outline", req="IF-2")
add("4J6", "4R1", "pad", max_mm=5, net="CELL0",
    why="pack return enters the shunt directly", req="FR-12")
add("4J7", "4R9", "pad", max_mm=30, net="CELL0",
    why="cell harness reaches the filter bank", req="IF-2")
thermal("4J7", ("2L1", "5L1"), 15,
        why="cell-tap harness away from the switching inductors",
        req="NFR-11")

# NTCs sense the pack, not the board: near the cell harness, away from heat.
for r, net in (("4R2", "TS1"), ("4R3", "TS2"), ("4R4", "TS3")):
    add(r, "4U1", "pad", max_mm=30, net=net,
        why="TS line reaches the AFE; the NTC itself is at the pack",
        src="BQ76942 §18.1", req="FR-4")
    add(r, "4J7", "edge", max_mm=20,
        why="NTC should measure the pack/cell harness, not the PCB",
        req="FR-4")
    thermal(r, ("2L1", "5L1", "2Q1", "2Q2", "2Q3", "2Q4",
                "5Q1", "5Q2", "5Q3", "5Q4"), 15,
            why="NTC must not read board heat from the power stage",
            req="FR-4")
for r, net in (("4R5", "N_ALERT"), ("4R6", "N_RST"),
               ("4R7", "N_CFETOFF"), ("4R8", "N_DFETOFF")):
    add(r, "4U1", "pad", max_mm=10, net=net,
        why="bias/status pull-up at the AFE pin",
        src="BQ76942 §18.1", req="FR-7")

# --------------------------------------------------------------------------- #
# D — output converter (LM5176)
# --------------------------------------------------------------------------- #
# §10.1: gate loops at the IC, switching cell together, Kelvin sense, pin
# bypass/filter at the pins, FB divider at FB.
for q, gnet in (("5Q1", "N_G7"), ("5Q2", "N_G8"),
                ("5Q3", "N_G9"), ("5Q4", "N_G10")):
    add(q, "5U1", "pad", max_mm=5, net=gnet,
        why="gate loop; forward and return close together",
        src="LM5176 §10.1", req="NFR-1", primary=True)
for q, net in (("5Q1", "SW1_OUT"), ("5Q2", "SW1_OUT"),
               ("5Q3", "SW2_OUT"), ("5Q4", "SW2_OUT")):
    add(q, "5L1", "pad", max_mm=10, net=net,
        why="switch node and inductor are one high-di/dt loop",
        src="LM5176 §10.1", req="NFR-1")
add("5Q1", "5Q2", "pad", max_mm=5, net="SW1_OUT",
    why="buck half-bridge loop", src="LM5176 §10.1", req="NFR-1")
add("5Q3", "5Q4", "pad", max_mm=5, net="SW2_OUT",
    why="boost half-bridge loop", src="LM5176 §10.1", req="NFR-1")
add("5R3", "5U1", "pad", max_mm=10, net="N_CS",
    why="CS/CSG Kelvin pair to the shunt",
    src="LM5176 §10.1", req="NFR-11", primary=True)
add("5R3", "5Q2", "pad", max_mm=5, net="N_CS",
    why="shunt in the low-side current path",
    src="LM5176 §10.1", req="NFR-11")
add("5R3", "5Q3", "pad", max_mm=5, net="N_CS",
    why="shunt in the low-side current path",
    src="LM5176 §10.1", req="NFR-11")
add("5C1", "5U1", "pad", max_mm=3, net="VIN_SYS",
    why="VIN pin ceramic bypass", src="LM5176 §10.1", req="NFR-1")
add("5C1", "5Q1", "pad", max_mm=3, net="VIN_SYS",
    why="input switching-current loop closes at the high-side FET",
    src="LM5176 §10.1", req="NFR-1")
for r, net in (("5C4", "N_SS"), ("5C5", "N_COMP"),
               ("5C6", "N_SLOPE"), ("5C7", "N_DITH"),
               ("5C8", "VCC")):
    add(r, "5U1", "pad", max_mm=3, net=net,
        why="pin bypass / timing capacitor at the IC pin",
        src="LM5176 §10.1", req="NFR-1")
for r, net in (("5C2", "N_BOOT1"), ("5C3", "N_BOOT2")):
    add(r, "5U1", "pad", max_mm=3, net=net,
        why="bootstrap capacitor at the controller and its switch node",
        src="LM5176 §10.1", req="NFR-1", primary=True)
add("5C2", "5Q1", "pad", max_mm=3, net="SW1_OUT",
    why="BOOT1–SW1 loop", src="LM5176 §10.1", req="NFR-1")
add("5C3", "5Q4", "pad", max_mm=3, net="SW2_OUT",
    why="BOOT2–SW2 loop", src="LM5176 §10.1", req="NFR-1")
for r, net in (("5R1", "N_FB"), ("5R2", "N_FB")):
    add(r, "5U1", "pad", max_mm=3, net=net,
        why="feedback divider at the FB pin, not at the output",
        src="LM5176 §10.1", req="FR-3")
for r, net in (("5R4", "N_RT"), ("5R5", "N_MODE"), ("5R6", "N_COMP")):
    add(r, "5U1", "pad", max_mm=3, net=net,
        why="frequency/mode/compensation set component at its pin",
        src="LM5176 §10.1", req="FR-3")
for r, net in (("5R7", "N_EN"), ("5R8", "N_EN"), ("5R9", "N_PGOOD")):
    add(r, "5U1", "pad", max_mm=10, net=net,
        why="enable/status divider at the controller",
        src="LM5176 §10.1", req="FR-3")

# Output bulk: at the connector and at the inductor output, but off the heat.
add("5C9", "5J2", "pad", max_mm=15, net="VOUT12",
    why="bulk output capacitor feeds the XT30 directly",
    src="LM5176 §10.1", req="IF-3")
add("5C9", "5Q4", "pad", max_mm=10, net="VOUT12",
    why="boost output loop", src="LM5176 §10.1", req="IF-3")
thermal("5C9", ("5L1", "5Q4"), 4,
        why="electrolyte life: keep the can off inductor/FET heat",
        req="NFR-3")
add("5C10", "5Q4", "pad", max_mm=3, net="VOUT12",
    why="ceramic output capacitor at the switching cell",
    src="LM5176 §10.1", req="IF-3")
add("5C10", "5J2", "pad", max_mm=15, net="VOUT12",
    why="output ceramic also feeds the connector",
    req="IF-3")
add("5Q4", "5J2", "pad", max_mm=15, net="VOUT12",
    why="output FET to connector", req="IF-3")
add("5J2", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=3.0,
    why="output connector is a panel/harness exit", req="IF-3")

# --------------------------------------------------------------------------- #
# F — control, host link, UI
# --------------------------------------------------------------------------- #
add("6U1", "6Y1", "pad", max_mm=5, net="N_XIN",
    why="crystal at XIN/XOUT; load capacitance is part of the oscillator",
    src="RP2040 hardware design §2.3", req="FR-7")
add("6U1", "6U2", "pad", max_mm=15, net="N_QCS",
    why="QSPI flash on short, direct traces",
    src="RP2040 hardware design §2.2", req="FR-7")
add("6U2", "6U1", "pad", max_mm=15, net="N_QCS",
    why="QSPI flash on short, direct traces",
    src="RP2040 hardware design §2.2", req="FR-7")
add("6U3", "6U1", "pad", max_mm=15, net="+3V3",
    why="3.3 V regulator at the load it feeds",
    src="RP2040 hardware design §2.1", req="FR-7")
add("6C3", "6U3", "pad", max_mm=3, net="VIN_SYS",
    why="3.3 V buck input bypass", src="RP2040 hardware design §2.1",
    req="FR-7")
add("6C4", "6U1", "pad", max_mm=5, net="+3V3",
    why="IOVDD decoupling at the MCU pins",
    src="RP2040 hardware design §2.1.2", req="FR-7")
add("6C4", "6U3", "pad", max_mm=10, net="+3V3",
    why="regulator output capacitor",
    src="RP2040 hardware design §2.1", req="FR-7")
add("6C5", "6U1", "pad", max_mm=3, net="N_DVDD",
    why="1 µF DVDD bypass at VREG_OUT",
    src="RP2040 hardware design §2.1.2", req="FR-7")
for r, net in (("6C1", "N_XIN"), ("6C2", "N_XOUT")):
    add(r, "6U1", "pad", max_mm=3, net=net,
        why="crystal load capacitor at the oscillator pin",
        src="RP2040 hardware design §2.3", req="FR-7")
    add(r, "6Y1", "edge", max_mm=3,
        why="load capacitor at the crystal body",
        src="RP2040 hardware design §2.3", req="FR-7")
add("6R1", "6U1", "pad", max_mm=10, net="N_RUN",
    why="RUN pull-up at the MCU", src="RP2040 datasheet", req="FR-7")
for r, net, led, lednet in (("6R2", "N_LED1", "6D1", "N_LEDA1"),
                            ("6R3", "N_LED2", "6D2", "N_LEDA2"),
                            ("6R4", "N_LED3", "6D3", "N_LEDA3"),
                            ("6R5", "N_LED4", "6D4", "N_LEDA4")):
    add(r, "6U1", "pad", max_mm=20, net=net,
        why="LED drive from the MCU", req="FR-13")
    add(r, led, "pad", max_mm=10, net=lednet,
        why="series resistor at its LED", req="FR-13")

for r, net in (("6R6", "N_USBDM"), ("6R7", "N_USBDP")):
    add(r, "6U1", "pad", max_mm=3, net=net,
        why="27 Ω USB series termination at the chip",
        src="RP2040 hardware design §2.4", req="FR-7")
add("6R8", "6J5", "pad", max_mm=10, net="N_FANTACH",
    why="tach pull-up at the fan header", req="FR-16")
add("6J3", "6R6", "pad", max_mm=10, net="N_USBDM_C",
    why="USB data pair to its series termination",
    src="RP2040 hardware design §2.4", req="IF-4")
add("6J3", "6U1", "edge", max_mm=20,
    why="connector reach to the MCU (through the 27 Ω resistors)",
    src="RP2040 hardware design §2.4", req="IF-4")
add("6J3", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=3.0,
    why="USB-C receptacle at the outline", req="IF-4")
add("6J4", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=6.0,
    why="SWD header must stay accessible", req="NFR-10")
add("6J4", "6U1", "pad", max_mm=30, net="N_SWCLK",
    why="programming header reach", req="NFR-10")
add("6J5", "6U1", "pad", max_mm=20, net="N_FANPWM",
    why="fan PWM/tach to the MCU", req="FR-16")
add("6J5", "BOARD_EDGE", "board_edge", min_mm=0.5, max_mm=6.0,
    why="fan header at the outline", req="FR-16")

# --------------------------------------------------------------------------- #
# EMI / thermal keep-aways across blocks
# --------------------------------------------------------------------------- #
# 300–800 kHz power inductors are the radiators; the AFE, crystal, USB and
# cell harness are the receivers.
for host in ("2L1", "5L1"):
    thermal("4U1", host, 20,
            why="AFE away from the switching magnetic field",
            src="BQ76942 §18.1", req="NFR-11")
    thermal("4J7", host, 15,
            why="cell-sense harness away from the switching field",
            req="NFR-11")
    thermal("6Y1", host, 15,
            why="crystal away from switching field",
            src="RP2040 hardware design §2.3", req="FR-7")
    thermal("6J3", host, 15,
            why="USB connector away from switching field",
            src="RP2040 hardware design §2.4", req="IF-4")
    thermal(("6R6", "6R7"), host, 10,
            why="USB series resistors away from switching field",
            req="IF-4")
    thermal("6U2", host, 10,
            why="QSPI flash away from switching field",
            req="FR-7")


# --------------------------------------------------------------------------- #
# coverage helpers
# --------------------------------------------------------------------------- #
def limits_for(ref: str) -> list[Limit]:
    return [l for l in LIMITS if l.part == ref]


def constrained_parts() -> set[str]:
    return {l.part for l in LIMITS}


def hosts_for(ref: str) -> list[str]:
    return [l.host for l in LIMITS if l.part == ref]


def validate(known_refs) -> list[str]:
    """Return coverage problems for a board's reference set."""
    known = set(known_refs)
    problems = []
    for r in sorted(known - set(ROLES)):
        problems.append(f"{r}: no role")
    for r in sorted(set(ROLES) - known):
        problems.append(f"{r}: role but not on the board")
    for l in LIMITS:
        if l.part not in known:
            problems.append(f"limit for unknown part {l.part}")
        if l.host != "BOARD_EDGE" and l.host not in known:
            problems.append(f"{l.part}: unknown host {l.host}")
        if l.measure not in ("pad", "edge", "board_edge"):
            problems.append(f"{l.part}: bad measure {l.measure}")
        if l.max_mm is None and l.min_mm == 0:
            problems.append(f"{l.part}: limit has neither min nor max")
        if l.max_mm is not None and l.max_mm < l.min_mm:
            problems.append(f"{l.part}: max < min")
    for r in sorted(known - constrained_parts() - set(FREE) - set(ANCHORS)):
        problems.append(f"{r}: neither constrained, FREE nor an anchor")
    for r in sorted(set(FREE) | set(ANCHORS)):
        if r not in known:
            problems.append(f"FREE/anchor part {r} not on the board")
        if r in constrained_parts():
            problems.append(f"FREE/anchor part {r} also has limits")
    return problems


def as_json(ref: str) -> list[dict]:
    """Limits for one part, in graph/JSON form (for the placement UI)."""
    return [{
        "host": l.host, "measure": l.measure, "min": l.min_mm,
        "max": l.max_mm, "net": l.net, "why": l.why,
        "src": l.src, "req": l.req, "primary": l.primary,
    } for l in limits_for(ref)]


if __name__ == "__main__":
    import json
    print(f"{len(ROLES)} roles, {len(LIMITS)} limits, {len(FREE)} free")
    print(json.dumps({r: as_json(r) for r in sorted(constrained_parts())},
                     indent=1))
