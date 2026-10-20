# 0027 – power pours take a trunk, not a chain through every pad

**What:** the `VIN_SYS` pour walked its series pads in greedy order:
`1Q1 -> 3Q1 -> 3C2 -> 3C3 -> 5Q1 -> 2R1`.  The 470 uF hold-up caps sat on the
20 A trunk, the 10 A charger shunt was its tail, and the `3C3 -> 5Q1` leg
crossed 9 foreign parts.  Multi-pin lands were visited pin by pin, so a Power56
source left two pins as stubs; the pad end was capped at the pad's inscribed
radius, which necked 1J1/1F1 to half a pad and looked spiky at every FET.

**What changed:** each footprint is one terminal now.  Its pads are one land,
the port is the area-weighted pad centre (middle pin / drain tab), and the
corridor is a **trunk with branches**: a branch is a cap/connector to GND or a
part whose other side carries < 75 % of the current (`2R1`, `2R2`).  Branches
attach to the nearest point on the trunk at their own pair current.  The trunk
is greedy nearest from `1J1`, with foreign pads in the corridor priced at 25 mm
per part.  The landing keeps the pour half-width (no pad-radius taper); foreign
pads are cut from the outline so a wide drain tab cannot take the source pins'
space, and a round join is added only on the side the corridor occupies.

**Numbers (fixed5, unrouted):** `VIN_SYS` is `1Q1 -> 3Q1 -> 5Q1`, `2R1` is a
branch at (97,66), the caps sit on 4.5 A branches.  `power_report`
high-current **16/16 PASS**; fill `+12V_IN` 5.48 → **6.01 mm**, `N_AF`
7.06 → **7.44**, `VIN_SYS` 1.11 → **1.35**, `SW2` 0.76 → **1.26**, `VOUT12`
1.58 → **2.72**; `power_channel` **16/16 ok**; DRC 262 unconnected (was 261;
only the tap MST moved), 0 clearance, 0 zone islands.  Open: `5C1` (10 u
bypass) still sits ~47 mm from `5Q1`; `3C2/3C3` are ~49–60 mm away, so moving
the caps is a placement task, not a pour task.
