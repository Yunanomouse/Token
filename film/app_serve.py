#!/usr/bin/env python3
"""Serve Venture Trader with its own dashboard server, on loopback only.

Usage:  <app-venv>/bin/python film/app_serve.py /path/to/copy-of-openbb-trader [port]
"""
import os, sys, time

if len(sys.argv) < 2:
    sys.exit(__doc__)
APP = os.path.abspath(sys.argv[1]); port = int(sys.argv[2]) if len(sys.argv) > 2 else 8090
os.chdir(APP); sys.path.insert(0, APP)
import dashboard_server
if not dashboard_server.start_dashboard_server('127.0.0.1', port):
    sys.exit('the dashboard server did not start')
print(f'Venture Trader on http://127.0.0.1:{port}/  (Ctrl-C to stop)', flush=True)
while True:
    time.sleep(3600)
