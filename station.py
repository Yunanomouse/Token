#!/usr/bin/env python3
"""Double-click entry point for Quantum Station: every bot, on this computer.

Starts the station (the bots' scheduler and the dashboard), opens the
dashboard in your default browser, and keeps running until this window is
closed.  Paper trading only.  See docs/station.md.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; this is {sys.version.split()[0]}.")
    print("Install it from https://www.python.org/downloads/ and run this again.")
    input("press Enter to close")
    sys.exit(1)

# numpy for the engine; tzdata on Windows, whose Python has no time-zone
# database of its own (New York time decides when every bot runs).
NEEDED = ["numpy"] + (["tzdata"] if sys.platform.startswith("win") else [])


def missing() -> list[str]:
    out = []
    for mod in NEEDED:
        try:
            __import__(mod)
        except ImportError:
            out.append(mod)
    if "tzdata" not in out:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo("America/New_York")
        except Exception:
            out.append("tzdata")
    return out


need = missing()
if need:
    print(f"Quantum Station needs these Python packages: {', '.join(need)}")
    answer = input("Install them now with pip? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes") or subprocess.call([sys.executable, "-m", "pip", "install", *need]) != 0:
        print(f"Run:  python -m pip install {' '.join(need)}   and start this again.")
        input("press Enter to close")
        sys.exit(1)
    if missing():
        print("The packages were installed but still cannot be loaded; restart this window.")
        input("press Enter to close")
        sys.exit(1)

from quantum.local import main  # noqa: E402

if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        input("press Enter to close")
    sys.exit(code)
