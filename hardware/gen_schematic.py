#!/usr/bin/env python3
"""Generate the TinyUPS KiCad schematic from a netlist description.

Approach
--------
* Symbols come from the KiCad standard libraries (Device, Transistor_FET,
  Connector_Generic, power) plus a small generated ``tinyups`` library of
  box symbols for the ICs (authored from their datasheets).
* Connectivity is expressed as **named labels placed on each pin**. KiCad
  connects same-named labels on a sheet, so no wire routing is required and
  the result is deterministic and diff-friendly.
* Run ``make erc`` afterwards; the goal is a clean ERC.

This is a *generator*: edit the description below, re-run, and the schematic
is rebuilt. Kept deliberately small and readable.
"""
from __future__ import annotations

import copy
import os
import uuid as _uuid
from dataclasses import dataclass, field

from kiutils.items.common import Effects, Fill, Font, Position, Property, Stroke
from kiutils.items.schitems import Connection, LocalLabel, NoConnect
from kiutils.items.syitems import SyRect
from kiutils.schematic import (Schematic, SchematicSymbol, SymbolInstance,
                               SymbolProjectInstance, SymbolProjectPath)
from kiutils.symbol import Symbol, SymbolLib, SymbolPin

KICAD_SYMBOLS = "/usr/share/kicad/symbols"
HERE = os.path.dirname(os.path.abspath(__file__))
GRID = 1.27


# --------------------------------------------------------------------------- #
# library + placement helpers
# --------------------------------------------------------------------------- #
_LIBS: dict[str, SymbolLib] = {}


def _lib(path: str) -> SymbolLib:
    if path not in _LIBS:
        _LIBS[path] = SymbolLib.from_file(path)
    return _LIBS[path]


def std(libname: str, entry: str) -> Symbol:
    s = copy.deepcopy(
        next(x for x in _lib(f"{KICAD_SYMBOLS}/{libname}.kicad_sym").symbols
             if x.entryName == entry)
    )
    s.libraryNickname = libname
    return s


def _pin_local(sym: Symbol, number: str) -> tuple[float, float]:
    for u in sym.units:
        for p in u.pins:
            if str(p.number) == str(number):
                return p.position.X, p.position.Y
    raise KeyError(f"{sym.entryName}: no pin {number}")


# footprint per part (verified to exist in the KiCad libraries)
_FP = {
    "Fuse": "Fuse:Fuse_1206_3216Metric",
    "L": "Inductor_SMD:L_12x12mm_H8mm",
    "D_TVS": "Diode_SMD:D_SMB",
    "Q_NMOS_GSD": "Package_TO_SOT_SMD:TO-252-2",
    "LED": "LED_SMD:LED_0805_2012Metric",
    "Crystal": "Crystal:Crystal_SMD_5032-2Pin_5.0x3.2mm",
    "Conn_01x03": "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
    "Conn_01x04": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
    "LM5069": "Package_SO:VSSOP-10_3x3mm_P0.5mm",
    "LM74700-Q1": "Package_TO_SOT_SMD:SOT-23-6",
    "BQ25720": "Package_DFN_QFN:QFN-32-1EP_4x4mm_P0.4mm_EP2.65x2.65mm",
    "LM5176": "Package_DFN_QFN:QFN-28-1EP_4x4mm_P0.4mm_EP2.4x2.4mm",
    "BQ76942": "Package_QFP:TQFP-48_7x7mm_P0.5mm",
    "RP2040": "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
    "W25Q128": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "REG_3V3": "Package_TO_SOT_SMD:SOT-23-5",
}


def default_fp(sym: Symbol, value: str | None) -> str:
    e = sym.entryName
    if e == "R":
        return ("Resistor_SMD:R_2512_6332Metric"
                if value and value.endswith("m") else
                "Resistor_SMD:R_0805_2012Metric")
    if e == "C":
        return ("Capacitor_SMD:CP_Elec_8x10"
                if value in ("470u", "220u") else
                "Capacitor_SMD:C_0805_2012Metric")
    return _FP.get(e, "")


