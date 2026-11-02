#!/bin/bash
# Builds dist/ma2-panel-win.zip: embeddable Python 3.12 + Windows wheels + the app. Needs internet once, nothing on the target PC.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=dist/ma2-panel-win/ma2-panel
PYV=3.12.10
CACHE=dist/cache
rm -rf dist/ma2-panel-win && mkdir -p "$OUT" "$CACHE"
ZIP="$CACHE/python-$PYV-embed-amd64.zip"
[ -f "$ZIP" ] || curl -fsSL -o "$ZIP" "https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip"
shasum -a 256 "$ZIP"
mkdir "$OUT/python" && unzip -q "$ZIP" -d "$OUT/python"
printf 'python312.zip\r\n.\r\n..\r\n..\\lib\r\nimport site\r\n' > "$OUT/python/python312._pth"
printf 'fastapi==0.143.3\nuvicorn==0.54.0\nwebsockets==17.2\nstarlette==1.8.0\npydantic==2.14.1\npydantic-core==2.50.1\nanyio==4.15.1\nh11==0.16.0\nclick==8.5.0\nidna==3.20\nannotated-doc==0.0.5\nannotated-types==0.8.0\ntyping-extensions==4.16.0\ntyping-inspection==0.4.4\nopentelemetry-api==1.45.1\n' > "$CACHE/req.txt"
uv pip install --target "$OUT/lib" --python-platform windows --python-version 3.12 --no-deps -r "$CACHE/req.txt"
rm -rf "$OUT/lib/bin"
cp ./*.py secret.env.example "$OUT/"
# Only public templates are shipped; never read this machine's site settings.
cp settings.example.json "$OUT/settings.json"
cp config.example.json "$OUT/config.json"
cp -R static "$OUT/static"
cp win/*.bat "$OUT/"
VERSION="$(date +%Y-%m-%d_%H%M) $(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
[ -z "$(git status --porcelain 2>/dev/null)" ] || VERSION="${VERSION}+dirty"
printf '%s\n' "$VERSION" > "$OUT/VERSION"
mkdir "$OUT/docs" && cp docs/hall-test-plan.md docs/outgoing-commands.md docs/ma2-syntax.md "$OUT/docs/"
cp README.md "$OUT/README-RU.md"
cp CHANGELOG.md "$OUT/"
cp docs/SETUP.md docs/USAGE.md docs/RELEASE-3.0.md docs/update-usb.txt docs/spec.md docs/CODEMAP.md docs/code-index.md "$OUT/docs/"
mkdir -p "$OUT/docs/archive" "$OUT/docs/superpowers/specs"
cp docs/superpowers/specs/2026-10-30-tablet-ui-design.md "$OUT/docs/superpowers/specs/"
cp docs/archive/spec-history.md "$OUT/docs/archive/"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
(cd dist/ma2-panel-win && rm -f ../ma2-panel-win.zip && zip -qr ../ma2-panel-win.zip ma2-panel)
ls -la dist/ma2-panel-win.zip
# USB update: only program files; config.json, settings.json, secret.env and shows/ on the PC stay untouched
bash scripts/serve_update.sh --build-only
rm -rf dist/usb && mkdir -p dist/usb/ma2-panel-update
cp dist/update/ma2-panel-update.zip dist/update/ma2-panel-update.zip.sha256 update.py win/update-usb.bat docs/update-usb.txt dist/usb/ma2-panel-update/
(cd dist/usb && rm -f ../ma2-panel-update-usb.zip && zip -qr ../ma2-panel-update-usb.zip ma2-panel-update)
ls -la dist/ma2-panel-update-usb.zip
