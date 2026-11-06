# Supervised first session — 3.2.0

**Pre-release: real grandMA2 hardware acceptance is not complete.** Work with the MA2 operator, a copy of the show and one selected safe test fixture.

[Install on Windows](SETUP.md) · [First connection](FIRST-CONNECTION.md) · [Tablet connection](TABLET.md)

## Prepare the session

Install the full package in a separate folder and open the outer `start.bat`. Keep the launcher window open. The setup wizard is at [http://localhost:8080/setup.html](http://localhost:8080/setup.html), the full panel at [http://127.0.0.1:8080](http://127.0.0.1:8080), and the simple view at [http://127.0.0.1:8090](http://127.0.0.1:8090).

Prepare the dedicated MA2 user, separate User Profile and Telnet Remote **inside onPC**, then enter the same credentials in the wizard. Replace `ma2-unconfigured.invalid` with the actual onPC address, save and restart. Saving settings does not prove login. A new installation uses test mode, empty permissions and local-only browser access. Mock is off by default; `program/start-mock.bat` is a separate simulation.

## Check one fixture first

1. Save a copy of the show in MA2. Clear people from the test fixture's beam and movement area. Starting the bridge must not change dimmer, position or executor state; stop if it does.
2. Confirm successful login and the intended user, User Profile and MA2 version in the wizard and Diagnostics. A TCP connection or mock status does not prove MA2 login.
3. Check reading one scene, group and Fixture ID. Fixture reading/XML import needs its own permission. Set the actual onPC export directory if required. An empty venue plan is not an automatic import of the active show. Keep logs if the response format is unrecognized.
4. In Settings, keep **test** mode and allow only that Fixture ID in `safety.allowed_fixtures`. Leave scenes, master control, recording, Highlight, RDM and show loading disabled. Save and restart the bridge.
5. Select the fixture and check its ID in the panel and the dedicated MA2 profile's Programmer. Selection alone must not change dimmer or position.
6. With the operator's agreement, set a small, safe dimmer value. Compare the command log, onPC Programmer/DMX and physical fixture. A command accepted without error is not proof of a physical change. Stop on an unknown result; do not retry blindly.
7. Only after checking that fixture type's Pan/Tilt range, try one **±1°** step on a safe axis. Check the direction, amount and stop on release. Then test the joystick, separate sliders, color and return to the agreed state.
8. Test multi-selection and relative movement later, using two explicitly permitted heads with verified ranges. Use known targets for presets/groups and a dedicated executor for a test scene.
9. With the lighting in a safe stationary state, disconnect and restore the onPC connection. Status should become stale and controls should block; earlier movements or scenes must not replay after reconnect. Check saved settings after a restart. Inspect the plan and patch before permitting writes.

Do not begin with all-off/Blackout, sudden movement, all fixtures, Highlight, RDM, patch changes or real show saving/loading. User Profile Programmer isolation and global all-off behavior need separate acceptance. Automated tests cannot confirm physical results.

## Stop and record problems

Stopping command transmission does not turn lights off. To end the process, press **Ctrl+C** in its window or open `program/stop.bat`. Verify lighting in onPC; disconnecting the bridge does not undo values or stop running scenes.

Record the time, onPC version, Fixture ID/executor, action and observed status. Logs are in `program/bridge.log` and `.1`–`.3`; the Diagnostics page can save an archive. Raw replies are in `program/field-data/auto`, diagnostics in `program/diag`, and configuration backups in `program/backups`.

Keep `.updates`, `previous` and RDM state intact if recovery or operation state is uncertain. Inspect diagnostics for passwords and private show data before sharing them.

## Remaining acceptance

Verify actual MA2 response formats, scene Running/Off status and transitions, Programmer isolation, fixture ranges and Pan/Tilt accuracy, relative movement, CMY/Shutter, RDM shutdown, all-off behavior, real show saving/loading and touch operation on the target devices.

The Windows package passed its delivered-runtime checks, but the target laptop, real onPC connection and physical touch have not been validated. A Windows virtual-environment browser updater test has a known PID mismatch. Use a separate full installation, with no updates during lighting operation.

[Release status and evidence](RELEASE-3.2.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Backups and recovery](ADVANCED.md)
