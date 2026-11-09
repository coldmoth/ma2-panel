# Индекс функций

Собрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.

## ma2panel/__init__.py


## ma2panel/__main__.py


## ma2panel/api.py
- 54 `register`
  - 59 `import_file`
  - 75 `import_confirm`
  - 91 `idle`
  - 97 `get_log`
  - 101 `stop`
  - 110 `get_settings`
  - 122 `put_settings`
  - 161 `restart`
  - 171 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 183 `diagnostics`
  - 197 `upload_status`
  - 204 `upload_diagnostics`
    - 235 `private_names`
    - 254 `collect`
  - 268 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 309 `export_probe`
  - 328 `probe_console`
  - 345 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 349 `part`
    - 355 `read`

## ma2panel/bridge.py
- 58 `is_loopback`
- 77 `create_app`
  - 95 `get_config_attrs`
  - 98 `refresh_attr_names`
  - 106 `add_strobe_attrs`
  - 155 `revision_token`
  - 158 `ActionLock`
    - 159 `__aenter__`
    - 173 `__aexit__`
  - 205 `status_msg`
  - 213 `config_revision`
  - 220 `config_msg`
  - 234 `scenes_msg`
  - 238 `values_meta`
  - 248 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 258 `invalidate_evidence`
  - 271 `shown_msg`
  - 277 `session_msg`
  - 282 `broadcast`
  - 298 `spawn_broadcast`
  - 303 `history_context`
  - 306 `history_reason`
  - 319 `history_msg`
  - 324 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 343 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 352 `light_what`
  - 357 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 371 `forget_positions`
  - 378 `highlight_zone`
  - 383 `highlight_status`
  - 388 `highlight_stuck`
  - 392 `highlight_record`
  - 398 `highlight_lines`
  - 424 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 470 `highlight_action`
  - 526 `highlight_disconnect`
  - 535 `highlight_lease`
  - 545 `show_from`
  - 554 `invalidate_profiles`
  - 576 `update_show`
  - 590 `identify_show`
  - 608 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 629 `spawn_capture`
  - 634 `on_state`
  - 663 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 692 `check_ids`
  - 699 `check_scene`
  - 703 `heads`
  - 709 `selected`
  - 715 `remember`
  - 747 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 857 `action_ticket`
  - 860 `ticket_valid`
  - 865 `execute` — Send the action's lines; None on success, else the error text.
  - 972 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 984 `swap_off`
  - 997 `throttled`
  - 1023 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1035 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1065 `layout_save`
  - 1074 `new_id`
  - 1078 `mover`
  - 1084 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1149 `scene_pages`
  - 1152 `list_cmd`
  - 1155 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1175 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1221 `expire_evidence`
  - 1237 `poll_dmx` — What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan s
  - 1251 `expire_dmx`
  - 1267 `read_dmx` — One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset.
  - 1377 `require_scene_context`
  - 1382 `confirm_scene_show`
  - 1391 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1419 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 1438 `send_ma2_lines`
  - 1448 `ma2_action`
  - 1558 `invalidate_scene_offers`
  - 1564 `offer_context`
  - 1567 `find_scene_slot`
    - 1572 `emit`
  - 1621 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1636 `record`
  - 1649 `show_name`
  - 1655 `plan_path`
  - 1658 `check_show`
  - 1665 `import_context`
  - 1668 `import_xml`
  - 1688 `confirm_import`
  - 1703 `commit_import`
  - 1724 `open_show_plan`
  - 1770 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1782 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1812 `fetch_fixtures`
    - 1817 `apply`
  - 1829 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 1851 `send`
    - 1860 `can_retry`
    - 1864 `failed`
    - 1909 `commit`
  - 1924 `require_patch_context`
  - 1928 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1950 `rdm_read`
  - 1965 `patch_offer`
  - 1972 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2108 `list_shows`
  - 2127 `load_show`
  - 2226 `handle`
  - 2675 `on_result`
  - 2692 `rdm_busy`
  - 2707 `ProtocolThrottle`
    - 2708 `clear`
  - 2723 `lifespan`
  - 2750 `mask`
  - 2753 `safe_data`
  - 2765 `DiagnosticHandler`
    - 2766 `emit`
  - 2781 `updating`
  - 2791 `update_busy`
  - 2798 `update_gate`
  - 2805 `update_reopen`
  - 2809 `update_stop`
  - 2814 `perform_action_inner`
  - 2851 `operation_reply`
  - 2863 `finish_operation`
  - 2879 `perform_action`
  - 2923 `handle_load`
  - 2932 `ws_endpoint`
  - 2935 `simple_ws_endpoint`
  - 2938 `serve_ws`
    - 2948 `worker`
    - 2952 `spawn`
  - 3003 `no_cache`
  - 3024 `simple_index`
  - 3028 `simple_style`
  - 3032 `simple_script`
  - 3036 `simple_feedback_script`
  - 3040 `simple_health`
  - 3044 `update_health`
