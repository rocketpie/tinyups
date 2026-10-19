# 0020 – FET drain and source are reversed on the board

**What:** every FET symbol is `Transistor_FET:Q_NMOS_GSD` (G=1, S=2, D=3), but
the footprint is `Package_TO_SOT_SMD:TO-252-2` (G=1, D=2 tab, S=3). The netlist
therefore puts the source net on the drain tab and the drain net on the source
lead. On `4Q1`/`4Q2` the mid-node `N_PACKMID` lands on both drains —
common-drain, while the BMS needs a common-source pair. Parity cannot see it:
the pad numbers match the netlist, the physical meaning does not.

**Why it matters:** the body diode and the gate reference are on the wrong
terminal, and the BMS pair no longer blocks in both directions. The Power56
land makes it worse: it is S=1/G=2/D=3, so a straight footprint sync would put
the gate net on the source pins.

**Status:** open — change the TO-252 symbols to `Q_NMOS_GDS` (or use a
GDS-numbered land) and the Power56 symbols to `Q_NMOS_SGD`, then swap the
pad-2/3 nets and re-place. Do this before syncing the Power56 footprints
([ADR-0015](../decisions/0015-terminal-rating-in-power-gate.md)).
