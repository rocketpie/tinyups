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
# kicad-libraries bundles symbols, footprints and 3D models (~1 GB).
RUN apt-get update \
    && apt-get install -y \
        python3 python3-pip python3-venv pipx python3-wxgtk4.0 \
        ngspice \
        sigrok-cli \
        kicad kicad-libraries \
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
        kibot

# Put the EDA venv and KiCad CLI on the PATH for everyone.
ENV PATH="/opt/eda/venv/bin:${PATH}"
