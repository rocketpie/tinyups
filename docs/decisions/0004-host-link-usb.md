# 0004 – Host link: USB-C composite CDC + HID Power-Device-Class

- Status: accepted

## Context

Interface D must report battery status and signal the host to shut down cleanly
when the pack runs low. The hosts are x86 mini servers: they have no exposed
GPIO header, so a header-based I²C/UART + GPIO approach is not viable. We want
both the simplest tooling path and the most compatible, "laptop-like" path.

## Decision

- A single **USB-C (Full-Speed, data only)** port on an RP2040 enumerates as a
  **composite device**:
  1. **CDC-ACM** — a line-framed protocol for custom tooling and scripting.
  2. **USB HID Power Device Class (PDC)** — so Linux / Network UPS Tools
     (`usbhid-ups`, `upsmon`) sees a native UPS and performs the low-battery
     shutdown with no custom daemon.
- The USB port is **not** a power source; the module is powered from the pack.
- A future discrete shutdown/FSD line may be added as a hardware backup
  (open item in `requirements.md`).

## Consequences

- Turnkey graceful shutdown on Linux via standard UPS tooling, plus a
  scriptable channel for custom integration.
- The HID-PDC descriptor work is the non-trivial firmware part; CDC is
  mandatory, HID-PDC is the v1 target. The hardware (RP2040 native USB) does
  not block either.
- USB is data-only, so no PD negotiation or charger emulation is needed.
- Related requirements: FR-7, FR-8, FR-10, IF-4, NFR-10.
