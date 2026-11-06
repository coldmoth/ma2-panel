# Advanced installation and development

For normal Windows installation, use the [packaged download](SETUP.md). This page covers source installations, local diagnostics and data recovery. These procedures do not replace real grandMA2 acceptance.

## Install from source

Use Git, Python **3.12+ x64** and [uv](https://docs.astral.sh/uv/getting-started/installation/). Windows is the documented target platform for onPC operation. The source archive does not include Python or dependencies.

For a **new folder**, run in PowerShell:

```powershell
git clone --branch v3.2.0 --depth 1 https://github.com/coldmoth/ma2-panel.git ma2-panel-3.2
cd ma2-panel-3.2
uv sync --locked --no-dev
Copy-Item config.example.json config.json
Copy-Item settings.example.json settings.json
uv run --no-sync python bridge.py --open-browser
```

The initial dependency installation needs internet access. Afterward, `uv run --no-sync` uses the installed environment. Do not copy example files over existing settings or shows. The Windows BAT launcher expects the embedded runtime; use the Python command for a source installation.

Follow [First connection](FIRST-CONNECTION.md). The password can be saved through the wizard to `secret.env` beside `settings.json`; copying `secret.env.example` is optional. When a source process exits with code 3 after a settings restart, run the launch command again.

Source-installation data paths are relative to the repository root. Packaged-installation paths below are relative to `program`.

## Mock mode

Use a separate installation or copies of configuration and settings, with isolated show/export directories and unused ports. Start `program/start-mock.bat` in the Windows package, or run:

```powershell
uv run --no-sync python bridge.py --mock
```

Mock replaces the MA2 connection with a marked simulation. It does not verify real console behavior. The starter venue plan is empty. Stop mock before starting a real connection.

## Back up and move an existing installation

For **3.2.0**, install the full Windows package in a separate folder. No compatible update ZIP is published for this release; the runtime lock identity changed. Do not use USB or browser updates to move an older runtime to 3.2.0, and do not update during lighting operation.

1. Save the real show in MA2. Stop the old bridge.
2. Back up the **entire old installation folder** before copying anything.
3. In the new installation's `program` folder, transfer your own `config.json`, `settings.json`, `secret.env`, `highlight.json`, `shows/`, `diag/`, `diagnostic-upload.json`, `field-data/`, `rdm-search.json` and `update_url.txt`, where present. Preserve old backups and logs separately. Never replace user data with public examples.
4. Keep `rdm-search.json` intact, including a pending, corrupt or unknown target. Copying it does not confirm RDM is off. Do not edit or delete it to clear a warning.
5. Keep Python, `lib`, `runtime.json` and `runtime-files.json` from the **same new package**. Do not mix runtimes between installations.
6. Restart only one bridge, confirm its settings, and repeat the supervised connection checks. After changing the path or ports, run `program/firewall-open.bat` as administrator for your trusted private network.

The local plan (`config.json` and `shows/`) is separate from the real MA2 show file. Keep backups of both. Automatic configuration backups are under `backups/`.

## Interrupted update recovery

This applies to an existing installation with an interrupted update, rather than the normal 3.2.0 installation path.

Keep `backups/`, `previous/` and `.updates/` until recovery is verified. Do not copy templates over user files. If an update stopped the bridge before restarting it, run the outer `start.bat`; the embedded launcher checks for recovery first.

If the inner BAT file is missing and automatic recovery cannot start, stop the bridge and back up the current folder. In the `program` folder, use PowerShell:

```powershell
.\python\python.exe .updates\recovery.py --recover .
```

Run `start.bat` after successful recovery. For older installations with a different layout, run from the directory containing `python` and `.updates`. Preserve both copies of any newer or uncertain RDM state rather than replacing it with an older backup; have the operator check them. The legacy [USB recovery reference (Russian)](update-usb.txt) describes older update packages, not a published 3.2.0 update asset.

## Local diagnostics

With the bridge running, open `program/selfcheck.bat`. It checks the main port, **8080**, by default. For a custom port, pass its main-panel URL:

```powershell
.\selfcheck.bat http://127.0.0.1:8180
```

From source, use `uv run --no-sync python selfcheck.py http://127.0.0.1:8180`. The simple view has no diagnostics API. `selfcheck-report.txt` is written beside the script. Exit code 0 means all checks passed; 1 means a negative check, a check failure or a report-write failure. Action checks run only in test mode. The BAT returns the code after its pause.

## Development

The browser sends actions over WebSocket to a Python/FastAPI bridge, which builds and guards Telnet commands for grandMA2. The frontend uses HTML, CSS and JavaScript without a framework or build step.

Install development dependencies with `uv sync --locked`. Node.js is needed for the JavaScript checks:

```powershell
uv run pytest -q -p no:cacheprovider
node tests/panel-v4.cjs
```

On macOS/Linux, the existing Windows packaging script is `bash scripts/build_win.sh` and requires uv, curl, zip/unzip and internet access. Its outputs require separate Windows validation; building a ZIP is not hardware acceptance. Keep venue configurations, secrets, shows and diagnostics out of Git.
