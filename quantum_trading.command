#!/bin/bash
# macOS: double-click in Finder. First time: right-click > Open (unsigned).
cd "$(dirname "$0")"
echo "Quantum Trading launcher"
echo "Folder: $(pwd)"
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer was not found. Install it from https://www.python.org/downloads/macos/"
  echo "then double-click this file again."
  read -r -p "press Enter to close"
  exit 1
fi
echo "Using: $PY ($($PY --version))"
"$PY" launch.py
echo "The dashboard has stopped."
read -r -p "press Enter to close"
