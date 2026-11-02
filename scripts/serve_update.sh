#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist/update
VERSION="$(date +%Y-%m-%d_%H%M) $(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
[ -z "$(git status --porcelain 2>/dev/null)" ] || VERSION="${VERSION}+dirty"
export VERSION
python3 - <<'PY'
import os
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
with ZipFile('dist/update/ma2-panel-update.zip', 'w', ZIP_DEFLATED) as z:
    for name in sorted(p.name for p in Path('.').glob('*.py')):  # every program module in the root
        z.write(name, name)
    for path in Path('static').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            z.write(path, path.as_posix())
    for path in Path('win').glob('*.bat'):
        z.write(path, path.name)
    for name in ('hall-test-plan.md', 'outgoing-commands.md'):
        z.write('docs/' + name, 'docs/' + name)
    z.write('docs/hall-test-plan.md', 'README-RU.md')
    z.writestr('VERSION', os.environ['VERSION'] + '\n')
PY
(cd dist/update && shasum -a 256 ma2-panel-update.zip > ma2-panel-update.zip.sha256)
[ "${1:-}" = "--build-only" ] && exit 0
for interface in en0 en1; do
    address=$(ipconfig getifaddr "$interface" 2>/dev/null || true)
    if [ -n "$address" ]; then
        echo "Mac: $address"
        echo "На Windows: python\\python.exe update.py http://$address:8765/ma2-panel-update.zip"
    fi
done
python3 -m http.server 8765 --bind 0.0.0.0 --directory dist/update
