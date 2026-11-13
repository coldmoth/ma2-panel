# In-app updates and test releases

Open Settings on the Windows x64 bridge computer using localhost. Keep using
**«Проверить обновления»** (Check for updates), read the version and release notes,
then press **«Обновить»** (Update). The application downloads, verifies, installs
and restarts through the existing updater. No manual package transfer is required
for compatible installations starting with v3.3.0.

**«Получать тестовые обновления»** (Receive test updates) is off by default.
Changing it saves immediately to the installation's settings, without checking,
downloading, installing or restarting. When enabled, checks include stable, RC
and beta releases. Drafts and unsupported tags are ignored; versions are ordered
by SemVer precedence, including numbered prereleases. Build metadata does not
make an installed version newer. Downgrades are never offered. After installing a
stable version, the next RC must have a higher base version: for example,
`3.3.2` → `3.3.3-rc.1`, not `3.3.2-rc.2`.

The stable channel uses GitHub `/releases/latest`; the optional test channel reads
the paginated release list and selects the newest newer compatible candidate.
The channel is re-read before downloading, so changing it invalidates a previous
selection. A changed release requires a new check and confirmation.

## Verification and preservation

The existing trusted HTTPS host checks, SHA256 sidecar, complete file manifest,
VERSION/manifest/tag agreement and Python/lib runtime checks remain mandatory.
Stable packages require authenticated stable promotion evidence. Test packages
require all mandatory software gates and a quality report fingerprint anchored
in a GitHub Actions check for the exact source, CI run/attempt and ZIP hashes.
Test evidence cannot authorize a stable release. Legacy RC1 has a stable internal
VERSION and lacks this candidate evidence; it is not silently re-labelled.

The bridge stays running during download. Admission checks before the operation
and before shutdown reject busy lighting work. A detached worker performs the
existing transaction, verifies the restarted version on both enabled interfaces,
and attempts exact program rollback if startup fails. Existing recovery journals
and the previous program remain available; private files are not program payload.
Settings, plans, groups, shows, secrets, diagnostics and existing logs survive;
logs may receive normal new entries. Program rollback preserves current user data.
Keep `previous/`, `.updates/` and backups intact. Locked files, failed disk writes,
network errors and interrupted operations must report failure, not success.

## First update from v3.3.0

The published v3.3.0 client cannot discover a prerelease. It needs a new, compatible
stable release with the usual `ma2-panel-update.zip` and `.sha256` assets. A full
stable containing the RC fixes and channel switch would require **one** Update
press. An updater-only stable followed by a higher-version RC would require
**two**, both through the same UI.

Neither route bypasses release gates. Stable requires independent review,
hardware acceptance and complete field evidence bound to the exact candidate
source and ZIPs. There is no updater-only exemption. Until those receipts exist,
no new stable is published and the old client has no new in-app target.

## Automated test scope

`scripts/update_channels_windows.py` downloads the unchanged published v3.3.0 full
Windows ZIP and verifies its pinned SHA256. It runs its embedded Python and actual
old updater, clicks the existing buttons in Chromium, installs a **synthetic
stable fixture**, enables test updates and installs the current matching RC
package. Only GitHub transport and CI receipts are fixtures; real network access
to MA2 is blocked. It verifies settings, shows, plans/groups, secrets, journals,
logs and the rollback snapshot after restarting. Separate release lifecycle and
Windows delivery gates execute rollback and interrupted recovery.

This test does not assert that a stable fixture is public, that a public RC has
already been installed after a public stable, or that physical lighting works.
Hardware acceptance remains separate: see hall-test-plan sections 12–13.