- 3056 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3078 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3090 `local_addresses`
- 3097 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3117 `stop_running`
- 3129 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3142 `main`

## ma2panel/browser_update.py
- 38 `trusted_url`
- 45 `GitHubRedirect`
  - 46 `redirect_request`
- 51 `_open`
- 56 `supported_platform`
- 60 `version_key`
- 68 `newer`
- 72 `download`
- 86 `fetch_json`
- 108 `latest`
- 135 `status`
- 148 `progress`
- 156 `release_lock`
- 160 `prepare`
- 194 `launch`
- 205 `stop_child`
- 216 `health`
  - 220 `record`
- 253 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 255 `__init__`
  - 260 `start`
    - 264 `Handler`
      - 265 `log_message`
      - 268 `do_GET`
  - 302 `stop`
- 310 `apply`
- 363 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 384 `wait`
- 396 `worker`
- 415 `Updater`
  - 416 `__init__`
  - 420 `begin`
  - 429 `_run`
- 470 `recover_pending`
- 490 `watch_orphan`
- 513 `orphan_worker`
- 543 `register`
  - 549 `local`
  - 560 `denied`
  - 564 `update_health`
  - 568 `update_status`
  - 574 `check_update`
  - 586 `updater_idle`
  - 592 `quiesce`
  - 601 `start_update`

