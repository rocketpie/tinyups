"""The placement spec must cover the board and must not guess hosts.

These tests are cheap and do not need a routed board: they read the board's
reference set and the spec.  The point is the rule from history 0030 — every
part's function and target is written down, and a rail cap is not attributed
to whichever switch happens to be nearest.
"""

import os
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hardware"))

import placement_spec as spec  # noqa: E402


def _refs():
    board = pcbnew.LoadBoard(os.path.join(ROOT, "hardware", "tinyups.kicad_pcb"))
    return [fp.GetReference() for fp in board.GetFootprints()]


def test_spec_covers_every_board_part():
    problems = spec.validate(_refs())
    assert not problems, "\n".join(problems)


def test_every_limit_is_documented():
    for lim in spec.LIMITS:
        assert lim.why, f"{lim.part} -> {lim.host}: no reason"
        assert lim.req, f"{lim.part} -> {lim.host}: no requirement id"
        assert lim.max_mm is not None or lim.min_mm > 0


def test_rail_caps_have_designed_hosts_not_nearest_switch():
    # The four VIN_SYS caps serve different blocks.  6C3 is the 3.3 V buck's
    # input bypass; the two 470 uF parts are converter input hold-up, not
    # charger caps and not "5Q1's caps".
    assert spec.hosts_for("6C3") == ["6U3"]
    assert "5U1" in spec.hosts_for("3C2")
    assert "5U1" in spec.hosts_for("3C3")
    assert "5Q1" in spec.hosts_for("5C1")
    assert "6U3" not in spec.hosts_for("3C2")
    assert "5U1" not in spec.hosts_for("6C3")


def test_free_parts_say_why():
    assert spec.FREE
    for ref, why in spec.FREE.items():
        assert why, f"{ref}: free but no reason"
    for ref, why in spec.ANCHORS.items():
        assert why, f"{ref}: anchor but no reason"
