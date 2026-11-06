# Repository structure

The backend is a single `ma2panel` package. This change moves code and resources;
it does not change MA2 commands, safety rules, the UI or HTTP/WebSocket contracts.

```text
.github/                 CI and Windows acceptance workflow
ma2panel/                backend modules, __main__.py and source VERSION
  resources/             public configuration templates
    mock/                the three fixtures needed by the mock at runtime
static/                  existing HTML, CSS and JavaScript
scripts/                 development, smoke and release tools
  win/                   BAT templates copied to program/ during packaging
  relay/                 separate diagnostics service
tests/                  Python and Node regression tests
docs/                    user guides, engineering docs, changelog and design notes
bridge.py                stable launcher; recovery runs before backend imports
README.md                English download-first page
LICENSE
pyproject.toml
uv.lock
.python-version
.gitignore
```

There were **45** tracked entries at the root of public `main` (`a1ccfae`). There
are now **13**, including the three hidden entries. The extra launcher is kept
for compatibility; the Python version pin and dependency lock keep builds stable.
The duplicate source-root BAT is replaced by the maintained `scripts/win/start.bat`
template. Both delivered `ma2-panel/start.bat` and `program/start.bat` are retained.
No `MA2 Panel.exe` existed in the published v3.2.0 ZIP.

## Source development

Use Python 3.12+ and `uv sync --locked`. For a new source installation only, copy
`ma2panel/resources/config.example.json` and `settings.example.json` to the working
root as `config.json` and `settings.json`. Do not overwrite existing data.

Launch with `uv run python bridge.py` or `uv run python -m ma2panel`. Both use the
working root beside `bridge.py` for settings, secrets, logs, PID, updates and data;
they do not depend on the shell's current directory. Add `--mock` for a simulated
console. As before, a normal launch can connect to MA2.

Backend imports are `from ma2panel import bridge` / `from ma2panel.commands import …`.
Use `uv run python -m ma2panel.selfcheck URL` for source diagnostics. Repository
tools that import the package run as modules, e.g.:

```sh
uv run python -m scripts.build_windows --verify-reproducible
uv run python -m scripts.package_release
uv run python -m scripts.command_map
uv run python -m scripts.setup_diagnostic_relay
```

The shell wrappers `scripts/build_win.sh` and `scripts/serve_update.sh` remain.
The relay service's new application path is `scripts.relay.app:configured_app`;
update its systemd unit when deploying source from this branch.

## Delivered layout and update compatibility

The full ZIP retains its outer `start.bat` and `program/` with embedded Python,
`lib/`, templates installed as initial working settings, static files and BAT tools.
`program/ma2panel/` contains the backend and its mock resources. The payload is
shared by full, USB and LAN builds, with the same manifest and hashes.

Standalone stdlib copies of `update.py`, `release.py` and `browser_update.py`
are emitted beside the launcher for the existing BAT interfaces and detached
workers. Their source of truth is the package. The detached updater loads its
staged validator explicitly; it never borrows one from the installed program.
Recovery remains `.updates/recovery.py`, independent of the replaceable package.

**Migration boundary:** the v3.2.0 in-app/LAN updater rejects `ma2panel/` as an
invalid location. It cannot install this layout directly, and fails validation
before replacing the program. Do not publish this ZIP as a routine in-app update
for v3.2.0. Use the **new external USB kit** (`ma2-panel-update-usb.zip`) with its
`update-usb.bat`, selecting the existing `program` directory, or a separate full
installation with an explicit data migration. Never copy new updater modules
into the old installation by hand. The new updater continues to accept the old
flat payload and supports rollback to the previous flat installation.

The unchanged dependency lock permits the external USB transition with the old
embedded runtime. An incompatible runtime remains a full-installation case.
Keep config/settings, secrets, shows, presets in the show plan, backups,
diagnostics, RDM state and `.updates/` intact. Never update during live control.

## Acceptance and merge gates

The bounded `repository-structure.yml` workflow builds twice independently and
compares the three ZIPs, extracts the actual full ZIP, runs embedded Python x64,
checks BAT exit codes and Unicode paths, and checks update/rollback with data
preservation. It also downloads the immutable published v3.2.0 Windows ZIP with
a pinned SHA256 and exercises legacy rejection, external USB migration and rollback.
A separate delivered-runtime smoke checks both HTTP/WS listeners, assets, mock
login, action replies and shutdown. It never connects to MA2.

Before merging, obtain independent review of import/resource paths and the updater
transition. Before a release, make an explicit decision about the v3.2.0 migration
boundary above. Mock/CI are not physical MA2 acceptance; an operator must still
check the target Windows laptop, real console connection and existing show.
