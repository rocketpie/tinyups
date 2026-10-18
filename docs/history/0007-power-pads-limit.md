# 0007 – The power path's pads limit it, not the copper

**What:** with series-aware sizing (`power_report.series_parts()`, from the
graph's thick edges) and F.Cu pours swept along the **series** pads only, the
copper geometry works — `SW1`'s neck reaches 10.3 A against 8 A. Counting the
**pad**, every rail still fails:

| net | need | narrowest series pad | at 2 oz |
| --- | --- | --- | --- |
| `+12V_IN` | 20 A | 1.25 mm — `1F1`, `Fuse_1206_3216Metric` | 4.6 A |
| `N_AF` | 20 A | 1.23 mm — `1R1`, `R_2512_6332Metric` | 4.6 A |
| `VIN_SYS`, `VBAT`, `VOUT12`, `SW*_OUT` | 17–20 A | 1.20 mm — TO-252-2 lead | 4.5 A |
| `VSYS`, `SW1`, `SW2` | 8 A | 1.20 mm — TO-252-2 lead | 4.5 A |

**Why it matters:** no pour, placement or route carries 20 A through a 1.2 mm
terminal — the same defect class as the undersized power traces of ADR-0008, one
level deeper. `docs/bom.md` already flags the fuse.

**Caveat:** IPC-2221 sizes *traces*; a device terminal is limited by its
datasheet and its copper heatsinking, so 4.5 A is conservative. The terminals in
the path are nevertheless too small for 20 A.

**Status:** open — needs a 20 A fuse and shunt, and packages with a wide source
terminal (or devices in parallel).
