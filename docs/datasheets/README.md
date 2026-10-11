# Datasheet & source register

Project rule: **no component without a manufacturer + part number + source
link.** This file lists the source for every selected part. Datasheet PDFs are
stored in this folder (or vendor URLs kept here if a local copy is not yet
filed).

## Required sources

| Component | Part | Vendor | Source | Filed locally |
| --- | --- | --- | --- | --- |
| LiFePO₄ cell | Topband 33138-HE, 15 Ah | Topband | vendor spec + in-house measurement (ADR-0007) — no datasheet | n/a |
| Input front-end | LM5069 | Texas Instruments | https://www.ti.com/product/LM5069 | no |
| Ideal diode (pack path) | LM74700-Q1 | Texas Instruments | https://www.ti.com/product/LM74700-Q1 | no |
| Charger | BQ25720 | Texas Instruments | https://www.ti.com/product/BQ25720 | no |
| Output converter | LM5176 | Texas Instruments | https://www.ti.com/product/LM5176 | no |
| Battery AFE | BQ76942 | Texas Instruments | https://www.ti.com/product/BQ76942 | no |
| MCU | RP2040 | Raspberry Pi | https://www.raspberrypi.com/products/rp2040/ | no |
| Reference design | PMP21278 | Texas Instruments | https://www.ti.com/tool/PMP21278 | no |
| Input connector | XT60, 2-pin | Amass | verify part page (XT60-M / XT60-F) | no |
| Output connector | XT30, 2-pin | Amass | verify part page | no |
| Output adapter | 5.5 × 2.5 mm barrel plug | (e.g. Switchcraft/Cliff) | verify part page | no |
| Fan | 80 mm, 4-pin PWM | (e.g. Noctua/Arctic) | verify part page | no |

## How to file a datasheet

1. Download the vendor PDF.
2. Save it as `docs/datasheets/<vendor>-<part>.pdf`
   (e.g. `ti-lm5176.pdf`).
3. Add a row above with the local filename in the "Filed locally" column.

Keep the register in sync with the BOM: a part may not enter
`hardware/tinyups.kicad_sch` before it appears here.
