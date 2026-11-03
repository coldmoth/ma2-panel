#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/package_release.py
[ "${1:-}" = "--build-only" ] && exit 0
for interface in en0 en1; do
    address=$(ipconfig getifaddr "$interface" 2>/dev/null || true)
    if [ -n "$address" ]; then
        echo "Mac: $address"
        echo "На Windows: python\\python.exe update.py http://$address:8765/ma2-panel-update.zip"
    fi
done
python3 -m http.server 8765 --bind 0.0.0.0 --directory dist/update
