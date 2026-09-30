#!/usr/bin/env python3
"""Build the standalone Quantum Trading app for the computer this runs on.

    python -m pip install pyinstaller numpy
    python packaging/build.py

Writes dist/quantum-trading-<os>-<arch>/ and a .zip of it.  The folder holds
the program (Python and numpy included, nothing to install), the bundled
price data, and the instructions.  Unzip it anywhere writable and
double-click "Quantum Trading"; the paper book is saved in that folder.

PyInstaller does not cross-compile: build on Windows for Windows, on a Mac
for macOS, on Linux for Linux.  .github/workflows/desktop-app.yml does all
three on GitHub.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Quantum Trading"


def target() -> str:
    osname = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower().replace("amd64", "x64").replace("x86_64", "x64").replace("aarch64", "arm64")
    return f"quantum-trading-{osname}-{arch}"


def main() -> int:
    build, dist = ROOT / "build" / "pyinstaller", ROOT / "dist"
    out = dist / target()
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "launch.py"),
        "--name", NAME, "--onedir", "--console", "--noconfirm", "--clean",
        "--collect-submodules", "quantum",
        "--distpath", str(out.parent / (out.name + ".tmp")), "--workpath", str(build), "--specpath", str(build),
    ], check=True, cwd=ROOT)
    shutil.move(str(out.parent / (out.name + ".tmp") / NAME), str(out))
    shutil.rmtree(out.parent / (out.name + ".tmp"))
    # Data and docs sit next to the program, where the dashboard looks for them.
    for sub in ("prices", "qoblib"):
        shutil.copytree(ROOT / "data" / sub, out / "data" / sub)
    shutil.copy2(ROOT / "data" / "README.md", out / "data" / "README.md")
    shutil.copy2(ROOT / "packaging" / "README.txt", out / "README.txt")
    shutil.copy2(ROOT / "web" / "quantum-trading.html", out / "quantum-trading.html")
    if sys.platform == "darwin":
        helper = out / "Open Quantum Trading.command"
        shutil.copy2(ROOT / "packaging" / "open_macos.command", helper)
        helper.chmod(0o755)
    archive = shutil.make_archive(str(dist / target()), "zip", root_dir=dist, base_dir=target())
    print(f"built {out}\nzipped {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
