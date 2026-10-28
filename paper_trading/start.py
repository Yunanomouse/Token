#!/usr/bin/env python3
"""Run Paper Trading from these source files (the installed program,
Paper Trading Setup.exe, needs none of this).

Opens Paper Trading in its own window (window.py) and keeps running until
the window is closed.  PRETEND MONEY ONLY: no broker is connected, no keys
are read, and the only thing sent over the internet is a stock symbol when
you ask for a price.  Needs Python 3.10+, tzdata on Windows, and pywebview
for the window (without it the page opens in the browser).  See README.md.
"""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

def ask(prompt: str, no_keyboard: str = "") -> str:
    """input(), or ``no_keyboard`` when there is none (started from another program)."""
    try:
        return input(prompt)
    except EOFError:
        return no_keyboard


if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; this is {sys.version.split()[0]}.")
    print("Install it from https://www.python.org/downloads/ and run this again.")
    ask("press Enter to close")
    sys.exit(1)

# tzdata on Windows, whose Python has no time-zone database of its own (New
# York time decides when the market is open).  Nothing else is needed.
NEEDED = ["tzdata"] if sys.platform.startswith("win") else []


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
    print(f"Paper Trading needs these Python packages: {', '.join(need)}")
    answer = ask("Install them now with pip? [Y/n] ", no_keyboard="n").strip().lower()
    if answer not in ("", "y", "yes") or subprocess.call([sys.executable, "-m", "pip", "install", *need]) != 0:
        print(f"Run:  python -m pip install {' '.join(need)}   and start this again.")
        ask("press Enter to close")
        sys.exit(1)
    if missing():
        print("The packages were installed but still cannot be loaded; restart this window.")
        ask("press Enter to close")
        sys.exit(1)

if importlib.util.find_spec("webview") is None:  # pywebview draws the program window
    print("Paper Trading opens in its own window with the pywebview package (not installed).")
    if ask("Install it now with pip? Otherwise it opens in your browser. [Y/n] ",
           no_keyboard="n").strip().lower() in ("", "y", "yes"):
        if subprocess.call([sys.executable, "-m", "pip", "install", "pywebview>=5,<7"]) != 0:
            print("That didn't work; opening in the browser instead.")

from window import main  # noqa: E402

if __name__ == "__main__":
    code = main(sys.argv[1:])
    if code:
        ask("press Enter to close")
    sys.exit(code)
