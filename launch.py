#!/usr/bin/env python3
"""Double-click entry point for the Quantum Trading dashboard.

Starts the local server, opens the dashboard in your default browser, and
keeps running until this window is closed.  Paper trading only.

The same file is the entry point of the standalone app built by
packaging/build.py, where Python and numpy are bundled.  There, with
arguments it runs the command line instead (``Quantum Trading live ...``,
``Quantum Trading backtest ...``: the same subcommands as
``python -m quantum``).
"""
import os
import subprocess
import sys

FROZEN = getattr(sys, "frozen", False)  # the standalone app
# The folder holding data/ and the saved state: next to the app, or this file.
HERE = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
os.chdir(HERE)
if not FROZEN:
    sys.path.insert(0, HERE)

if FROZEN and len(sys.argv) > 1:
    from quantum.cli import main as cli_main
    sys.exit(cli_main(sys.argv[1:]))

if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; this is {sys.version.split()[0]}.")
    print("Install it from https://www.python.org/downloads/ and run this again.")
    input("press Enter to close")
    sys.exit(1)

try:
    import numpy  # noqa: F401  (always present in the standalone app)
except ImportError:
    print("The dashboard needs the numpy package, which is not installed.")
    answer = input("Install it now with pip? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        code = subprocess.call([sys.executable, "-m", "pip", "install", "numpy"])
        if code != 0:
            print("pip could not install numpy. Run:  python -m pip install numpy")
            input("press Enter to close")
            sys.exit(1)
    else:
        print("Run:  python -m pip install numpy   and start this again.")
        input("press Enter to close")
        sys.exit(1)

from quantum.desktop import serve  # noqa: E402

if __name__ == "__main__":
    try:
        serve()
    except OSError as exc:
        print(f"could not start the dashboard: {exc}")
        print("If port 8765 is busy, run:  python -m quantum desktop --port 8800")
        input("press Enter to close")
        sys.exit(1)
