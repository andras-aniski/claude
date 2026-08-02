#!/bin/bash
if ! command -v python3 &>/dev/null; then
    echo "[statusline] python3 not found — install Python 3.8+ to enable the status line"
    exit 0
fi
if ! python3 -c "import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)" 2>/dev/null; then
    ver=$(python3 --version 2>&1)
    echo "[statusline] Python 3.8+ required, found: $ver"
    exit 0
fi
# Resolve the script next to this launcher, so the pair can be copied anywhere
# together without the path being rewritten.
exec python3 "$(dirname "$0")/statusline.py"
