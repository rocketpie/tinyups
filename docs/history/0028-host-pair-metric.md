# 0028 – a rail bypass belongs to a switch, not to the nearest controller

**What:** the belongs-to force only considered ICs (`kind U`) as hosts.  On a
wide rail every IC ties on net specificity, so the tie-break picked whichever
controller happened to be closest: `5C1` (10 u on `VIN_SYS`) was assigned to
`3U1`, even though it bypasses the output converter at `5Q1`.  The force could
not pull a bypass cap to the FET it actually serves.

**What changed:** hosts may be `U` or `Q`; a two-terminal cap to GND on a power
rail is restricted to `Q`/`J` (the switch or connector it bypasses), while a
boot/charge-pump cap between two non-GND nets keeps the IC scoring.  Assignment
is now always computed — `HOST_POWER` gates the *force*, not what the inspector
shows.  A host-pair metric reports every critical part (caps, inductors, power
resistors/shunts, gate resistors) against a target of **6 mm** for a signal
part and **15 mm** for a power-path part.  It is in the UI metrics table and
headless as `make proximity` (`hardware/proximity_report.py`).

**Numbers (fixed5, caps moved next to 5Q1):** `5C1 -> 5Q1` **5.8 / 6 mm** (ok),
`3C2 -> 5Q1` **12.0 / 15** (ok), `3C3 -> 5Q1` **18.8 / 15** (over), `6C3 -> 5Q1`
**25.6 / 6** (over; it is 12.1 mm from `6U3`, so if it is that regulator's input
cap it belongs there), `5C9 -> 5J2` **18.4 / 15**, `4R1 -> 4U1` **42.5 / 15**
(the Kelvin gate's problem), `5L1 -> 5U1` **45.2 / 15**.  The critical set is 45
pairs, 39 over target, mean 13.5 mm — the metric is a screen, not a gate.

**Status:** force assignment fixed; placement work remains for the pairs above.
