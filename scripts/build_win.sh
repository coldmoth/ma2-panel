#!/bin/bash
# Builds dist/ma2-panel-win.zip: embeddable Python 3.12 + Windows wheels + the app. Needs internet once, nothing on the target PC.
set -euo pipefail
cd "$(dirname "$0")/.."
BUNDLE=dist/ma2-panel-win/ma2-panel
OUT="$BUNDLE/program"
PYV=3.12.10
CACHE=dist/cache
rm -rf dist/ma2-panel-win && mkdir -p "$OUT" "$CACHE"
ZIP="$CACHE/python-$PYV-embed-amd64.zip"
[ -f "$ZIP" ] || curl -fsSL -o "$ZIP" "https://www.python.org/ftp/python/$PYV/python-$PYV-embed-amd64.zip"
shasum -a 256 "$ZIP"
mkdir "$OUT/python" && unzip -q "$ZIP" -d "$OUT/python"
printf 'python312.zip\r\n.\r\n..\r\n..\\lib\r\nimport site\r\n' > "$OUT/python/python312._pth"
uv export --locked --no-dev --no-emit-project --no-hashes --output-file "$CACHE/req.txt" > /dev/null
uv pip install --target "$OUT/lib" --python-platform windows --python-version 3.12 --no-deps --requirement "$CACHE/req.txt"
rm -rf "$OUT/lib/bin"
# Generate the program tree and update ZIP together, with exactly one identity.
python3 scripts/package_release.py --tree "$OUT"
cp secret.env.example "$OUT/"
cp settings.example.json "$OUT/settings.json"
cp config.example.json "$OUT/config.json"
python3 -c 'import release, sys; release.write_windows_launcher(sys.argv[1])' "$BUNDLE"
find "$OUT" -name __pycache__ -prune -exec rm -rf {} +
(cd dist/ma2-panel-win && rm -f ../ma2-panel-win.zip && zip -qr ../ma2-panel-win.zip ma2-panel)
ls -la dist/ma2-panel-win.zip
# USB update: only program files; config.json, settings.json, secret.env and shows/ on the PC stay untouched
rm -rf dist/usb && mkdir -p dist/usb/ma2-panel-update
cp dist/update/ma2-panel-update.zip dist/update/ma2-panel-update.zip.sha256 update.py release.py win/update-usb.bat docs/update-usb.txt dist/usb/ma2-panel-update/
(cd dist/usb && rm -f ../ma2-panel-update-usb.zip && zip -qr ../ma2-panel-update-usb.zip ma2-panel-update)
ls -la dist/ma2-panel-update-usb.zip
