#!/usr/bin/env python3
"""Shared power specification: design current and nominal voltage per net.

Single source of truth for `power_report.py` (ampacity), `power_map.py`
(per-component dissipation) and `power_silk.py` (marking).  Values come from
`docs/requirements.md` and `docs/bom.md`; estimates are marked.

Current is the net's design current in A; volt is the nominal rail voltage.
"""
from __future__ import annotations

from dataclasses import dataclass

# net -> design current (A)
DESIGN_CURRENT = {
    "+12V_IN": 20.0,   # 12 V/20 A adapter, load + charge
    "N_AF": 20.0,      # after the fuse
    "VIN_LM": 20.0,    # LM5069 input (after R1 sense)
    "VIN_SYS": 20.0,   # system input rail
    "VBAT": 17.0,      # pack + (15 A cont / 17 A peak)
    "VSYS": 10.0,      # charger system node
    "VBUS": 10.0,      # charger input (RAC sense)
    "N_ACN": 10.0,     # charger input sense
    "SW1": 10.0,       # charger switch node
    "SW2": 10.0,
    "SW1_OUT": 17.0,   # output switch node
    "SW2_OUT": 17.0,
    "N_CS": 17.0,      # output current sense
    "N_PACKMID": 17.0, # pack protection FET mid-node
    "CELL0": 17.0,     # pack return through the 1 mOhm shunt 4R1, not a tap
    "CELL4": 0.01,     # pack + Kelvin tap (sense only)
    "PACK+": 17.0,     # pack terminal, through the protection FETs
    "VOUT12": 17.0,    # regulated output
    "N_VCAP": 0.05,    # LM74700 charge-pump cap (tiny)
    "+3V3": 1.0,       # logic rail (estimate)
    "VCC": 0.05,       # LM5176 VCC (tiny)
    "REGN": 0.05,
    "VDDA": 0.05,
}

# net -> nominal voltage (V)
RAIL_V = {
    "+12V_IN": 12.0, "N_AF": 12.0, "VIN_LM": 12.0, "VIN_SYS": 12.0,
    "VBAT": 13.8, "VSYS": 12.0, "VBUS": 12.0, "N_ACN": 12.0,
    "SW1": 12.0, "SW2": 12.0, "SW1_OUT": 12.0, "SW2_OUT": 12.0,
    "N_CS": 0.0, "N_PACKMID": 13.8, "CELL0": 0.0, "CELL4": 13.8, "PACK+": 13.8,
    "VOUT12": 12.0, "N_VCAP": 12.0, "+3V3": 3.3, "VCC": 5.0,
    "REGN": 6.0, "VDDA": 6.0, "GND": 0.0,
}


@dataclass(frozen=True)
class Terminal:
    """A component terminal's current rating, with its datasheet basis."""

    name: str
    amps: float
    basis: str
    url: str


# Terminal ratings are a *component* property, not a PCB trace: IPC-2221 cannot
# size a fuse blade, a shunt leadframe or a Power56 source.  Keyed by
# (footprint id as stored on the board, value).  A missing entry is printed as
# "unrated" and falls back to the conservative pad estimate — see ADR-0015.
PART_TERMINAL_A = {
    ("Fuse:Fuse_Blade_ATO_directSolder", "25A"): Terminal(
        "ATO 25 A", 25.0,
        "25 A ATO blade, 32 V; soldered land 8 x 3.8 mm",
        "https://www.farnell.com/datasheets/237771.pdf"),
    ("Resistor_SMD:R_Shunt_Vishay_WSR2_WSR3", "2.2m"): Terminal(
        "WSR2 2.2 mOhm", 30.0,
        "2 W at 2.2 mOhm (P = I^2 R); 0.88 W at 20 A",
        "https://www.vishay.com/docs/30101/wsr.pdf"),
    ("Resistor_SMD:R_Shunt_Vishay_WSR2_WSR3", "5m"): Terminal(
        "WSR2 5 mOhm", 20.0,
        "2 W at 5 mOhm; used at <= 10 A",
        "https://www.vishay.com/docs/30101/wsr.pdf"),
    ("Resistor_SMD:R_Shunt_Vishay_WSR2_WSR3", "1m"): Terminal(
        "WSR2 1 mOhm", 44.0,
        "2 W at 1 mOhm; 0.29 W at 17 A",
        "https://www.vishay.com/docs/30101/wsr.pdf"),
    ("Package_SON:VSONP-8-1EP_5x6_P1.27mm", "NTMFS5C410N"): Terminal(
        "NTMFS5C410N", 32.0,
        "ID 46 A at TA=25 C / 32 A at 100 C, 650 mm^2 2 oz land",
        "https://www.onsemi.com/download/data-sheet/pdf/ntmfs5c410n-d.pdf"),
    ("Package_SON:VSONP-8-1EP_5x6_P1.27mm", "NTMFS5C430N"): Terminal(
        "NTMFS5C430N", 25.0,
        "ID 35 A at TA=25 C / 25 A at 100 C, 650 mm^2 2 oz land",
        "https://www.onsemi.com/pdf/datasheet/ntmfs5c430-d.pdf"),
    ("Package_SON:VSONP-8-1EP_5x6_P1.27mm", "NTMFS4C01N"): Terminal(
        "NTMFS4C01N", 30.0,
        "ID 47 A at TA=25 C; 30 A at 100 C (RthJA 39 C/W, TJ 150 C)",
        "https://www.onsemi.com/pdf/datasheet/ntmfs4c01n-d.pdf"),
}


def terminal_rating(footprint: str, value: str) -> Terminal | None:
    """Datasheet terminal rating for a board footprint, if selected."""
    return PART_TERMINAL_A.get((footprint, value))


# component loss parameters (estimate where the datasheet value isn't in the
# schematic value string)
RDS_ON = {"N-FET 40V": 0.002, "N-FET 30V": 0.004}   # ohm
INDUCTOR_DCR = 0.003                                 # ohm
CAP_ESR = 0.010                                      # ohm
FUSE_R = 0.005                                       # ohm
CONNECTOR_R = 0.001                                  # ohm
IC_POWER = 0.20                                      # W (gate drive + quiescent)

# capacitor ripple-current model: I_rms = V_ripple_rms / |Z|,
# |Z| = ESR + 1/(2*pi*f*C).  A cap's size is set by C*V (energy), not by
# power, so its "handling" is ripple current (RMS), not DC.
RIPPLE_V_RMS = 0.05                                  # assumed rail ripple (V rms)
SW_FREQ = 300e3                                      # Hz (output converter)
