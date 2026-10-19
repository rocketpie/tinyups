# 0015 – Power gate: copper and component terminals

- Status: accepted

## Decision

`make power` separates two limits that were conflated:

1. **Copper** (traces and pour corridors) is sized by IPC-2221 (2 oz outer,
   10 °C rise) and is a hard fail.
2. **Component terminals** (fuse blade, shunt leadframe, FET pins) are sized
   from the datasheet. `power_spec.PART_TERMINAL_A` maps
   `(footprint, value/MPN)` to a rating, a basis and a datasheet URL. A known
   rating below the net current is a hard fail; an unknown part is printed as
   `unrated` with the conservative pad estimate and does not fail.
3. Same-net pads inside one footprint are added (a Power56 source is three
   pins, not one) as the fallback for an unrated part. The pour is measured on
   its **outline**; the filled polygon's pad neck is the terminal, not a trace.
   The filled width is printed as a `fill` warning.
4. The report prints **copper** and **terminal** as separate columns, so a
   failure names the binding limit.

Rating basis: the datasheet continuous drain current at `T_A = 100 °C` with the
manufacturer's 650 mm² 2 oz land (the conservative end of the range); the fuse
from its 25 A rating and the shunts from `P = I²R` at 2 W. A full thermal check
(NFR-3) remains a separate test.

## Consequences

- A verified design can pass `make check`; an undersized known terminal still
  fails. An unselected part is visible as `unrated`, not silently passed or
  failed.
- The MPN must be the board value (or a field the table keys on) for a part to
  be rated.
- The `fill` warning conflates a pad neck (covered by the terminal) with a real
  pour split; the latter is a placement/channel issue (`make channels`) and a
  DRC issue, not a terminal rating.
- Requirements: FR-1, FR-5, NFR-3, NFR-7, NFR-9. History: 0007, 0019, 0020.
