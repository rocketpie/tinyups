# TinyUPS

like a laptop battery, but for PCs

## Documentation

- [Design goals / requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Test plan](docs/test-plan.md)
- [Toolchain status](docs/toolchain.md)
- [Decision records](docs/decisions/)

## Toolchain

Everything runs inside the dev container (see [`.devcontainer/`](.devcontainer/)).
The agent drives the tools headlessly through the [Makefile](Makefile).

| Tool | Purpose |
| --- | --- |
| KiCad 9 + `kicad-cli` | Schematic, layout, ERC, DRC, fabrication exports |
| KiBot | CI-grade automation for the checks above |
| ngspice + PySpice | Circuit simulation |
| KiUtils | Programmatic access to KiCad files |
| pytest / PyVISA / PyMeasure | Automated bring-up and acceptance tests |
| sigrok-cli | Logic analyzer captures |

Common commands:

```sh
make erc        # schematic electrical rule check
make drc        # pcb design rule check
make gerbers    # fabrication outputs
make bom        # bill of materials
make sim        # SPICE simulations
make check      # everything above (used by CI)
```

## Development container

The container installs the full EDA toolchain at build time.
For a GUI KiCad session in the browser, enable the commented
`desktop-lite` feature in `.devcontainer/devcontainer.json` (noVNC).