class Builder:
    def __init__(self) -> None:
        self.sch = Schematic.create_new()
        self.sch.libSymbols = []
        self._lib_ids: set[str] = set()
        self._refcount: dict[str, int] = {}
        self._syms: dict[str, tuple] = {}
        self._x = 40.0
        self._y = 40.0

    # -- symbols ----------------------------------------------------------- #
    def _register(self, sym: Symbol) -> None:
        libid = f"{sym.libraryNickname}:{sym.entryName}"
        if libid not in self._lib_ids:
            self.sch.libSymbols.append(copy.deepcopy(sym))
            self._lib_ids.add(libid)

    def place(self, sym: Symbol, ref: str, value: str | None = None,
              x: float | None = None, y: float | None = None,
              angle: float = 0, fp: str | None = None) -> SchematicSymbol:
        if x is None:
            x, y = self._next_slot()
        x = round(x / GRID) * GRID
        y = round(y / GRID) * GRID
        fp = fp if fp is not None else default_fp(sym, value)
        self._register(sym)
        ss = SchematicSymbol(
            libraryNickname=sym.libraryNickname, entryName=sym.entryName,
            position=Position(X=x, Y=y, angle=angle), unit=1,
            inBom=True, onBoard=True, dnp=False, uuid=str(_uuid.uuid4()),
            properties=[
                Property(key="Reference", value=ref,
                         position=Position(X=x + 2.54, Y=y - 2.54, angle=0),
                         effects=Effects(font=Font(width=1.27, height=1.27))),
                Property(key="Value", value=value or sym.entryName,
                         position=Position(X=x + 2.54, Y=y + 2.54, angle=0),
                         effects=Effects(font=Font(width=1.27, height=1.27))),
                Property(key="Footprint", value=fp,
                         position=Position(X=x, Y=y, angle=0),
                         effects=Effects(hide=True)),
                Property(key="Datasheet", value="~",
                         position=Position(X=x, Y=y, angle=0),
                         effects=Effects(hide=True)),
            ],
            pins={},
            instances=[SymbolProjectInstance(
                name="tinyups",
                paths=[SymbolProjectPath(sheetInstancePath="/",
                                         reference=ref, unit=1)])],
        )
        for u in sym.units:
            for p in u.pins:
                ss.pins[str(p.number)] = _uuid.uuid4().hex
        self.sch.schematicSymbols.append(ss)
        self._syms[ref] = (ss, sym)
        return ss

    def _next_slot(self) -> tuple[float, float]:
        # lay components out on a coarse grid, 10 per row
        col = len(self._syms) % 10
        row = len(self._syms) // 10
        return 40.0 + col * 25.4, 40.0 + row * 25.4

    # -- connectivity ------------------------------------------------------ #
    def abs_pin(self, ref: str, number: str) -> tuple[float, float]:
        ss, sym = self._syms[ref]
        lx, ly = _pin_local(sym, str(number))
        # KiCad schematic Y is down, symbol library Y is up
        return ss.position.X + lx, ss.position.Y - ly

    def net(self, ref: str, number: str, name: str) -> None:
        x, y = self.abs_pin(ref, number)
        self.sch.labels.append(
            LocalLabel(text=name, position=Position(X=x, Y=y, angle=0),
                       effects=Effects(font=Font(width=1.27, height=1.27))))

    def nc(self, ref: str, number: str) -> None:
        x, y = self.abs_pin(ref, number)
        self.sch.noConnects.append(NoConnect(position=Position(X=x, Y=y, angle=0)))

    def pwr_flag(self, net: str, x: float, y: float) -> None:
        """Place a PWR_FLAG and tie it to a named net."""
        x = round(x / GRID) * GRID
        y = round(y / GRID) * GRID
        self.place(std("power", "PWR_FLAG"), "#FLG", "PWR_FLAG", x, y)
        self.sch.labels.append(
            LocalLabel(text=net, position=Position(X=x, Y=y, angle=0),
                       effects=Effects(font=Font(width=1.27, height=1.27))))

    def save(self, path: str) -> None:
        self.sch.to_file(path)


# --------------------------------------------------------------------------- #
# box-symbol generator for ICs
# --------------------------------------------------------------------------- #
def box_symbol(entry: str, ref: str, pins: list[tuple[str, str, str]],
               half_width: float = 12.7, row: float = 2.54) -> Symbol:
    """pins: list of (number, name, side) with side in {"L","R"}.

    All pins are passive (keeps ERC focused; power intent is in the docs).
    """
    left = [p for p in pins if p[2] == "L"]
    right = [p for p in pins if p[2] == "R"]
    rows = max(len(left), len(right), 1)
    half_h = ((rows + 1) / 2) * row
    top = half_h - row

    s = Symbol(entryName=entry, libraryNickname="tinyups",
               inBom=True, onBoard=True, isPower=False,
               properties=[
                   Property(key="Reference", value=ref, id=0,
                            effects=Effects(font=Font(width=1.27, height=1.27))),
                   Property(key="Value", value=entry, id=1,
                            effects=Effects(font=Font(width=1.27, height=1.27))),
                   Property(key="Footprint", value="", id=2,
                            effects=Effects(font=Font(width=1.27, height=1.27), hide=True)),
                   Property(key="Datasheet", value="~", id=3,
                            effects=Effects(font=Font(width=1.27, height=1.27), hide=True)),
               ],
               units=[])

    body = Symbol(unitId=0, styleId=1, entryName=entry)
    body.graphicItems.append(SyRect(
        start=Position(X=-half_width, Y=half_h),
        end=Position(X=half_width, Y=-half_h),
        stroke=Stroke(width=0.254), fill=Fill(type="background")))
    s.units.append(body)

    unit = Symbol(unitId=1, styleId=1, entryName=entry)
    for i, (num, name, side) in enumerate(left):
        y = top - i * row
        unit.pins.append(SymbolPin(
            electricalType="passive", graphicalStyle="line",
            position=Position(X=-half_width - 2.54, Y=y, angle=0), length=2.54,
            name=name, number=str(num),
            nameEffects=Effects(font=Font(width=1.27, height=1.27)),
            numberEffects=Effects(font=Font(width=1.27, height=1.27))))
    for i, (num, name, side) in enumerate(right):
        y = top - i * row
        unit.pins.append(SymbolPin(
            electricalType="passive", graphicalStyle="line",
            position=Position(X=half_width + 2.54, Y=y, angle=180), length=2.54,
            name=name, number=str(num),
            nameEffects=Effects(font=Font(width=1.27, height=1.27)),
            numberEffects=Effects(font=Font(width=1.27, height=1.27))))
    s.units.append(unit)
    return s


# --------------------------------------------------------------------------- #
# IC pin definitions (from the datasheets in docs/datasheets/)
# --------------------------------------------------------------------------- #
LM5069 = box_symbol("LM5069", "U", [
    ("1", "SENSE", "L"), ("2", "VIN", "L"), ("3", "UVLO", "L"),
    ("4", "OVLO", "L"), ("5", "GND", "L"),
    ("10", "GATE", "R"), ("9", "OUT", "R"), ("8", "PGD", "R"),
    ("7", "PWR", "R"), ("6", "TIMER", "R"),
])
LM74700 = box_symbol("LM74700-Q1", "U", [
    ("6", "ANODE", "L"), ("3", "EN", "L"), ("2", "GND", "L"),
    ("1", "VCAP", "R"), ("5", "GATE", "R"), ("4", "CATHODE", "R"),
])


