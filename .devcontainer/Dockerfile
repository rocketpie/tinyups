FROM mcr.microsoft.com/devcontainers/base:ubuntu

# Install OpenCode 2 as the vscode user (installs to ~/.opencode/bin).
USER vscode
RUN curl -fsSL https://opencode.ai/v2/install | bash

# Expose it on the global PATH.
USER root
RUN ln -sf /home/vscode/.opencode/bin/opencode /usr/local/bin/opencode

# ---------------------------------------------------------------------------
# PCB / EDA / simulation / bench-test toolchain
# ---------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive

# KiCad 9 provides `kicad-cli` for headless ERC/DRC/export.
# kicad-libraries = symbols + footprints.  kicad-packages3d = the component 3D
# models (~4.7 GB unpacked) needed by `kicad-cli pcb render` / STEP export with
# bodies — NOT bundled in kicad-libraries.
RUN apt-get update \
    && apt-get install -y \
        python3 python3-pip python3-venv pipx python3-wxgtk4.0 \
        ngspice \
        sigrok-cli \
        kicad kicad-libraries kicad-packages3d \
        default-jre-headless \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Auto-placement PoC (hardware/layout_poc/): graphviz is the classic layout
# toolbox (dot/neato/fdp/sfdp); node runs the JS engines (d3-force, dagre — the
# engine behind mermaid flowcharts — and elkjs, see build/layout/).  On Ubuntu
# the force-directed backends live in a separate plugin package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        graphviz libgvplugin-neato-layout8 \
        nodejs npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# GUI-debugging helpers: xwd + ImageMagick to screenshot the noVNC desktop
# (used to inspect KiCad dialogs during agent sessions). Small, optional.
RUN apt-get update \
    && apt-get install -y --no-install-recommends x11-apps imagemagick \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python tooling: KiCad file automation, SPICE wrappers, bench instruments, tests.
# --system-site-packages lets KiBot use the distro wxPython (python3-wxgtk4.0).
# --no-compile is recommended by KiBot for pip installs.
# pypdf extracts text from vendor datasheet PDFs (offline datasheet checks).
RUN python3 -m venv --system-site-packages /opt/eda/venv \
    && /opt/eda/venv/bin/pip install --no-cache-dir --upgrade pip wheel \
    && /opt/eda/venv/bin/pip install --no-cache-dir --no-compile \
        kiutils \
        pyvisa pyvisa-py pymeasure pyserial python-can \
        pytest pytest-html \
        doorstop \
        lxml \
        pypdf \
        kibot \
        networkx grandalf pydot shapely scipy matplotlib

# Put the EDA venv and KiCad CLI on the PATH for everyone.
ENV PATH="/opt/eda/venv/bin:${PATH}"

# KiCad's stock library-table variables. The GUI sets these itself, but
# headless `kicad-cli` does not, which makes it fail to resolve footprints
# (spurious lib_footprint_issues DRC warnings). Keep in sync with the Makefile.
ENV KICAD9_FOOTPRINT_DIR="/usr/share/kicad/footprints" \
    KICAD9_SYMBOL_DIR="/usr/share/kicad/symbols" \
    KICAD9_3DMODEL_DIR="/usr/share/kicad/3dmodels"

# freerouting: autorouter for the PCB step (KiCad has no built-in one).
# Driven by hardware/route.py; needs the JRE installed above.
RUN mkdir -p /opt/freerouting \
    && curl -fsSL -o /opt/freerouting/freerouting.jar \
       https://github.com/freerouting/freerouting/releases/download/v2.5.0/freerouting-2.5.0.jar
ENV FREEROUTING_JAR=/opt/freerouting/freerouting.jar
