"""Smoke tests: verify the dev-container toolchain is present and runnable.

These do not need hardware and are safe to run in CI.
"""

import shutil
import subprocess


def _which_version(cmd, *args):
    exe = shutil.which(cmd)
    assert exe, f"{cmd} not found on PATH"
    out = subprocess.run([exe, *args], capture_output=True, text=True)
    assert out.returncode == 0, f"{cmd} {' '.join(args)} failed: {out.stderr}"
    return out.stdout.strip()


def test_kicad_cli_present():
    version = _which_version("kicad-cli", "version")
    assert version.splitlines()[-1].strip()[0].isdigit(), version


def test_kicad_cli_erc_available():
    out = subprocess.run(
        ["kicad-cli", "sch", "erc", "--help"], capture_output=True, text=True
    )
    assert "Electrical Rules Check" in out.stdout


def test_ngspice_present():
    assert shutil.which("ngspice")


def test_sigrok_cli_present():
    assert shutil.which("sigrok-cli")


def test_python_eda_imports():
    import kiutils  # noqa: F401
    import pyvisa  # noqa: F401


def test_kibot_importable():
    import kibot  # noqa: F401
