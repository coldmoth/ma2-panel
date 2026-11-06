# Changelog

## 3.2.0 — 2026-11-06 (Pre-release)

- Stage Atlas interface: graphite palette, venue plan and inspector, tablet/phone layouts, search, groups and zoom.
- Existing scene/executor, fixture, independent Pan/Tilt, ±1° step, relative movement, preset, patch, RDM and show controls retain their permissions.
- Fixed selection recovery after reconnect, Zoom/Focus access without Pan/Tilt, overlapping controls and command-result feedback.
- New installations require an explicit MA2 address. Initial test mode does not permit fixture or scene control.
- Packaging uses the existing Windows x64 builder, pinned runtime and dependencies. Real MA2 acceptance remains pending.
- [Release details and verification](docs/RELEASE-3.2.md) · [First-session checklist](docs/ONPC-HALL-TEST-3.2.md).

## 3.1.1 — 2026-11-04 (Test build)

- Accumulated fixes for scene status, cancellation of stale operations, DMX handling, RDM and data preservation.
- Online updates from official GitHub Releases: numeric version comparison, explicit release selection, release notes, restricted HTTPS redirects and free-space/platform checks.
- Retained USB/LAN updates, transactional installation/recovery and exact rollback.
- Shared Windows x64 packager with pinned embedded Python 3.12.10, dependencies verified against lockfile hashes, reproducible Windows/USB/update ZIPs and recorded build inputs.
- GitHub Actions checks Python/Node, Chromium/WebKit and the delivered Windows package; release drafts depend on successful jobs.

This build was intended for isolated testing. Real grandMA2 acceptance, independent updater review and manual Windows checks were not complete. The stable updater does not offer pre-releases. Do not install automatically on a performance computer.

## 3.1.0 — 2026-11-03

- Independent absolute Pan/Tilt axes alongside the joystick, selective DMX range reads and stale-value handling.
- Request IDs, confirmed operation results, protection against stale shared-plan saves and clearer scene status.
- Browser updates with manifest checks, transactional installation and exact program rollback.
- Configuration migration to schema v5, safe show-plan paths and XML import confirmation.
- Browser transfer of real `.show.gz` files with file checks and console-load confirmation.
- Explicit RDM fixture search start/stop, shutdown checks and state recovery after a crash.
- Sanitized diagnostics queued through an HTTPS relay without GitHub keys on the venue computer.
- Compact Windows package: outer `start.bat`, `program` folder and a connection wizard with offline QR codes and current network addresses.
- Protocol, HTTP/WebSocket and Chromium/WebKit interface checks; Linux, Windows mock and browser CI jobs.
- GPL-3.0-only source, Windows x64 package, USB/program update ZIPs and checksums.

Automated checks do not replace acceptance on Windows, physical tablets and MA2. General scene behavior and complete all-off behavior awaited venue evidence. Updating 3.0 through an update ZIP was incompatible with its runtime; a separate full installation and preserved local data were required. See the [historical 3.1 notes (Russian)](docs/RELEASE-3.1.md).

## 3.0.0 — 2026-11-02

First public GitHub release of the current panel.

- Tablet interface for scenes, lighting, venue layout, shows and venue setup.
- Simple scene view for teachers on separate port 8090.
- Dimmer, color and moving-head controls according to fixture-type capabilities.
- MA2 fixture/group import, local show plans and change history.
- Executor checks before recording; protection for uncertain results and concurrent changes.
- Command filtering, separate permissions for hazardous operations, throttling and serialized transmission.
- Windows package, USB updates, diagnostics and mock mode.
- README, installation/user guides and public templates; local user data excluded from publication.

Application code corresponded to `beb22c7` from 2026-10-30. Release preparation changed documentation, packaging and the package version. No real console was tested during release preparation.

## Before public releases — 2026-10-16 to 2026-10-30

These were local development stages, not published GitHub tags:

- **October 16:** initial commands, Telnet bridge, mock, WebSocket, simple UI, XML import and venue layout.
- **October 17:** internal v2 — moving heads, presets, groups, dark interface, scenes and pages.
- **October 18:** internal v3 — fixture reads, Highlight and shows; Windows package and command restrictions.
- **October 18–22:** internal v4 — UI sections, MA2 groups/presets, console fixes, DMX reads, patch/RDM and history.
- **October 25–29:** simple view on 8090; strobe and parameter visibility by fixture type.
- **October 30:** tablet lighting/scene control, concurrent-state protection and uncertain scene handling.

The first public release used configuration schema `4`. Test names containing `v3`/`v4` and older plans are retained as development history.
