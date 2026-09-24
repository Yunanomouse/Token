#!/bin/bash
# macOS marks everything unzipped from a download as quarantined, and blocks
# the unsigned program and the libraries beside it.  Clear that for this
# folder only, then start the app in this window.
cd "$(dirname "$0")" || exit 1
xattr -dr com.apple.quarantine . 2>/dev/null
exec "./Quantum Trading"
