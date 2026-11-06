# ma2-panel 3.2.0 — Pre-release

**[Download for Windows](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/ma2-panel-win.zip)** · [SHA256 checksum](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/ma2-panel-win.zip.sha256)

**For supervised testing. Validation with real grandMA2 hardware is not yet complete.**

## Get started

1. Download `ma2-panel-win.zip` and extract the entire `ma2-panel` folder to a new, writable location, separate from any previous installation.
2. Open the outer **`start.bat`**, next to the `program` folder. Python 3.12.10 x64 and dependencies are included; no separate Python installation is needed. Keep the launcher window open.
3. Follow the wizard at [http://localhost:8080/setup.html](http://localhost:8080/setup.html). Prepare a dedicated user with a separate User Profile and enable Telnet Remote **in grandMA2**, then enter those credentials in the wizard. The wizard does not create the MA2 account.
4. Replace `ma2-unconfigured.invalid` with the onPC address: `127.0.0.1` on the same computer, or its local network address. Check the Telnet port (usually `30000`), save and restart the bridge.
5. Open the [full panel](http://127.0.0.1:8080) or [simple scene view](http://127.0.0.1:8090). Confirm login and test one permitted fixture with the operator before wider use.

The application interface is currently in Russian. New installations have an empty venue plan, **test** mode, empty permission lists and local-only browser access. Mock is off by default; `program/start-mock.bat` starts a separate simulation.

[Installation](https://github.com/coldmoth/ma2-panel/blob/main/docs/SETUP.md) · [First connection](https://github.com/coldmoth/ma2-panel/blob/main/docs/FIRST-CONNECTION.md) · [First-session checklist](https://github.com/coldmoth/ma2-panel/blob/main/docs/ONPC-HALL-TEST-3.2.md)

## What's new

- **Stage Atlas interface:** a graphite palette, large venue plan and inspector, tablet and phone layouts, fixture search, groups, zoom, pan and lasso selection.
- Scene/executor and fixture controls, independent Pan/Tilt sliders, ±1° steps, relative movement, groups, presets, patch and show tools retain their existing permissions.
- Improved selection recovery after reconnect, Zoom/Focus access for fixtures without Pan/Tilt, control spacing and command-result feedback. An accepted command is not presented as physical confirmation.
- Explicit first-time MA2 setup. Existing command guards and protection against replaying unconfirmed commands remain in place. No venue settings, passwords, working shows or prototype/demo adapters are included. Dependencies were not upgraded.

## Requirements

- Windows **10/11 x64** and a writable installation folder.
- grandMA2 onPC **3.9**, a dedicated user/User Profile and Telnet Remote configured.
- A modern browser, such as Chrome or Edge.
- A trusted local network for tablet access. The panel has no web user authentication; do not expose its ports to the internet.

## Known limitations

- **Real MA2 acceptance is pending.** Response formats, scene Running/Off status and transitions, Programmer isolation, Pan/Tilt ranges and accuracy, relative head movement, CMY/Shutter, RDM, global all-off behavior and real show saving/loading require physical verification. The target laptop and physical tablet/touch controls have not been validated.
- **Use a separate full installation.** No update ZIP is attached to this release: the runtime lock identity changed, so updating an older runtime through a USB/browser ZIP is unsupported. Back up the old installation and preserve its user data; do not overwrite it with examples. Never update during lighting operation.
- A known **Windows virtual-environment browser updater test failure** rejects the restarted process because its PID differs from the launcher's PID. Strict process identity checks were retained. The delivered embedded Windows package passed its separate checks; this does not remove the diagnostic CI failure.
- Start with confirmed login and one safe fixture, not all-off/Blackout, sudden movement, all fixtures, Highlight, RDM, patch changes or show writes. An unknown result requires checking MA2, not blindly repeating the command. Independent review was not performed during release preparation.
- The package is **not Authenticode-signed**. SHA256 checks integrity; it is not an independent publisher signature.

## Verification

- Local checks: **1,342 pytest passed, 1 skipped**, 11 subtests; Node checks passed. Mock HTTP/WebSocket checks passed for the full and simple views. Non-mock startup was checked with console egress blocked; no hardware was connected.
- Chromium/WebKit preflight: **8/8**; Stage Atlas at four widths: **8/8**; reconnect, gestures and multi-selection checks: **2/2**. These are desktop checks, not physical tablet acceptance.
- Windows checks passed for reproducible builds, the embedded runtime, BAT launchers, Unicode paths, update/rollback, user/RDM data and mock HTTP/WebSocket. The downloaded ZIP, manifests and checksums were verified. Payload: **3.2.0+a5fb29b**.

[CI results, including the known updater failure](https://github.com/coldmoth/ma2-panel/actions/runs/42216586120). The attached [verification report](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/verification-3.2.0.json) and [build inputs](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/build-inputs.json) record the release evidence. Automated checks do not confirm physical lighting behavior.

The original ZIP includes the first-session guide at `program/docs/ONPC-HALL-TEST-3.2.md` in Russian. The links above provide the revised English guides; the published binary package is unchanged.

Released **2026-11-06**. Source code: **GPL-3.0-only**.
