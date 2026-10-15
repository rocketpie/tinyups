#!/usr/bin/env python3
"""Functional-block map for TinyUPS, and the block-flow reference scheme.

Reference designators carry the block's position in the power flow as a leading
digit, then the component type and a per-block counter:

    ``1F1``  input-protection fuse        (block A, IP  = 1)
    ``2R1``  first charger resistor       (block C, CHG = 2)
    ``3Q1``  priority-path FET            (block B, PP  = 3)
    ``4Q1``  battery-management FET       (block E, BMS = 4)
    ``5R7``  output-regulation resistor   (block D, OR  = 5)
    ``6U1``  control MCU                  (block F, CTL = 6)

Counters restart per block and per component type; connectors keep their
familiar ``J`` numbers (``1J1`` XT60, ``5J2`` XT30, ``6J3`` USB, ``4J6`` PACK).

This module is the single source of truth for the block membership, used by
`gen_schematic.py` (to name the symbols), `gen_pcb.py` / `routing_report.py`
(to group parts) and `power_map.py` (overrides).
"""
from __future__ import annotations

import re

# block -> prefix shown on the board (documentation / human reference)
PREFIX = {
    "A": "IP",     # input protection + hot-swap
    "B": "PP",     # priority power path
    "C": "CHG",    # charger
    "D": "OR",     # output regulation (buck-boost)
    "E": "BMS",    # battery AFE / management
    "F": "CTL",    # control (MCU / USB / fan)
}

# block -> number used in the reference designator, in power-flow order
# (back -> front): IP=1, CHG=2, PP=3, BMS=4, OR=5, CTL=6
BLOCK_NUM = {"A": 1, "C": 2, "B": 3, "E": 4, "D": 5, "F": 6}

# reserved width (mm) of the central power-path corridor. IPC-2221, 10 C rise,
# 1 oz outer copper: 20 A needs ~19 mm (2 oz: ~10 mm).  Set to 0 until the
# corridor is actually reserved on the board (see progress.md); place_metrics
# then measures distance to the corridor *edge* = |dx| - CORRIDOR_MM/2.
CORRIDOR_MM = 0.0
CORRIDOR_TARGET_MM = 20.0   # 1 oz outer copper, 20 A, 10 C rise

# block -> base reference designators (as used in gen_schematic.py)
BLOCKS = {
    "A": {"J1", "F1", "D1", "R1", "R2", "R3", "R4", "R5", "C1", "R6", "R7",
          "Q1", "U1"},
    "B": {"U2", "Q2", "C2", "C3", "C4", "R8"},
    "C": {"U3", "Q3", "Q4", "Q5", "Q6", "L2", "R9", "R10", "C5", "C6", "C7",
          "C8", "R11", "R12", "R13", "R14", "R15", "R40", "C29", "C30",
          "C31", "R41", "C32", "R42", "C33", "R43", "R44"},
    "D": {"U4", "Q7", "Q8", "Q9", "Q10", "L3", "R16", "R17", "R18", "R19",
          "R20", "R21", "R22", "R23", "R24", "C9", "C10", "C11", "C12",
          "C13", "C14", "C15", "C16", "C17", "C18", "J2"},
    "E": {"U5", "Q11", "Q12", "R25", "Rf0", "Rf1", "Rf2", "Rf3", "Rf4",
          "Cf0", "Cf1", "Cf2", "Cf3", "Cf4", "C19", "C20", "C21", "C22",
          "C23", "R26", "R27", "R28", "R29", "R30", "R45", "R46", "J6", "J7"},
    "F": {"U6", "U7", "U8", "J3", "J4", "J5", "Y1", "R31", "R36", "R37",
          "R38", "R32", "R33", "R34", "R35", "D2", "D3", "D4", "D5",
          "C24", "C25", "C26", "C27", "C28"},
}

_TYPE_ALIAS = {"Rf": "R", "Cf": "C"}     # cell filters count as R / C


def _split(ref: str) -> tuple[str, int]:
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def _build_label() -> dict[str, str]:
    counters: dict[tuple[str, str], int] = {}
    out: dict[str, str] = {}
    for blk, refs in BLOCKS.items():
        for ref in sorted(refs, key=_split):
            t = _TYPE_ALIAS.get(_split(ref)[0], _split(ref)[0])
            if t == "J":                         # keep familiar J1/J2/... numbers
                out[ref] = f"{BLOCK_NUM[blk]}{ref}"
                continue
            counters[(blk, t)] = counters.get((blk, t), 0) + 1
            out[ref] = f"{BLOCK_NUM[blk]}{t}{counters[(blk, t)]}"
    return out


LABEL = _build_label()                       # base ref -> block-prefixed ref
PREFIXED_BLOCKS = {b: {LABEL[r] for r in refs} for b, refs in BLOCKS.items()}


def label(ref: str) -> str:
    """Base ref -> block-prefixed ref (e.g. 'R9' -> '2R1')."""
    return LABEL.get(ref, ref)


def kind(ref: str) -> str:
    """Component type letters: '2R1'->'R', 'CHG.R1'->'R', 'Rf0'->'Rf', '1J1'->'J'."""
    s = ref.rsplit(".", 1)[-1]
    m = re.match(r"^\d*([A-Za-z]+)", s)
    return m.group(1) if m else s


def base(ref: str) -> str:
    """Block-prefixed ref -> base ref (e.g. 'CHG.R1' -> 'R9')."""
    for b, lab in LABEL.items():
        if lab == ref:
            return b
    return ref
