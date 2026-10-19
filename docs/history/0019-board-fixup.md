# 0019 – board fixup: stale parts, power nets

**What:** the 0007 part follow-up existed only in `tinyups.kicad_sch` and the
BOM; the board still carried the 1206 fuse and the five 2512 shunts
(`make drc --schematic-parity`: 9 mismatches). `hardware/sync_footprints.py`
now replaces a mismatched footprint, keeps pose / path / reference / value,
remaps pads by number and takes the BOM/DNP flags from the schematic. The board
has the ATO fuse and the WSR2 shunts; parity is 0.

**Also:** `place-apply` left the pours swept through the old pad positions (284
clearance + 199 mask items on `fixed1`); it now regenerates the pour set it
inherited and fills. The regeneration must delete zones with `BOARD.Delete()`,
not `Remove()` — the latter frees the proxies under the board and the next
`GetFootprints()` walk crashes.

**Power nets:** `power_channel.py` read x/y swapped, so the channel numbers were
measured on a transposed grid; no-net TO-252 thermal pads were counted as
obstacles (`N_PACKMID` 11.0 → 2.0 mm); `CELL0`/`CELL4` were 17 A although they
are Kelvin taps. The grid is `(row, col)` now, no-net pads are ignored, nets
below 0.5 mm are skipped, and the cell taps are 0.01 A. On `fixed2` the corrected
gate has one marginal rail: `N_CS` 7.0 / 7.5 mm (1.1×).

**Status:** fixed. The part swap invalidated the earlier `fixed1` route/power
numbers; the pad gate that stays red is the FET-package item in
[0007](0007-power-pads-limit.md), not these tools.