def _split(pins: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Assign pins to left/right sides (first half left)."""
    half = (len(pins) + 1) // 2
    return [(n, nm, "L" if i < half else "R") for i, (n, nm) in enumerate(pins)]


BQ25720 = box_symbol("BQ25720", "U", _split([
    ("1", "VBUS"), ("2", "ACN"), ("3", "ACP"), ("4", "CHRG_OK"),
    ("5", "OTG/VAP/FRS"), ("6", "ILIM_HIZ"), ("7", "VDDA"), ("8", "IADPT"),
    ("9", "IBAT"), ("10", "PSYS"), ("11", "PROCHOT"), ("12", "SDA"),
    ("13", "SCL"), ("14", "CMPIN"), ("15", "CMPOUT"), ("16", "COMP1"),
    ("17", "COMP2"), ("18", "CELL_BATPRESZ"), ("19", "SRN"), ("20", "SRP"),
    ("21", "BATDRV"), ("22", "VSYS"), ("23", "SW2"), ("24", "HIDRV2"),
    ("25", "BTST2"), ("26", "LODRV2"), ("27", "PGND"), ("28", "REGN"),
    ("29", "LODRV1"), ("30", "BTST1"), ("31", "HIDRV1"), ("32", "SW1"),
]))

CUSTOM_SYMBOLS = [LM5069, LM74700, BQ25720]

LM5176 = box_symbol("LM5176", "U", _split([
    ("1", "MODE"), ("2", "DITH"), ("3", "RT/SYNC"), ("4", "SLOPE"),
    ("5", "SS"), ("6", "COMP"), ("7", "AGND"), ("8", "FB"),
    ("9", "VOSNS"), ("10", "ISNS-"), ("11", "ISNS+"), ("12", "CSG"),
    ("13", "CS"), ("14", "PGOOD"), ("15", "SW2"), ("16", "HDRV2"),
    ("17", "BOOT2"), ("18", "LDRV2"), ("19", "PGND"), ("20", "VCC"),
    ("21", "BIAS"), ("22", "LDRV1"), ("23", "BOOT1"), ("24", "HDRV1"),
    ("25", "SW1"), ("26", "EN/UVLO"), ("27", "VIN"), ("28", "VISNS"),
]))

CUSTOM_SYMBOLS.append(LM5176)

BQ76942 = box_symbol("BQ76942", "U", _split([
    ("1", "NC"), ("2", "VC9"), ("3", "NC"), ("4", "VC8"), ("5", "NC"),
    ("6", "VC7"), ("7", "NC"), ("8", "VC6"), ("9", "NC"), ("10", "VC5"),
    ("11", "NC"), ("12", "VC4"), ("13", "VC3"), ("14", "VC2"), ("15", "VC1"),
    ("16", "VC0"), ("17", "VSS"), ("18", "SRP"), ("19", "NC"), ("20", "SRN"),
    ("21", "TS1"), ("22", "TS2"), ("23", "TS3"), ("24", "REG18"), ("25", "ALERT"),
    ("26", "SCL"), ("27", "SDA"), ("28", "HDQ"), ("29", "CFETOFF"), ("30", "DFETOFF"),
    ("31", "DCHG"), ("32", "DDSG"), ("33", "RST_SHUT"), ("34", "REG2"), ("35", "REG1"),
    ("36", "REGIN"), ("37", "BREG"), ("38", "FUSE"), ("39", "PDSG"), ("40", "PCHG"),
    ("41", "LD"), ("42", "PACK"), ("43", "DSG"), ("44", "NC"), ("45", "CHG"),
    ("46", "CP1"), ("47", "BAT"), ("48", "VC10"),
]))
CUSTOM_SYMBOLS.append(BQ76942)

RP2040 = box_symbol("RP2040", "U", _split([
    ("1", "IOVDD"), ("2", "GPIO0"), ("3", "GPIO1"), ("4", "GPIO2"),
    ("5", "GPIO3"), ("6", "GPIO4"), ("7", "GPIO5"), ("8", "GPIO6"),
    ("9", "GPIO7"), ("10", "IOVDD"), ("11", "GPIO8"), ("12", "GPIO9"),
    ("13", "GPIO10"), ("14", "GPIO11"), ("15", "GPIO12"), ("16", "GPIO13"),
    ("17", "GPIO14"), ("18", "GPIO15"), ("19", "TESTEN"), ("20", "XIN"),
    ("21", "XOUT"), ("22", "IOVDD"), ("23", "DVDD"), ("24", "SWCLK"),
    ("25", "SWDIO"), ("26", "RUN"), ("27", "GPIO16"), ("28", "GPIO17"),
    ("29", "GPIO18"), ("30", "GPIO19"), ("31", "GPIO20"), ("32", "GPIO21"),
    ("33", "IOVDD"), ("34", "GPIO22"), ("35", "GPIO23"), ("36", "GPIO24"),
    ("37", "GPIO25"), ("38", "GPIO26/ADC0"), ("39", "GPIO27/ADC1"),
    ("40", "GPIO28/ADC2"), ("41", "GPIO29/ADC3"), ("42", "IOVDD"),
    ("43", "ADC_AVDD"), ("44", "VREG_VIN"), ("45", "VREG_VOUT"),
    ("46", "USB_DM"), ("47", "USB_DP"), ("48", "USB_VDD"), ("49", "IOVDD"),
    ("50", "QSPI_SD3"), ("51", "QSPI_SCLK"), ("52", "QSPI_SD0"),
    ("53", "QSPI_SD2"), ("54", "QSPI_SD1"), ("55", "QSPI_SS"),
    ("56", "IOVDD"), ("57", "GND"),
]))
FLASH = box_symbol("W25Q128", "U", _split([
    ("1", "CS"), ("2", "CLK"), ("3", "IO0"), ("4", "IO1"),
    ("5", "IO2"), ("6", "IO3"), ("7", "VCC"), ("8", "GND"),
]))
REG3V3 = box_symbol("REG_3V3", "U", _split([
    ("1", "VIN"), ("2", "GND"), ("3", "EN"), ("4", "VOUT"),
]))
CUSTOM_SYMBOLS += [RP2040, FLASH, REG3V3]


def build() -> Schematic:
    b = Builder()
    b._syms = {}

    # ---- Block A: input protection + LM5069 hot-swap --------------------- #
    b.place(std("Connector_Generic", "Conn_01x02"), "J1", "XT60", 40.0, 40.0,
            fp="Connector_Wire:SolderWire-2.5sqmm_1x02_P8.8mm_D2.4mm_OD4.4mm")
    b.place(std("Device", "Fuse"), "F1", "25A", 63.5, 40.0)
    b.place(std("Device", "D_TVS"), "D1", "SMBJ15A", 88.9, 40.0)
    b.place(std("Device", "R"), "R1", "2.2m", 114.3, 40.0)   # Rsense
    b.place(LM5069, "U1", "LM5069", 152.4, 45.72)
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q1", "N-FET 40V", 139.7, 71.12)
    b.place(std("Device", "R"), "R2", "TBD-UV-hi", 63.5, 71.12)
    b.place(std("Device", "R"), "R3", "TBD-UV-lo", 63.5, 96.52)
    b.place(std("Device", "R"), "R4", "TBD-OV-hi", 88.9, 71.12)
    b.place(std("Device", "R"), "R5", "TBD-OV-lo", 88.9, 96.52)
    b.place(std("Device", "C"), "C1", "TBD", 114.3, 71.12)   # timer
    b.place(std("Device", "R"), "R6", "TBD-PWR", 114.3, 96.52)
    b.place(std("Device", "R"), "R7", "100k-PGD", 139.7, 40.0)

    N = b.net
    # connector / input rail
    N("J1", "1", "+12V_IN"); N("J1", "2", "GND")
    N("F1", "1", "+12V_IN"); N("F1", "2", "N_AF")
    N("D1", "1", "N_AF");    N("D1", "2", "GND")
    N("R1", "1", "N_AF");    N("R1", "2", "VIN_LM")
    # LM5069
    N("U1", "1", "N_AF")       # SENSE
    N("U1", "2", "VIN_LM")     # VIN
    N("U1", "3", "N_UV")       # UVLO
    N("U1", "4", "N_OV")       # OVLO
    N("U1", "5", "GND")        # GND
    N("U1", "10", "N_GATE")    # GATE
    N("U1", "9", "VIN_SYS")    # OUT
    N("U1", "8", "N_PGD")      # PGD
    N("U1", "7", "N_PWR")      # PWR
    N("U1", "6", "N_TMR")      # TIMER
    # pass FET
    N("Q1", "1", "N_GATE"); N("Q1", "3", "VIN_LM"); N("Q1", "2", "VIN_SYS")
    # UVLO divider
    N("R2", "1", "VIN_LM"); N("R2", "2", "N_UV")
    N("R3", "1", "N_UV");   N("R3", "2", "GND")
    # OVLO divider
    N("R4", "1", "VIN_LM"); N("R4", "2", "N_OV")
    N("R5", "1", "N_OV");   N("R5", "2", "GND")
    # timer / power-limit / PGD pull-up
    N("C1", "1", "N_TMR");  N("C1", "2", "GND")
    N("R6", "1", "N_PWR");  N("R6", "2", "GND")
    N("R7", "1", "+12V_IN"); N("R7", "2", "N_PGD")

    # ---- Block B: priority power path (pack ideal diode, LM74700) -------- #
    b.place(LM74700, "U2", "LM74700-Q1", 40.0, 121.92)
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q2", "N-FET 40V", 63.5, 121.92)
    b.place(std("Device", "C"), "C2", "100n", 88.9, 121.92)   # charge-pump cap
    b.place(std("Device", "C"), "C3", "470u", 114.3, 121.92)  # converter hold-up
    b.place(std("Device", "C"), "C4", "470u", 139.7, 121.92)  # converter hold-up
    b.place(std("Device", "R"), "R8", "100k", 63.5, 147.32)   # EN pull-down (pack off)

    N("U2", "6", "VBAT")      # ANODE  (pack +)
    N("U2", "2", "GND")       # GND
    N("U2", "3", "IN_VALID")  # EN  (from input-valid detect; low = pack off)
    N("U2", "1", "N_VCAP")    # VCAP
    N("U2", "5", "N_PGATE")   # GATE
    N("U2", "4", "N_CATH")    # CATHODE (to FET drain)
    N("Q2", "1", "N_PGATE"); N("Q2", "3", "N_CATH"); N("Q2", "2", "VBAT")
    N("C2", "1", "N_VCAP"); N("C2", "2", "VBAT")
    N("C3", "1", "VIN_SYS"); N("C3", "2", "GND")
    N("C4", "1", "VIN_SYS"); N("C4", "2", "GND")
    N("R8", "1", "IN_VALID"); N("R8", "2", "GND")

    # ---- Block C: 4S LFP charger (BQ25720) ------------------------------- #
    b.place(BQ25720, "U3", "BQ25720", 190.5, 45.72)
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q3", "N-FET 30V", 190.5, 96.52)  # buck HS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q4", "N-FET 30V", 215.9, 96.52)  # buck LS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q5", "N-FET 30V", 241.3, 96.52)  # boost LS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q6", "N-FET 30V", 266.7, 96.52)  # boost HS
    b.place(std("Device", "L"), "L2", "2.2u", 228.6, 121.92)
    b.place(std("Device", "R"), "R9", "5m", 165.1, 45.72)    # input sense
    b.place(std("Device", "R"), "R10", "5m", 165.1, 71.12)   # battery sense
    b.place(std("Device", "C"), "C5", "47n", 190.5, 121.92)  # BTST1
    b.place(std("Device", "C"), "C6", "47n", 215.9, 121.92)  # BTST2
    b.place(std("Device", "C"), "C7", "1u", 241.3, 121.92)   # REGN
    b.place(std("Device", "C"), "C8", "1u", 266.7, 121.92)   # VDDA
    b.place(std("Device", "R"), "R11", "100k", 165.1, 96.52)  # CELL_BATPRESZ top
    b.place(std("Device", "R"), "R12", "100k", 165.1, 121.92)  # CELL_BATPRESZ bottom
    b.place(std("Device", "R"), "R13", "10k", 190.5, 147.32)   # ILIM_HIZ

    N("U3", "1", "VBUS"); N("R9", "1", "VBUS"); N("U3", "3", "VBUS")   # VBUS/ACP
    N("U3", "2", "N_ACN"); N("R9", "2", "N_ACN"); N("Q3", "3", "N_ACN")
    N("U3", "32", "SW1"); N("Q3", "2", "SW1"); N("Q4", "3", "SW1")
    N("L2", "1", "SW1"); N("C5", "2", "SW1")
    N("U3", "23", "SW2"); N("Q5", "3", "SW2"); N("Q6", "2", "SW2")
    N("L2", "2", "SW2"); N("C6", "2", "SW2")
    N("U3", "22", "VSYS"); N("Q6", "3", "VSYS"); N("R10", "1", "VSYS")
    N("U3", "20", "VSYS")                                             # SRP
    N("U3", "19", "VBAT"); N("R10", "2", "VBAT")                      # SRN
    N("U3", "30", "N_BTST1"); N("C5", "1", "N_BTST1")
    N("U3", "25", "N_BTST2"); N("C6", "1", "N_BTST2")
    N("U3", "28", "REGN"); N("C7", "1", "REGN")
    N("U3", "7", "VDDA"); N("C8", "1", "VDDA"); N("R11", "1", "VDDA")
    N("U3", "18", "N_CBP"); N("R11", "2", "N_CBP"); N("R12", "1", "N_CBP")
    N("U3", "6", "ILIM_HIZ"); N("R13", "1", "ILIM_HIZ")
    N("U3", "31", "N_G3"); N("Q3", "1", "N_G3")
    N("U3", "29", "N_G4"); N("Q4", "1", "N_G4")
    N("U3", "26", "N_G5"); N("Q5", "1", "N_G5")
    N("U3", "24", "N_G6"); N("Q6", "1", "N_G6")
    N("Q4", "2", "GND"); N("Q5", "2", "GND"); N("C7", "2", "GND")
    N("C8", "2", "GND"); N("R12", "2", "GND"); N("R13", "2", "GND")
    N("U3", "27", "GND")                                              # PGND
    N("U3", "12", "I2C_SDA"); N("U3", "13", "I2C_SCL")
    b.place(std("Device", "R"), "R14", "10k", 215.9, 147.32)  # SDA pull-up
    b.place(std("Device", "R"), "R15", "10k", 241.3, 147.32)  # SCL pull-up
    N("R14", "1", "I2C_SDA"); N("R14", "2", "+3V3")
    N("R15", "1", "I2C_SCL"); N("R15", "2", "+3V3")
    # compensation / monitors / status (from PMP22419)
    b.place(std("Device", "R"), "R40", "10k", 304.8, 381.0)    # COMP1
    b.place(std("Device", "C"), "C29", "10n", 330.2, 381.0)
    b.place(std("Device", "C"), "C30", "1n", 355.6, 381.0)     # COMP2
    b.place(std("Device", "C"), "C31", "100n", 381.0, 381.0)   # PSYS
    b.place(std("Device", "R"), "R41", "10k", 406.4, 381.0)    # IADPT
    b.place(std("Device", "C"), "C32", "100n", 431.8, 381.0)
    b.place(std("Device", "R"), "R42", "10k", 457.2, 381.0)    # IBAT
    b.place(std("Device", "C"), "C33", "100n", 482.6, 381.0)
    b.place(std("Device", "R"), "R43", "10k", 508.0, 381.0)    # CHRG_OK pull-up
    b.place(std("Device", "R"), "R44", "10k", 533.4, 381.0)    # PROCHOT pull-up
    N("U3", "16", "N_COMP1"); N("R40", "1", "N_COMP1")
    N("R40", "2", "N_COMP1B"); N("C29", "1", "N_COMP1B"); N("C29", "2", "GND")
    N("U3", "17", "N_COMP2"); N("C30", "1", "N_COMP2"); N("C30", "2", "GND")
    N("U3", "10", "N_PSYS"); N("C31", "1", "N_PSYS"); N("C31", "2", "GND")
    N("U3", "8", "N_IADPT"); N("R41", "1", "N_IADPT")
    N("R41", "2", "N_IADPTB"); N("C32", "1", "N_IADPTB"); N("C32", "2", "GND")
    N("U3", "9", "N_IBAT"); N("R42", "1", "N_IBAT")
    N("R42", "2", "N_IBATB"); N("C33", "1", "N_IBATB"); N("C33", "2", "GND")
    N("U3", "4", "N_CHGOK"); N("R43", "1", "N_CHGOK"); N("R43", "2", "+3V3")
    N("U3", "11", "N_PROCHOT"); N("R44", "1", "N_PROCHOT"); N("R44", "2", "+3V3")
    N("U3", "14", "GND")   # CMPIN tied to ground (unused comparator)
    N("U3", "5", "GND")    # OTG/VAP/FRS disabled
    b.nc("U3", "15")       # CMPOUT (float)
    b.nc("U3", "21")       # BATDRV (no BATFET in this design)

    # ---- Block D: 12 V output buck-boost (LM5176) ------------------------ #
    b.place(LM5176, "U4", "LM5176", 330.2, 45.72)
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q7", "N-FET 40V", 330.2, 96.52)   # buck HS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q8", "N-FET 40V", 355.6, 96.52)   # buck LS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q9", "N-FET 40V", 381.0, 96.52)   # boost LS
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q10", "N-FET 40V", 406.4, 96.52)  # boost HS
    b.place(std("Device", "L"), "L3", "1u0", 368.3, 121.92)
    b.place(std("Device", "R"), "R16", "100k", 330.2, 147.32)
    b.place(std("Device", "R"), "R17", "7k15", 355.6, 147.32)
    b.place(std("Device", "R"), "R18", "1m", 381.0, 147.32)    # current sense
    b.place(std("Device", "R"), "R19", "27k", 406.4, 147.32)   # RT/SYNC
    b.place(std("Device", "R"), "R20", "93k1", 304.8, 147.32)  # MODE
    b.place(std("Device", "R"), "R21", "10k", 330.2, 172.72)   # COMP
    b.place(std("Device", "R"), "R22", "100k", 355.6, 172.72)  # EN top
    b.place(std("Device", "R"), "R23", "10k", 381.0, 172.72)   # EN bottom
    b.place(std("Device", "R"), "R24", "100k", 406.4, 172.72)  # PGOOD pull-up
    b.place(std("Device", "C"), "C9", "10u", 304.8, 96.52)     # input cap
    b.place(std("Device", "C"), "C10", "100n", 304.8, 121.92)  # BOOT1
    b.place(std("Device", "C"), "C11", "100n", 330.2, 121.92)  # BOOT2
    b.place(std("Device", "C"), "C12", "10n", 355.6, 121.92)   # SS
    b.place(std("Device", "C"), "C13", "1n", 381.0, 121.92)    # COMP
    b.place(std("Device", "C"), "C14", "1n", 406.4, 121.92)    # SLOPE
    b.place(std("Device", "C"), "C15", "1n", 304.8, 172.72)    # DITH
    b.place(std("Device", "C"), "C16", "1u", 330.2, 198.12)    # VCC
    b.place(std("Device", "C"), "C17", "220u", 355.6, 198.12)  # output
    b.place(std("Device", "C"), "C18", "10u", 381.0, 198.12)   # output
    b.place(std("Connector_Generic", "Conn_01x02"), "J2", "XT30", 406.4, 198.12,
            fp="Connector_Wire:SolderWire-2.5sqmm_1x02_P7.2mm_D2.4mm_OD3.6mm")

    N("U4", "27", "VIN_SYS"); N("U4", "28", "VIN_SYS"); N("C9", "1", "VIN_SYS")
    N("U4", "25", "SW1_OUT"); N("Q7", "2", "SW1_OUT"); N("Q8", "3", "SW1_OUT")
    N("L3", "1", "SW1_OUT"); N("C10", "2", "SW1_OUT")
    N("U4", "15", "SW2_OUT"); N("Q9", "3", "SW2_OUT"); N("Q10", "2", "SW2_OUT")
    N("L3", "2", "SW2_OUT"); N("C11", "2", "SW2_OUT")
    N("Q7", "3", "VIN_SYS"); N("C9", "2", "GND")
    N("Q8", "2", "N_CS"); N("Q9", "2", "N_CS"); N("U4", "13", "N_CS"); N("R18", "1", "N_CS")
    N("U4", "12", "GND"); N("R18", "2", "GND")
    N("Q10", "3", "VOUT12"); N("U4", "9", "VOUT12"); N("R16", "1", "VOUT12")
    N("C17", "1", "VOUT12"); N("C18", "1", "VOUT12"); N("J2", "1", "VOUT12")
    N("U4", "8", "N_FB"); N("R16", "2", "N_FB"); N("R17", "1", "N_FB")
    N("U4", "10", "N_ISNS"); N("U4", "11", "N_ISNS")
    N("U4", "23", "N_BOOT1"); N("C10", "1", "N_BOOT1")
    N("U4", "17", "N_BOOT2"); N("C11", "1", "N_BOOT2")
    N("U4", "20", "VCC"); N("C16", "1", "VCC"); N("U4", "21", "VCC")
    N("U4", "24", "N_G7"); N("Q7", "1", "N_G7")
    N("U4", "22", "N_G8"); N("Q8", "1", "N_G8")
    N("U4", "18", "N_G9"); N("Q9", "1", "N_G9")
    N("U4", "16", "N_G10"); N("Q10", "1", "N_G10")
    N("U4", "26", "N_EN"); N("R22", "2", "N_EN"); N("R23", "1", "N_EN")
    N("R22", "1", "VIN_SYS")
    N("U4", "3", "N_RT"); N("R19", "1", "N_RT")
    N("U4", "1", "N_MODE"); N("R20", "1", "N_MODE")
    N("U4", "4", "N_SLOPE"); N("C14", "1", "N_SLOPE")
    N("U4", "5", "N_SS"); N("C12", "1", "N_SS")
    N("U4", "6", "N_COMP"); N("R21", "1", "N_COMP"); N("C13", "1", "N_COMP")
    N("U4", "2", "N_DITH"); N("C15", "1", "N_DITH")
    N("U4", "7", "GND"); N("U4", "19", "GND")
    N("U4", "14", "N_PGOOD"); N("R24", "1", "N_PGOOD")
    for _c in ("C12", "C13", "C14", "C15", "C16", "C17", "C18"):
        N(_c, "2", "GND")
    for _r in ("R17", "R19", "R20", "R21", "R23", "R24"):
        N(_r, "2", "GND" if _r not in ("R24",) else "+3V3")
    N("J2", "2", "GND")

    # ---- Block E: battery AFE / BMS (BQ76942) ---------------------------- #
    b.place(BQ76942, "U5", "BQ76942", 482.6, 45.72)
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q11", "N-FET 40V", 431.8, 121.92)  # CHG
    b.place(std("Transistor_FET", "Q_NMOS_GSD"), "Q12", "N-FET 40V", 457.2, 121.92)  # DSG
    b.place(std("Device", "R"), "R25", "1m", 431.8, 147.32)   # pack current sense
    for _i in range(5):
        b.place(std("Device", "R"), f"Rf{_i}", "100", 304.8 + _i * 25.4, 223.52)
        b.place(std("Device", "C"), f"Cf{_i}", "100n", 304.8 + _i * 25.4, 248.92)
    b.place(std("Device", "C"), "C19", "1u", 431.8, 172.72)   # REG18
    b.place(std("Device", "C"), "C20", "1u", 457.2, 172.72)   # REG2
    b.place(std("Device", "C"), "C21", "1u", 482.6, 172.72)   # REG1
    b.place(std("Device", "C"), "C22", "1u", 508.0, 172.72)   # REGIN
    b.place(std("Device", "C"), "C23", "100n", 533.4, 172.72)  # CP1
    b.place(std("Device", "R"), "R26", "10k-NTC", 431.8, 198.12)
    b.place(std("Device", "R"), "R27", "10k-NTC", 457.2, 198.12)
    b.place(std("Device", "R"), "R28", "10k-NTC", 482.6, 198.12)
    b.place(std("Device", "R"), "R29", "100k", 508.0, 198.12)  # ALERT pull-up
    b.place(std("Device", "R"), "R30", "100k", 533.4, 198.12)  # RST_SHUT pull-up

    # cell taps (external 4S pack) + input RC filters
    for _i in range(5):
        N(f"Rf{_i}", "1", f"CELL{_i}"); N(f"Rf{_i}", "2", f"VC{_i}")
        N(f"Cf{_i}", "1", f"VC{_i}")
        N(f"Cf{_i}", "2", f"CELL{_i - 1}" if _i > 0 else "GND")
    N("U5", "16", "VC0"); N("U5", "15", "VC1"); N("U5", "14", "VC2")
    N("U5", "13", "VC3"); N("U5", "12", "VC4")
    for _p in ("2", "4", "6", "8", "10", "48"):
        N("U5", _p, "CELL4")
    N("U5", "18", "CELL0")   # SRP (pack -)
    N("U5", "17", "GND"); N("U5", "20", "GND")   # VSS, SRN
    N("R25", "1", "CELL0"); N("R25", "2", "GND")
    N("U5", "21", "TS1"); N("R26", "1", "TS1")
    N("U5", "22", "TS2"); N("R27", "1", "TS2")
    N("U5", "23", "TS3"); N("R28", "1", "TS3")
    N("U5", "24", "N_REG18"); N("C19", "1", "N_REG18")
    N("U5", "34", "N_REG2"); N("C20", "1", "N_REG2")
    N("U5", "35", "N_REG1"); N("C21", "1", "N_REG1")
    N("U5", "36", "VBAT"); N("C22", "1", "VBAT")
    N("U5", "46", "N_CP1"); N("C23", "1", "N_CP1")
    N("U5", "25", "N_ALERT"); N("R29", "1", "N_ALERT")
    N("U5", "33", "N_RST"); N("R30", "1", "N_RST")
    N("U5", "26", "I2C_SCL"); N("U5", "27", "I2C_SDA")
    N("U5", "47", "VBAT"); N("U5", "43", "N_DSG"); N("Q12", "1", "N_DSG")
    N("U5", "45", "N_CHG"); N("Q11", "1", "N_CHG")
    N("Q11", "3", "VBAT"); N("Q12", "2", "VBAT")
    N("Q11", "2", "N_PACKMID"); N("Q12", "3", "N_PACKMID")
    N("C23", "2", "VBAT"); N("R29", "2", "+3V3")
    for _c in ("C19", "C20", "C21", "C22"):
        N(_c, "2", "GND")
    for _r in ("R26", "R27", "R28", "R30"):
        N(_r, "2", "GND")
    # CFETOFF/DFETOFF held high (from the BQ76942 EVM)
    b.place(std("Device", "R"), "R45", "100k", 558.8, 381.0)
    b.place(std("Device", "R"), "R46", "100k", 584.2, 381.0)
    N("U5", "29", "N_CFETOFF"); N("R45", "1", "N_CFETOFF"); N("R45", "2", "N_REG1")
    N("U5", "30", "N_DFETOFF"); N("R46", "1", "N_DFETOFF"); N("R46", "2", "N_REG1")
    for _p in ("1", "3", "5", "7", "9", "11", "19", "28", "31", "32",
               "37", "38", "39", "40", "41", "42", "44"):
        b.nc("U5", _p)

    # ---- Block F: MCU / USB / fan / UI (RP2040) -------------------------- #
    b.place(RP2040, "U6", "RP2040", 558.8, 45.72)
    b.place(FLASH, "U7", "W25Q128", 558.8, 172.72)
    b.place(REG3V3, "U8", "3V3", 482.6, 248.92)
    b.place(std("Connector_Generic", "Conn_01x03"), "J3", "USB", 584.2, 223.52)
    b.place(std("Connector_Generic", "Conn_01x03"), "J4", "SWD", 584.2, 248.92)
    b.place(std("Connector_Generic", "Conn_01x04"), "J5", "FAN", 584.2, 274.32)
    b.place(std("Device", "Crystal"), "Y1", "12MHz", 508.0, 248.92)
    b.place(std("Device", "R"), "R31", "1k", 508.0, 274.32)   # RUN pull-up
    b.place(std("Device", "R"), "R36", "27", 508.0, 299.72)   # USB DM series
    b.place(std("Device", "R"), "R37", "27", 533.4, 299.72)   # USB DP series
    b.place(std("Device", "R"), "R38", "10k", 558.8, 299.72)  # tach pull-up
    for _i in range(4):
        b.place(std("Device", "R"), f"R{32 + _i}", "1k", 482.6 + _i * 25.4, 325.12)
        b.place(std("Device", "LED"), f"D{2 + _i}", "LED", 482.6 + _i * 25.4, 350.52)
    b.place(std("Device", "C"), "C24", "20p", 431.8, 248.92)  # XIN load
    b.place(std("Device", "C"), "C25", "20p", 457.2, 248.92)  # XOUT load
    b.place(std("Device", "C"), "C26", "10u", 431.8, 274.32)  # 3V3 in
    b.place(std("Device", "C"), "C27", "10u", 457.2, 274.32)  # 3V3 out
    b.place(std("Device", "C"), "C28", "1u", 431.8, 299.72)   # DVDD

    # power / ground
    for _p in ("1", "10", "22", "33", "42", "43", "44", "48", "49", "56"):
        N("U6", _p, "+3V3")
    N("U6", "19", "GND"); N("U6", "57", "GND")            # TESTEN, EP
    N("U6", "45", "N_DVDD"); N("U6", "23", "N_DVDD"); N("C28", "1", "N_DVDD")
    N("C28", "2", "GND")
    N("U8", "1", "VIN_SYS"); N("U8", "3", "VIN_SYS"); N("U8", "4", "+3V3")
    N("U8", "2", "GND"); N("C26", "1", "VIN_SYS"); N("C26", "2", "GND")
    N("C27", "1", "+3V3"); N("C27", "2", "GND")
    # clock
    N("U6", "20", "N_XIN"); N("Y1", "1", "N_XIN"); N("C24", "1", "N_XIN")
    N("U6", "21", "N_XOUT"); N("Y1", "2", "N_XOUT"); N("C25", "1", "N_XOUT")
    N("C24", "2", "GND"); N("C25", "2", "GND")
    # reset + debug
    N("U6", "26", "N_RUN"); N("R31", "1", "N_RUN"); N("R31", "2", "+3V3")
    N("U6", "24", "N_SWCLK"); N("J4", "1", "N_SWCLK")
    N("U6", "25", "N_SWDIO"); N("J4", "2", "N_SWDIO")
    N("J4", "3", "GND")
    # USB (data only)
    N("U6", "46", "N_USBDM"); N("R36", "1", "N_USBDM"); N("R36", "2", "N_USBDM_C")
    N("U6", "47", "N_USBDP"); N("R37", "1", "N_USBDP"); N("R37", "2", "N_USBDP_C")
    N("J3", "1", "N_USBDM_C"); N("J3", "2", "N_USBDP_C"); N("J3", "3", "GND")
    # QSPI flash
    N("U6", "55", "N_QCS"); N("U7", "1", "N_QCS")
    N("U6", "51", "N_QCLK"); N("U7", "2", "N_QCLK")
    N("U6", "52", "N_QIO0"); N("U7", "3", "N_QIO0")
    N("U6", "54", "N_QIO1"); N("U7", "4", "N_QIO1")
    N("U6", "53", "N_QIO2"); N("U7", "5", "N_QIO2")
    N("U6", "50", "N_QIO3"); N("U7", "6", "N_QIO3")
    N("U7", "7", "+3V3"); N("U7", "8", "GND")
    # I2C to charger + AFE
    N("U6", "6", "I2C_SDA"); N("U6", "7", "I2C_SCL")
    # input-valid control (pack enable)
    N("U6", "13", "IN_VALID")
    # fan: PWM + tach
    N("U6", "4", "N_FANPWM"); N("J5", "3", "N_FANPWM")
    N("U6", "5", "N_FANTACH"); N("J5", "4", "N_FANTACH"); N("R38", "1", "N_FANTACH")
    N("R38", "2", "+3V3")
    N("J5", "1", "VOUT12"); N("J5", "2", "GND")
    # status LEDs
    for _i in range(4):
        _gp = ("8", "9", "11", "12")[_i]
        N("U6", _gp, f"N_LED{_i + 1}")
        N(f"R{32 + _i}", "1", f"N_LED{_i + 1}")
        N(f"R{32 + _i}", "2", f"N_LEDA{_i + 1}")
        N(f"D{2 + _i}", "2", f"N_LEDA{_i + 1}")   # anode
        N(f"D{2 + _i}", "1", "GND")               # cathode
    for _p in ("2", "3", "14", "15", "16", "17", "18", "27", "28", "29",
               "30", "31", "32", "34", "35", "36", "37", "38", "39", "40", "41"):
        b.nc("U6", _p)

    # mark the externally-sourced power nets (ready for pin typing in layout)
    b.pwr_flag("+12V_IN", 25.4, 25.4)
    b.pwr_flag("GND", 25.4, 50.8)
    b.pwr_flag("VBAT", 25.4, 76.2)
    b.pwr_flag("VOUT12", 25.4, 101.6)
    b.pwr_flag("+3V3", 25.4, 127.0)

    return b.sch


if __name__ == "__main__":
    sch = build()
    out = os.path.join(HERE, "tinyups.kicad_sch")
    sch.to_file(out)
    # also emit the custom symbol library so the project's symbol table resolves
    libdir = os.path.join(HERE, "libs")
    os.makedirs(libdir, exist_ok=True)
    lib = SymbolLib()
    lib.symbols = [copy.deepcopy(s) for s in CUSTOM_SYMBOLS]
    lib.to_file(os.path.join(libdir, "tinyups.kicad_sym"))
    print(f"wrote {out}: {len(sch.schematicSymbols)} symbols")
