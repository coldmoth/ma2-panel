# User guide

The interface is currently in Russian. This guide describes the controls in English. Before controlling lighting, complete [First connection](FIRST-CONNECTION.md) and the [supervised first test](ONPC-HALL-TEST-3.2.md).

## Simple scene view

Use the address provided by the operator, normally port **8090**. Select a scene by its number and name. This view does not provide fixture, patch or show editing.

The all-off control stops configured, permitted scenes and sets eligible fixtures in the venue plan to zero. It is not a global MA2 master and does not guarantee complete darkness. Other executors, the Programmer and complex fixture types need separate verification.

If the connection drops or a result is unknown, ask the operator to check the panel and onPC before trying again.

## Full control panel

Open the main address, normally port **8080**. Check the connection and active show first. Available actions depend on the bridge permissions and fixture data.

- **Scenes and executors:** select a scene and adjust its transition if needed. Record or delete only on allocated executors; check the executor number before confirming. Starting a scene sends ClearAll to the panel user's Programmer, so use a dedicated User Profile.
- **Fixture control:** select fixtures or a group, then adjust dimmer and color. Moving heads have a joystick, independent Pan/Tilt sliders and position presets. Unknown and mixed values are shown explicitly; additional controls depend on the fixture type.
- **Venue layout:** read fixtures from MA2 or import XML, place them on the plan, then check groups, types and head orientation. Highlight requires permission and can affect live lighting.
- **Groups and presets:** use an existing group or preset only after checking its intended fixtures and values. Writing requires the relevant permissions.
- **Shows:** check the active MA2 show and the local plan. A local plan is not an MA2 show file. Real MA2 show saving and loading require separate permissions and hardware acceptance.
- **Patch and RDM:** inspect addresses and conflicts. Address changes and RDM affect real devices; test them separately with the operator, outside a performance.
- **History:** inspect supported panel changes and available undo operations. This is not a complete backup of the console.

## Read status carefully

An accepted command is not confirmation of a physical lighting result. Running scene status is polled, normally every two seconds; an unknown or stale response stays unknown. The last pressed button is not a readback from MA2. Do not blindly repeat a command whose result is uncertain.

Venue icons show the most recently read MA2 output. Head direction is calculated from the last known Pan value and home/invert calibration, rather than physically measured. Without known Pan and calibration it is not shown; Tilt is not projected. Fixture ranges, multi-instance types, color/gobo wheels and individual channels require verification on the actual equipment.

Stopping command transmission, disconnecting and stopping the bridge do not turn off lighting already set in MA2. Use the operator's verified MA2 controls for emergency handling.

## Settings, diagnostics and data

On the Windows computer, open [Settings](http://127.0.0.1:8080/settings.html), [Diagnostics](http://127.0.0.1:8080/diag.html) or the [command log](http://127.0.0.1:8080/log.html). Refusals should be investigated before changing permissions.

Saving or loading a real show is separate from saving the local venue plan. Back up the MA2 show and installation folder before write operations. Check an uncertain operation on MA2 before repeating it.

If RDM is pending or its result is unknown, do not assume it is off. Preserve `program/rdm-search.json` and have the operator check the console. Background recovery is not physical confirmation that RDM is off.

Diagnostics may contain venue layouts, show names, addresses and raw console replies. Inspect archives before sharing them; do not attach sensitive data to a public issue. The diagnostic upload feature queues a sanitized report through the support relay without a GitHub account on the user's computer. Server acceptance and confirmed delivery are different states; an offline report can remain queued.

## Validation status

Version **3.2.0 is a pre-release**. Automated tests and Windows package checks cover software behavior, not the light output, target laptop or physical tablet. Remaining hardware checks include scene transitions, Programmer isolation, Pan/Tilt accuracy, fixture-specific attributes, RDM, all-off behavior and real show saving/loading.

[Backups and recovery](ADVANCED.md#back-up-and-move-an-existing-installation) · [Troubleshooting](TROUBLESHOOTING.md) · [Release notes](RELEASE-3.2.md)
