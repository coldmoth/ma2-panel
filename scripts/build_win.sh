#!/bin/sh
# One cross-platform builder for local USB and GitHub Windows artifacts.
set -eu
cd "$(dirname "$0")/.."
exec python3 scripts/build_windows.py "$@"
