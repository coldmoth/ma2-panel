# Install or update ma2-panel on Windows

**[Stable Windows download](https://github.com/coldmoth/ma2-panel/releases/latest/download/ma2-panel-win.zip)** · **[v3.3.1 RC1 for supervised testing](https://github.com/coldmoth/ma2-panel/releases/tag/v3.3.1-rc.1)**

RC1 is a prerelease built from commit `6ff3df5c89fef26cc85e47f2699f0227e8a47ef7`. Its Windows CI passed; final acceptance with physical grandMA2 and real fixtures is still pending. Stable remains v3.3.0. The application interface is currently in Russian.

## Before you start

Use Windows 10/11 x64, grandMA2 onPC 3.9 and a modern browser such as Chrome or Edge. The full Windows ZIP includes Python 3.12.10 x64 and dependencies. No separate Python installation is required.

Stop the existing bridge and copy its entire installation folder to a separate backup before installing or updating. Back up the MA2 show separately through grandMA2. Keep the original v3.3.0 installation and its data until testing is complete. Do not run the old and new bridges together.

## Install RC1 in a separate folder

1. From the [RC1 release](https://github.com/coldmoth/ma2-panel/releases/tag/v3.3.1-rc.1), download `ma2-panel-win.zip` and its `.sha256`. The GitHub Source code archives do not contain the Windows runtime.
2. Verify SHA256, then use Extract All. Keep the entire `ma2-panel` folder, including the outer `start.bat` and `program`, in a writable location outside Program Files, OneDrive and any existing installation.
3. For the first offline check, leave onPC closed and run `program/start-mock.bat`. This uses simulated fixtures. Stop mock mode before any normal launch.
4. To retain an existing venue, follow the data transfer instructions below while both bridges are stopped.
5. For a supervised real connection, prepare a dedicated grandMA2 user with a separate User Profile and enable Telnet Remote inside grandMA2. Double-click the outer `start.bat` and follow the setup wizard at [localhost:8080/setup.html](http://localhost:8080/setup.html). The wizard saves connection details; it does not create the MA2 account or enable Telnet.

Default addresses: full panel [127.0.0.1:8080](http://127.0.0.1:8080), simple scene view [127.0.0.1:8090](http://127.0.0.1:8090). A fresh plan is empty and permissions are restricted. There is no separate MA2 Panel.exe.

## Preserve data when using a separate full installation

After stopping both bridges, copy your existing data into the new `program` directory: `config.json`, `settings.json`, `secret.env`, `highlight.json`, `shows/`, `diag/`, `diagnostic-upload.json`, `field-data/`, `rdm-search.json`, `blackout.json`, `scene-write-*.json` and `update_url.txt`, where present. Preserve backups and logs as well. Never replace your own configuration with public templates.

Copy pending-operation journals byte for byte, including damaged or unknown RDM state and the original target. Do not edit or delete journals to dismiss warnings. Retain newer and older unknown states separately for operator review; copying a file does not confirm RDM Off.

Keep `runtime.json`, `runtime-files.json`, Python and `lib` together from the new full package. Do not copy old runtime files over them. Older installations without runtime identity files require a separate full installation rather than the update ZIP.

## Update an existing v3.3.0 installation

RC1 is installed manually. The stable updater does not offer prereleases automatically.

The recommended manual route is the [external USB kit](update-usb.txt): download `ma2-panel-update-usb.zip` from RC1, extract it outside the installation, stop the bridge, run the extracted `update-usb.bat` and select the existing `program` directory.

The regular `ma2-panel-update.zip` is for the compatible local ZIP-upload update flow. In Settings, open the local update page, select the downloaded RC1 update ZIP and confirm the displayed version. Keep the package ZIP intact. If runtime validation refuses the update, retain the refusal and use a separate full installation; do not bypass validation. Versions v3.2.0–v3.2.4 require the new external USB kit instead of their old in-app updater.

The updater preserves user data, creates a pre-update backup and retains a program snapshot for rollback. Keep your own full-folder backup too. After updating, verify the version is `3.3.1+6ff3df5`, then check settings, venue plan and shows before supervised fixture tests.

## Roll back

If you used a separate RC folder, stop RC1 and launch the untouched v3.3.0 installation. Retain any newer RC data separately.

If you updated v3.3.0 in place, stop the panel and run `program/rollback.bat`. This restores the previous program, including removal of files introduced by the update. Do not delete `previous/` or `.updates/`: they contain the snapshot and recovery journal. Automatic rollback preserves current user data rather than replacing it with the old backup. Before any manual data restore, save the entire current installation and have the operator review pending-operation state.

The [stable v3.3.0 release](https://github.com/coldmoth/ma2-panel/releases/tag/v3.3.0) remains available.

## Stop and check the installation

Press Ctrl+C in the launcher or run `program/stop.bat`. Stopping the bridge does not turn off lighting or scenes already running in MA2; check their state on the console.

After changing the installation path or ports, run `program/firewall-open.bat` as administrator if LAN/tablet access is needed. Use a trusted local network.

With the bridge running, `program/selfcheck.bat` checks the main port by default; specify `--port` if needed. A software check is not confirmation of physical light output.

[First connection](FIRST-CONNECTION.md) · [Tablet connection](TABLET.md) · [User guide](USAGE.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Source installation and mock mode](ADVANCED.md) · [Hardware acceptance plan](hall-test-plan.md)
