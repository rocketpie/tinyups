# 0001 – Tooling and workflow for PCB design

- Status: accepted

## Context

TinyUPS is to be documented, designed, given a component selection and
validated. The agent works in a dev container and should use as many tools as
possible headlessly and reproducibly.

## Decision

1. **EDA core: KiCad 9 + `kicad-cli`/KiBot (hybrid).**
   KiCad for schematic/layout; all checks and exports headless via
   `kicad-cli` and KiBot. Formats are text-based and git-friendly.
2. **Simulation: ngspice (optionally via PySpice).**
   For the power path, converters and protection circuits ahead of layout.
3. **Compute unit: MCU with telemetry.**
   Behaviour is observable and testable independently of the host.
4. **Goal: DC UPS for a PC**, output ~12 V.
5. **Test: `pytest` + PyVISA/PyMeasure + sigrok-cli** for automated bring-up
   and acceptance tests.
6. **Everything in the repo**: schematic, layout, BOM, Gerber, tests, docs.
   Checks as `make` targets, identical in CI (GitHub Actions).

## Consequences

- GUI KiCad is optional (noVNC feature) and not required for the workflow.
- The agent can run ERC/DRC/exports itself and iterate.
- The running container must contain the tools; changes to the `Dockerfile`
  only take effect on the next rebuild.
