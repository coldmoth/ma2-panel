# Existing-button updates and optional test channel

Implement the user's approved request, without changing lighting commands or the updater transaction engine.

1. Add strict SemVer ordering (including existing PEP 440 rc/beta spellings and build identities). Test rc.2 < rc.10 < stable and reject malformed versions.
2. Keep `/releases/latest` for stable; opt-in uses paginated releases, ignores drafts/unsupported tags, sorts by version and filters newer compatible candidates. Keep stable promotion evidence; authenticate test quality evidence against CI and exact ZIP/SHA.
3. Persist `test_updates` (false by default) through the existing settings transaction. Add one Russian checkbox beside the current buttons, no automatic download/check/install. Re-read preferences before installation; prevent channel changes during an operation.
4. Test old v3.3.0 code and downloaded Windows x64 embedded runtime with a controlled GitHub transport, mock bridge and both update steps. Label synthetic stable fixtures explicitly. Preserve all private-data sentinels; exercise rollback and recovery.
5. Run subsystem tests, full Python/Node and browser checks, regenerate code index; run Windows CI for the clean public commit. Publish a new RC only from exact successful artifacts. Existing releases are immutable for this task.
6. Stable remains blocked until exact-SHA/ZIP hardware, independent review and V3 receipts exist. This also blocks a minimal updater-only stable: there is no gate exemption. Do not manufacture receipts or publish a stable fixture.

Release sequence: candidate v3.3.2-rc.1 with matching internal identity; after acceptance, a separately tested stable (v3.3.1 or v3.3.2, with matching internal identity) reaches old clients in one installation. Subsequent RC must have a higher base, e.g. v3.3.2-rc.1 after v3.3.1, or v3.3.3-rc.1 after v3.3.2. Publication of stable is conditional on existing gates, not merely software CI.
