# TinyUPS

like a laptop battery, but for PCs.

A compact 12 V DC UPS for mini servers fed by an external adapter and a
[picoPSU](https://en.wikipedia.org/wiki/PicoPSU) DC-ATX converter. A 4S
LiFePO₄ pack keeps the machine running when mains drops and recharges when it
returns — the whole module fits the ATX PSU bay. Battery status and a clean
shutdown signal go to the host over USB.

## Documentation

- [Design goals / requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Component selection & BOM](docs/bom.md)
- [Schematic (generated)](hardware/README.md)
- [Interactive placement (browser)](ui/placement/README.md)
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
make place      # interactive placement UI (http://localhost:4097)
make route      # route a board with FreeRouting + routing/DRC report
make check      # everything above (used by CI)
```

## Development container

The container installs the full EDA toolchain at build time.
For a GUI KiCad session in the browser, enable the commented
`desktop-lite` feature in `.devcontainer/devcontainer.json` (noVNC).

## Dev Container Setup, Syncing

dev container setup for use with opencode. 
git interaction from host only.

1. say you clone all your repos here:  
`~/workspaces/your-github-slug/repo-name`

2. make another copy where you want your dev containers to live:  
`~/workspaces/containers/repo-name`  
and `rm -rf ~/workspaces/containers/repo-name/.git`  
(`import.sh` copies `.git` back in for read-only history in the container)

3. Add this to your host shell (`~/.bashrc`):

    `export GIT_WORKSPACE_ROOT=~/workspaces/your-github-slug/`


4. from `~/workspaces/containers/repo-name`, run:

|command|what it does|
|---|---|
| `devcontainer up` | build and run the dev container |
| `devcontainer exec opencode pair` | start opencode in the container (open the url to connect via browser) |
| `./import.sh` | sync from GIT_WORKSPACE_ROOT/repo-name to container copy, incl. `.git/` | 
| `./export.sh` | sync from container copy to GIT_WORKSPACE_ROOT/repo-name, never `.git/` | 

Both mirror with `rsync --delete` and skip `node_modules/`. `.git/` travels
one way only: `import.sh` brings it in so the container can read the history
(`git log`, `blame`, `diff` against HEAD), `export.sh` never copies it back, so
commits still happen on the host only.

Then, you can review the changes in `~/workspaces/your-github-slug/repo-name` with VSCode or whatever floats your goat.  
And that's pretty cool!