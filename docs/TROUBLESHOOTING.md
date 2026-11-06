# Troubleshooting

Start on the Windows computer running the bridge. These addresses assume the default main port, **8080**; substitute your configured port if needed.

## The launcher or browser does not open

- Extract the entire ZIP before launching. The outer `start.bat` must remain next to the `program` folder, which includes `python/python.exe`.
- Use a writable folder outside Program Files and OneDrive. Keep any previous installation separate.
- Keep the launcher window open and check its message. If the bridge is running but no browser opened, visit [the setup wizard](http://localhost:8080/setup.html).
- Check `program/bridge.log` and its rotated `.1`–`.3` files. If the port is already in use, stop the previous panel instance before starting another one.

The published package uses `start.bat`; it does not include a standalone MA2 Panel.exe.

## The panel opens but MA2 is disconnected

1. Open grandMA2 onPC yourself and confirm the intended show is loaded.
2. Follow [First connection](FIRST-CONNECTION.md): create or select the dedicated MA2 user and separate User Profile, and enable Telnet Remote in MA2.
3. Check the wizard's MA2 address, Telnet port, exact user name and password. Replace `ma2-unconfigured.invalid`; use `127.0.0.1` when onPC runs on this computer. The usual Telnet port is `30000`, not `8080`.
4. Save and restart the bridge, then check the current connection status and [Diagnostics](http://127.0.0.1:8080/diag.html). Saved fields and a TCP connection do not prove successful login.

The wizard does not create an MA2 account. An existing `MA2_PASSWORD` environment variable overrides `program/secret.env`. Mock mode simulates MA2 and cannot confirm a real connection.

## The panel is empty or commands are blocked

A new installation has an empty venue plan, **test** mode and empty lists of allowed fixtures and scenes. Read or import the correct fixtures with the operator, then allow only the intended test Fixture ID. Fixture export may require setting `ma2.export_dir` to the actual onPC export directory.

Recording, Highlight, show saving/loading, patch changes and RDM have separate permissions. Investigate a refusal in Diagnostics and the command log; do not enable full mode simply to bypass it. See the [first-session checklist](ONPC-HALL-TEST-3.2.md).

## The tablet cannot open the panel

- Confirm that the panel opens on the Windows computer first.
- Follow [Tablet connection](TABLET.md): enable LAN access in the wizard, save and restart.
- Use the Windows computer's displayed network address, not `localhost` or `127.0.0.1` on the tablet.
- Connect both devices to the same trusted router; disable guest/client isolation for that network.
- Check the Windows **Private** network profile and run `program/firewall-open.bat` as administrator. Repeat this after changing the installation path or ports.
- If several addresses appear, use the one on the lighting router's network. Do not forward ports to the internet.

## A command result is unknown

Stop and check the log, MA2 and the physical fixture with the operator. Do not blindly repeat movements, scene recording or show loading. Stopping the bridge does not undo values or stop scenes in MA2. An all-off action is not a guaranteed global blackout.

If RDM is pending or unknown, keep `program/rdm-search.json` intact and check the actual RDM state on MA2. Do not delete the file to clear a warning.

## Updating or recovering an installation

For **3.2.0**, use the full Windows package in a separate folder. No update ZIP is published for this release. A known Windows virtual-environment updater test fails because the restarted process has a different PID; strict process identity checking remains in place. Do not update during lighting operation.

Before moving data or recovering an interrupted update, [read the backup and recovery instructions](ADVANCED.md#back-up-and-move-an-existing-installation). Keep the old installation, `backups`, `previous` and `.updates` until recovery has been checked.

## Collect useful diagnostics

On the Windows computer, open [Diagnostics](http://127.0.0.1:8080/diag.html) and the [command log](http://127.0.0.1:8080/log.html). Note the time, onPC version, Fixture ID or executor, intended action and observed status. Logs are in `program/bridge.log*`; raw replies are in `program/field-data/auto`, and saved diagnostics are in `program/diag`.

Inspect any archive for passwords and show or venue data before sharing it. Do not post private diagnostics in a public GitHub issue. For a local software check, use `program/selfcheck.bat`; its report does not replace MA2 hardware acceptance. See [advanced diagnostics](ADVANCED.md#local-diagnostics).

[All documentation](README.md) · [Known release limitations](RELEASE-3.2.md#known-limitations)