## ma2panel/commands.py
- 22 `ActionError`
- 26 `nudge_step`
- 36 `_value`
- 43 `fade_suffix` — Programmer fade for dim and colour; "" when absent or 0. `At 50 Fade 2`: MA2 3.9 manual p.
- 51 `find`
- 58 `page_number`
- 65 `exec_page`
- 69 `store_lines` — No SaveShow: saving the whole show is the operator's decision, never the panel's.
- 77 `_reply_lines` — Ignore standalone prompts and List command echoes (possibly prefixed by a prompt).
- 85 `exec_verdict`
- 97 `unrecognised_lines`
- 110 `parse_executors` — (exec, label) from a `List Executor` reply. ponytail: reply format guessed, check in the h
- 121 `can_move` — Heads: the old moves flag, or Pan/Tilt among the parameters read from the MA2 export.
- 126 `parse_ma2_objects` — Catalogue rows from the site's assumed List format; never infer fixture membership.
- 142 `group_slot_empty` — Only an explicit empty response is safe; echoes/prompts alone prove nothing.
- 156 `parse_running` — exec -> running, only for lines that carry a status word. ponytail: status word guessed, c
- 178 `movers`
- 183 `scale`
- 189 `attr_lines`
- 194 `head_lines` — Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line.
- 209 `select_line`
- 213 `apply_move`
- 219 `check_move`
- 227 `check_jog` — Joystick step in degrees since the last one: relative, so the desk and the panel can turn
- 237 `mirrored` — Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns
- 244 `pan_flip`
- 248 `rel_lines` — Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down)
- 265 `parse_label`
- 272 `build`
- 344 `targets`
- 355 `validate_hall`
- 369 `parse_positions` — x and y both null take the fixture off the plan, back to the tray.
- 401 `is_error_reply`
- 405 `load_config`
- 436 `absolute` — "1.289" -> 289, "2.001" -> 513.
- 442 `dmx_intervals` — Sorted (start, count) ranges, without reading holes in a sparse patch.
- 456 `dmx_span` — (first address, count) covering every patched fixture of the plan.
- 462 `dmx_lua` — One Lua line per chunk of DMX_CHUNK addresses.
- 469 `parse_dmx` — {absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out.
- 487 `live_from_dmx` — What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without
- 511 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 525 `dmx_text` — 289 -> "1.289".
- 530 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 538 `check_uid`
- 545 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 569 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
  - 591 `fits`
- 622 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 640 `type_no`
- 645 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

## ma2panel/diagnostic_readback.py
- 6 `_number`
- 12 `_errors`
- 16 `build_readback`
- 107 `_valid`
- 129 `valid_readback`

## ma2panel/diagnostic_relay.py
- 11 `Relay`
  - 12 `put`

## ma2panel/diagnostic_setup.py
- 15 `_protect`
- 28 `configure` — Validate destination before replacing credentials; never print the token.
- 53 `main`

## ma2panel/diagnostic_upload.py
- 40 `UploadError`
  - 41 `__init__`
- 47 `_uuid`
- 58 `marker`
- 62 `_number`
- 69 `build_report`
  - 73 `clean`
  - 81 `typed`
  - 83 `choice`
- 148 `collect_report` — Reuse startup captures as explicitly historical evidence; never run a probe.
- 198 `Github`
  - 199 `__init__`
  - 202 `request`
  - 243 `check_private`
  - 248 `find`
  - 272 `create`
- 281 `Uploader`
  - 282 `__init__`
  - 288 `_credentials`
  - 302 `_load`
  - 328 `_save`
  - 352 `_process_lock`
  - 380 `_result`
  - 397 `enqueue` — Persist explicit consent and a snapshot without making any network request.
  - 436 `retry` — Deliver only explicitly queued reports; uncertain POSTs remain GET-only.
  - 466 `wake`
  - 470 `run`
  - 479 `status`
  - 496 `submit`
  - 515 `_uses_relay`
  - 521 `_direct_credentials`
  - 529 `_submit_relay`
  - 562 `_submit`

## ma2panel/exports.py
- 23 `bind`
  - 24 `export_folders` — Where an export may land: ma2.export_dir first, then every existing folder matching ma2.ex
  - 36 `listing`
  - 51 `save_diag_json`
  - 59 `export_type` — One Export FixtureType under a one-off name. The documentation puts fixture types in their
  - 100 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 129 `run_export`
  - 178 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 200 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

## ma2panel/firewall.py
- 7 `apply`
- 23 `main`

## ma2panel/fixtures.py
- 9 `local`
- 13 `describe` — What the file contains, for the error text and the diagnostics: the real MA2 XML layout ha
- 24 `dmx_address` — "200" -> "1.200", as List Fixture shows it. ponytail: absolute address assumed ((universe-
- 37 `guess_head`
- 41 `parse_group_export` — {group number: [fixture ids]} from an `Export Group` XML. listed: {n: name} from List Grou
- 62 `parse_export` — Fixtures with a Fixture ID. skipped, if given, gets the names of <Fixture> entries without
- 108 `parse_fixture_type` — {dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<C
- 152 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
- 210 `save_config`

## ma2panel/link.py
- 28 `Throttle`
  - 29 `__init__`
  - 35 `put`
  - 38 `pending`
  - 41 `run`
  - 49 `flush_all`
  - 53 `flush`
  - 60 `stop` — End running fades and drop waiting values whose key starts with prefix.
  - 67 `clear`
- 76 `clean`
- 80 `MA2Link` — One Telnet connection. Sends go one at a time; a drop discards everything waiting.
  - 92 `__init__`
  - 126 `ready`
  - 130 `halted`
  - 134 `halted`
  - 139 `mask`
  - 142 `_set`
  - 148 `run`
  - 204 `_login` — logged_in only when the login reply has no error AND ListVar names the configured user.
  - 235 `_sleep` — Waits before the next attempt; link_connect cuts it short.
  - 243 `disconnect` — Closes only this bridge's Telnet session. The console, its network and other sessions are
  - 249 `connect`
  - 253 `new_action`
  - 256 `close`
  - 260 `_raw`
  - 263 `_result`
  - 267 `send` — (ok, reply or reason). ok means status "sent". gen: the link generation the caller started
  - 322 `_drain` — Late answer to a timed-out line, so it is not read as the next line's answer. True when it
  - 332 `_pump`
  - 345 `_exchange`
  - 357 `_collect` — (reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

## ma2panel/migrations.py
- 19 `_read`
- 28 `merge_settings` — Current site settings win at each leaf, without discarding legacy siblings.
- 38 `_backup`
- 48 `legacy_archive_path` — Raw unnamed legacy snapshots are backups, not owner-checked show plans.
- 61 `migrate_config` — Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

## ma2panel/mock.py
- 14 `MockMA2`
  - 15 `__init__`
  - 63 `_handle`
  - 102 `_wire`
  - 107 `_reply`
  - 113 `_answer`
  - 241 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 257 `drop`
- 262 `start_mock`

## ma2panel/onboarding.py
- 11 `tablet_urls`
- 29 `register`
  - 32 `local`
  - 35 `urls`
  - 39 `status`
  - 51 `qr`

## ma2panel/rdm_search.py
- 30 `read_command`
- 46 `is_read_command`
- 53 `parse_state`
- 80 `RDMSearch`
  - 81 `__init__`
  - 109 `_current_target`
  - 113 `active`
  - 116 `snapshot`
  - 120 `_notify`
  - 127 `_persist`
  - 149 `_ensure`
  - 154 `_available`
  - 162 `_send`
  - 170 `_read`
  - 175 `_preflight`
  - 183 `prepare`
  - 197 `start`
  - 220 `_run`
  - 277 `_cleanup`
  - 291 `stop`
  - 295 `check`
  - 312 `shutdown`

## ma2panel/release.py
- 17 `RuntimeMismatch`
- 21 `_path`
- 40 `_names`
- 53 `payload`
  - 59 `add`
  - 72 `walk`
- 145 `identity`
- 160 `runtime`
- 164 `_json`
- 168 `build`
- 179 `write_zip`
- 190 `write_tree`
- 202 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 217 `_object`
- 226 `check`
- 233 `_check`
- 272 `_runtime_files`
- 288 `record_runtime`
- 292 `verify_runtime`

## ma2panel/safety.py
- 76 `_atomic_bytes`
- 88 `recover_settings` — Roll back an interrupted pair before either file is consumed. Keep the journal on failure.
- 106 `save_settings_pair` — Durable undo journal: a crash before removing it restores the previous complete pair.
- 141 `load_secret` — Password from the MA2_PASSWORD variable or secret.env (one line MA2_PASSWORD=...). Never g
- 155 `load_settings`
- 168 `read_settings_pair` — One recoverable snapshot for the settings UI, including fallback eligibility.
- 176 `effective_safety`
- 189 `redact` — Hide the password in diagnostics without eating ordinary text.
- 201 `make_guard` — guard(line) -> None when the line may be sent, else the reason it is blocked.
  - 223 `guard`
- 296 `without_passwords`
- 304 `validate_settings` — Validate the entire replacement before touching disk or the running link.

## ma2panel/scenes.py
- 7 `canonical_exec`
- 16 `exec_key`
- 20 `ordered_scenes`
- 25 `merge_scenes`
- 47 `slot_candidates`

## ma2panel/selfcheck.py
- 20 `check`
- 25 `get`
- 30 `log_lines`
- 35 `ask`
- 45 `fixtures_report`
- 60 `main`
- 100 `cli`

## ma2panel/show_files.py
- 15 `fingerprint`
- 19 `regular`
- 26 `validate`
- 42 `snapshot` — Exclusive verified copy; source must stay unchanged throughout the read.
- 74 `publish` — Publish complete file atomically without replacing any existing directory entry.

## ma2panel/show_plans.py
- 8 `_owner`
- 18 `plan_path` — Use a bounded ASCII SHA256 name; legacy names are read only and owner-checked.

## ma2panel/show_transfer.py
- 27 `disk`
- 37 `register`
  - 46 `space`
  - 51 `public`
  - 54 `fail`
  - 57 `trusted`
  - 71 `folder`
  - 83 `available`
  - 92 `new`
  - 103 `identity`
  - 113 `source_for`
  - 120 `connection`
  - 125 `fresh`
  - 131 `stage`
  - 136 `checked_send`
  - 150 `run`
  - 236 `upload`
  - 282 `prepare`
  - 303 `status`
  - 310 `confirm`
  - 345 `download`

## ma2panel/status_evidence.py
- 5 `Evidence`
  - 6 `__init__`
  - 10 `observe`
  - 13 `invalidate`
  - 20 `snapshot`

## ma2panel/update.py
- 21 `release_module`
- 33 `UpdateError`
- 37 `allowed`
- 52 `validate_zip`
- 85 `normalize_url`
- 96 `download`
- 108 `settings`
- 113 `version`
- 118 `idle`
- 128 `prepare_bridge`
- 156 `local_archive` — An update zip from a USB stick; a .sha256 next to it is checked when present.
- 171 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 198 `remove`
- 205 `sync_directory`
- 214 `sync_tree`
- 227 `durable_replace`
- 242 `atomic_json`
- 253 `copy_entry`
- 264 `safe_targets`
- 273 `snapshot_meta`
- 283 `check_snapshot`
- 295 `restore_snapshot`
- 306 `transaction`
- 315 `process_alive`
- 342 `recover` — Restore an interrupted replacement before the bridge opens any interfaces.
- 383 `install`
- 448 `acquire_lock` — Publish an already populated owner directory atomically (also survives pre-status crashes)
- 465 `serialized`
  - 467 `call`
- 491 `rollback`
- 522 `run`
- 561 `main`

## static/static/app.js
- 11 `selectionIdentity`
- 20 `rememberSelection`
- 25 `validateSelectionIntent`
- 48 `captureRevision`
- 56 `pumpConfigQueue`
- 80 `on`
- 86 `h`
- 101 `add`
- 121 `icon`
- 128 `pageOf`
- 129 `bridgeUp`
- 131 `linkReady`
- 132 `connected`
- 133 `fixtures`
- 134 `fixture`
- 136 `canMove`
- 137 `hasFixtures`
- 138 `safe`
- 145 `linkLine`
- 156 `send`
- 187 `sendRaw`
- 201 `busy`
- 203 `feedback`
- 207 `renderOperationFeedback`
- 218 `notice`
- 236 `actionFeature`
- 240 `featureReason`
- 246 `go`
- 256 `render`
- 304 `renderBanners`
- 331 `renderSection`
- 375 `readFromMa2`
- 376 `fixtureImportComplete`
- 387 `fixtureImportChoices`
- 417 `SECTIONS.start`
- 466 `setupSteps`
- 482 `safetyText`
- 489 `ma2Card`
- 513 `pagesList`
- 517 `SECTIONS.scenes`
- 558 `masterControl`
- 579 `setFill`
- 584 `openSceneEdit`
- 611 `cancelStore`
- 615 `openStore`
- 652 `SECTIONS.history`
- 664 `SECTIONS.shows`
- 725 `discardPending`
- 739 `clearEvidence`
- 744 `sceneAllowed`
- 747 `sceneEvidence`
- 754 `valueFreshness`
- 757 `sentSource`
- 760 `sentStale`
- 763 `observeEvidence`
- 771 `expireEvidence`
- 792 `receive`
- 926 `connect`
- 954 `cancelSlider`
- 961 `flushSliders`
- 970 `throttleSlider`
- 985 `selectConsoleGroup`
- 994 `selectFixtures`

## static/static/command-feedback.js
- 2 `commandOperationName`
- 20 `commandFeedback`
- 47 `commandWaiting`
- 58 `commandWaitMs`

## static/static/diag-upload.js


## static/static/diag.js
- 8 `replyList`
- 18 `refresh`
- 41 `exportText`
- 56 `showExport`
- 64 `runRead`
- 70 `runLink`
- 76 `runExport`
- 82 `guarded`

## static/static/interface.js
- 4 `panelReadTools`
- 8 `panelToolVisible`
- 10 `panelRefreshTools`

## static/static/light.js
- 4 `toolVisible`
- 16 `colorMode`
- 17 `supports`
- 23 `selected`
- 24 `attributeVisible`
- 33 `split`
- 37 `liveValues`
- 41 `valueSource`
- 43 `known`
- 56 `knownText`
- 61 `lightKey`
- 65 `unsupportedNote`
- 71 `fxName`
- 72 `allowedFixture`
- 73 `pickRow`
- 78 `SECTIONS.light`
- 257 `plural`
- 262 `sliderCard`
- 290 `hsv2rgb`
- 294 `rgb2hsv`
- 299 `cssRgb`
- 301 `colorCard`
- 425 `moveCard`

## static/static/move.js
- 9 `moveHeads`
- 17 `moveValue`
- 22 `moveClip`
- 24 `moveEl`
- 32 `joyVector`
- 38 `joyRate`
- 43 `joyTick`
- 53 `moveAxisCancel`
- 56 `moveAxisSend`
- 70 `moveStop`
- 87 `moveShell`
- 274 `movePresets`
- 310 `renderMove`

## static/static/patch.js
- 5 `patchKey`
- 38 `dmxText`
- 39 `closeDialog`
- 41 `rdmSearchPending`
- 42 `rdmSearchBusy`
- 43 `rdmSearchBegin`
- 49 `rdmRecoveryText`
- 52 `rdmSearchBanner`
- 60 `rdmResults`
- 64 `rdmCard`
- 98 `patchTable`
- 116 `patchPick`
- 122 `patchEditor`
- 155 `patchDialog`
- 181 `patchResult`
- 191 `SECTIONS.patch`

## static/static/plan.js
- 7 `planKind`
- 14 `placed`
- 15 `hallOf`
- 16 `planKey`
- 22 `planBeginEdit`
- 29 `stopPing`
- 34 `planEndEdit`
- 42 `highlightOn`
- 59 `planBeamAngle`
- 75 `hallPlan`
- 316 `tapFixture`
- 337 `planOrder`
- 338 `planCurrent`
- 344 `planLight`
- 349 `planNext`
- 363 `planStep`
- 372 `SECTIONS.hall`
- 452 `hallForm`
- 470 `groupSide`
- 496 `openGroupStore`
- 514 `beamCard`

## static/static/settings.js
- 7 `status`
- 8 `saved`
- 9 `clearErrors`
- 16 `fieldError`
- 26 `warning`
- 27 `csv`
- 28 `fill`
- 60 `load`
- 128 `importElement`
- 134 `importComplete`
- 146 `renderImportChoices`
- 200 `importResult`

## static/static/setup.js


## static/static/show-files.js
- 4 `showFilesPaint`
- 5 `showFilesRemember`
- 6 `showFilesRequest`
- 15 `showFilesPoll`
- 22 `showFilesRefresh`
- 37 `showFilesConfirm`
- 55 `showFilesPrepare`
- 66 `showFilesUpload`
- 81 `showFilesCard`

## static/static/simple.js


## static/static/update.js


