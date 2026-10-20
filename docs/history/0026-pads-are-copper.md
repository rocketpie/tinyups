# 0026 – the power gates read pad centres as holes

**What:** two gate bugs made a good pour look split and capped `N_PACKMID` no
matter where the FETs sat.

- `power_report.pour_width()` required every pad **centre** inside the filled
  polygon.  KiCad's fill stops at the pad edge (the pad is its own copper), so a
  multi-pin land could never be fully inside: `N_CS` read 0.00 mm ("pour split")
  and `SW1_OUT` 0.00 mm, while the copper was continuous.  A pad now counts as
  connected when the eroded fill reaches its land.
- `power_channel.py` required each pad centre to clear every obstacle by `w/2`.
  A Power56 source pin is 0.6 mm from its own drain tab, so `N_PACKMID` was
  pinned at **1.5 / 7.5 mm** however far the two sources moved (verified at
  4, 5, 6, 7, 8 mm).  Worse, pads that fell inside an obstacle were silently
  dropped (`lab == 0`), which hid IC pins entirely.  The gate now measures the
  **series parts** only (`power_report.series_parts()`) and a pad is reachable
  when the channel comes within `w/2` of its land.

**Numbers:** `power_channel` on fixed5: `N_PACKMID` 2.4 → **8.8 mm**, all **16**
rails `ok` (was 1 short); `power_report` high-current rails **16/16 PASS**, the
remaining 6/22 are unrouted signal nets (`CELL4`, `N_VCAP`, `+3V3`, `VCC`,
`REGN`, `VDDA`) with no copper yet.  `N_CS`/`SW1_OUT` fill warnings are 0.70 /
0.67 mm — pad necks, covered by the terminal rating (ADR-0015), not splits.
`4Q1` moved 6 mm away from `4Q2` per the TODO; placement DRC 0 courtyard /
0 clearance / 0 short, channels 0 short.

**Status:** fixed. The gate now agrees with the copper; the route is the next
gate. Open: the pour reaches the series pads only, so a tap pad on the same net
is left unrouted by freerouting ([0027](0027-pour-taps.md)). Details of the
placement: [`docs/progress.md`](../progress.md).
