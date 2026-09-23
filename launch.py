#!/usr/bin/env python3
"""Double-click entry point for the Quantum Trading dashboard.

Starts the local server, opens the dashboard in your default browser, and
keeps running until this window is closed.  Paper trading only.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

try:
    import numpy  # noqa: F401
except ImportError:
    print("numpy is required: run  python -m pip install numpy  and try again.")
    input("press Enter to close")
    sys.exit(1)

from quantum.desktop import serve  # noqa: E402

if __name__ == "__main__":
    serve()
