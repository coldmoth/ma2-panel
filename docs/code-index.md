# Индекс функций

Собрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.

## ma2panel/__init__.py


## ma2panel/__main__.py


## ma2panel/api.py
- 54 `register`
  - 59 `import_file`
  - 75 `import_confirm`
  - 92 `idle`
  - 98 `get_log`
  - 102 `stop`
  - 111 `get_settings`
  - 123 `put_settings`
  - 162 `restart`
  - 172 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 184 `diagnostics`
  - 198 `upload_status`
  - 205 `upload_diagnostics`
    - 236 `private_names`
    - 255 `collect`
  - 269 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 310 `export_probe`
  - 329 `probe_console`
  - 346 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 350 `part`
    - 356 `read`

## ma2panel/bridge.py
- 60 `is_loopback`
- 80 `create_app`
  - 98 `get_config_attrs`
  - 101 `refresh_attr_names`
  - 109 `add_strobe_attrs`
  - 162 `revision_token`
  - 165 `ActionLock`
    - 166 `__aenter__`
    - 180 `__aexit__`
  - 212 `status_msg`
  - 220 `config_revision`
  - 227 `config_msg`
  - 241 `scenes_msg`
  - 245 `values_meta`
  - 255 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 265 `invalidate_evidence`
  - 278 `shown_msg`
  - 284 `session_msg`
  - 289 `broadcast`
  - 305 `spawn_broadcast`
  - 310 `history_context`
  - 313 `history_reason`
  - 328 `history_msg`
  - 333 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 353 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 362 `light_what`
  - 367 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 382 `forget_positions`
  - 389 `highlight_zone`
  - 394 `highlight_status`
  - 399 `highlight_stuck`
  - 403 `highlight_record`
  - 409 `highlight_lines`
  - 435 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 481 `highlight_action`
  - 537 `highlight_disconnect`
  - 546 `highlight_lease`
  - 556 `show_from`
  - 565 `invalidate_profiles`
  - 591 `update_show`
  - 605 `identify_show`
  - 644 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 665 `spawn_capture`
  - 670 `on_state`
  - 708 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 747 `check_ids`
  - 754 `check_scene`
  - 758 `heads`
  - 764 `selected`
  - 770 `remember`
  - 800 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 914 `owned_scene_execs`
  - 926 `action_ticket`
  - 929 `ticket_valid`
  - 934 `execute` — Send the action's lines; None on success, else the error text.
  - 1096 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 1108 `throttled`
  - 1134 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1146 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1176 `layout_save`
  - 1185 `new_id`
  - 1189 `mover`
  - 1195 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1260 `scene_pages`
  - 1263 `list_cmd`
  - 1266 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1286 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1332 `expire_evidence`
  - 1348 `poll_dmx` — What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan s
  - 1370 `expire_dmx`
  - 1386 `dmx_diagnostics` — Local, read-only snapshot. Never treats cached/sent values as actual output.
  - 1438 `read_dmx` — One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset.
  - 1563 `require_scene_context`
  - 1568 `confirm_scene_show`
  - 1577 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1605 `catalogue_meta`
  - 1612 `read_ma2` — All pools must be complete; errors never turn a previous catalogue into empty.
  - 1650 `send_ma2_lines`
  - 1664 `ma2_action`
  - 1804 `invalidate_scene_offers`
  - 1810 `offer_context`
  - 1813 `find_scene_slot`
    - 1818 `emit`
  - 1867 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1882 `record`
  - 1895 `show_name`
  - 1901 `plan_path`
  - 1904 `check_show`
  - 1913 `confirm_write_show` — A fresh read under action_lock before scene mutations, never auto-bind.
  - 1921 `import_context`
  - 1924 `import_xml`
  - 1943 `confirm_import`
  - 1961 `commit_import`
  - 2003 `open_show_plan`
  - 2049 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 2061 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 2091 `fetch_fixtures`
    - 2096 `apply`
  - 2108 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 2130 `send`
    - 2139 `can_retry`
    - 2143 `failed`
    - 2150 `read_type_table`
    - 2205 `commit`
  - 2220 `require_patch_context`
  - 2224 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 2246 `rdm_read`
  - 2261 `patch_offer`
  - 2268 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2407 `list_shows`
  - 2426 `load_show`
  - 2525 `handle`
  - 3079 `on_result`
  - 3096 `rdm_busy`
  - 3111 `ProtocolThrottle`
    - 3112 `clear`
  - 3127 `lifespan`
  - 3154 `mask`
  - 3157 `safe_data`
  - 3169 `DiagnosticHandler`
    - 3170 `emit`
  - 3185 `updating`
  - 3195 `update_busy`
  - 3202 `update_gate`
  - 3209 `update_reopen`
  - 3213 `update_stop`
  - 3218 `perform_action_inner`
  - 3255 `operation_reply`
  - 3267 `finish_operation`
  - 3283 `perform_action`
  - 3327 `handle_load`
  - 3336 `ws_endpoint`
  - 3339 `simple_ws_endpoint`
  - 3342 `serve_ws`
    - 3352 `worker`
    - 3356 `spawn`
  - 3407 `no_cache`
  - 3428 `simple_index`
  - 3432 `simple_style`
  - 3436 `simple_script`
  - 3440 `simple_feedback_script`
  - 3444 `simple_health`
  - 3448 `update_health`
- 3460 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3482 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3494 `local_addresses`
- 3501 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3521 `stop_running`
- 3533 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3546 `main`

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
- 211 `stop_child`
- 222 `health`
  - 226 `record`
- 259 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 261 `__init__`
  - 266 `start`
    - 270 `Handler`
      - 271 `log_message`
      - 274 `do_GET`
  - 308 `stop`
- 316 `apply`
- 369 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 390 `wait`
- 402 `worker`
- 421 `Updater`
  - 422 `__init__`
  - 426 `begin`
  - 435 `_run`
- 476 `recover_pending`
- 496 `watch_orphan`
- 527 `orphan_worker`
- 557 `register`
  - 563 `local`
  - 574 `denied`
  - 578 `update_health`
  - 582 `update_status`
  - 588 `check_update`
  - 600 `updater_idle`
  - 606 `quiesce`
  - 615 `start_update`

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
- 521 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 535 `dmx_text` — 289 -> "1.289".
- 540 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 548 `check_uid`
- 555 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 579 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
  - 601 `fits`
- 632 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 650 `parse_type_names` — Unique exact LongName -> number from the recorded MA2 FixtureType table.
- 668 `type_no`
- 673 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

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
  - 102 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 131 `run_export`
  - 180 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 202 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

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
- 112 `parse_fixture_type` — {dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<C
- 178 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
  - 189 `unchanged`
- 274 `save_config`

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
  - 246 `_sleep` — Waits before the next attempt; link_connect cuts it short.
  - 254 `disconnect` — Closes only this bridge's Telnet session. The console, its network and other sessions are
  - 260 `connect`
  - 264 `new_action`
  - 267 `close`
  - 271 `_raw`
  - 274 `_result`
  - 278 `send` — (ok, reply or reason). ok means status "sent". gen: the link generation the caller started
  - 340 `_drain` — Late answer to a timed-out line, so it is not read as the next line's answer. True when it
  - 350 `_pump`
  - 363 `_exchange`
  - 375 `_collect` — (reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

## ma2panel/migrations.py
- 19 `_read`
- 28 `merge_settings` — Current site settings win at each leaf, without discarding legacy siblings.
- 38 `_backup`
- 48 `legacy_archive_path` — Raw unnamed legacy snapshots are backups, not owner-checked show plans.
- 61 `migrate_config` — Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

## ma2panel/mock.py
- 16 `MockMA2`
  - 17 `__init__`
  - 79 `output` — Small LTP/soft-transfer test model; not a console emulator or evidence.
  - 108 `_handle`
  - 147 `_wire`
  - 152 `_reply`
  - 158 `_answer`
  - 334 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 350 `drop`
- 355 `start_mock`

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
- 167 `_json`
- 171 `build`
- 182 `write_zip`
- 193 `write_tree`
- 205 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 220 `_object`
- 229 `check`
- 236 `_check`
- 275 `_runtime_files`
- 291 `record_runtime`
- 295 `verify_runtime`

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
- 326 `without_passwords`
- 334 `validate_settings` — Validate the entire replacement before touching disk or the running link.

## ma2panel/scene_runtime.py
- 9 `probe_command`
- 25 `is_probe_command`
- 31 `read_nonce`
- 44 `confirm_manual_scene`
- 61 `transition_lines`
- 71 `store_scene` — Prepare away from the live target. Keep the spare, including the old Cue 1.
- 91 `GrandMasterBlackout` — Snapshot/restore Grand, leaving the independent native B.O. mask untouched.
  - 97 `__init__`
  - 103 `read`
  - 114 `toggle`

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
- 171 `user_data_names` — Literal user files plus recovery journals of individual executors.
- 179 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 206 `remove`
- 213 `sync_directory`
- 222 `sync_tree`
- 235 `durable_replace`
- 250 `atomic_json`
- 261 `copy_entry`
- 272 `safe_targets`
- 281 `snapshot_meta`
- 291 `check_snapshot`
- 303 `restore_snapshot`
- 314 `transaction`
- 323 `process_alive`
- 350 `recover` — Restore an interrupted replacement before the bridge opens any interfaces.
- 391 `install`
- 456 `acquire_lock` — Publish an already populated owner directory atomically (also survives pre-status crashes)
- 473 `serialized`
  - 475 `call`
- 499 `rollback`
- 530 `run`
- 569 `main`

## static/static/app.js
- 11 `selectionIdentity`
- 20 `rememberSelection`
- 25 `validateSelectionIntent`
- 48 `captureRevision`
- 56 `pumpConfigQueue`
- 85 `on`
- 91 `h`
- 114 `catchUpSection`
- 117 `watchControl`
- 125 `controlActive`
- 126 `cancelTargetControls`
- 132 `add`
- 152 `icon`
- 159 `pageOf`
- 160 `bridgeUp`
- 162 `linkReady`
- 163 `contextReadable`
- 164 `connected`
- 165 `fixtures`
- 166 `fixture`
- 168 `canMove`
- 169 `hasFixtures`
- 170 `safe`
- 177 `linkLine`
- 189 `send`
- 224 `sendRaw`
- 238 `busy`
- 240 `feedback`
- 244 `renderOperationFeedback`
- 255 `notice`
- 273 `actionFeature`
- 277 `featureReason`
- 283 `go`
- 295 `render`
- 345 `renderBanners`
- 374 `renderSection`
- 423 `readFromMa2`
- 424 `fixtureImportComplete`
- 435 `fixtureImportChoices`
- 465 `SECTIONS.start`
- 518 `setupSteps`
- 534 `safetyText`
- 541 `ma2Card`
- 565 `pagesList`
- 570 `SECTIONS.prepare`
- 583 `SECTIONS.help`
- 594 `transitionControl`
- 607 `SECTIONS.scenes`
- 687 `masterControl`
- 706 `setFill`
- 711 `openSceneEdit`
- 740 `cancelStore`
- 744 `openStore`
- 784 `SECTIONS.history`
- 796 `SECTIONS.shows`
- 857 `discardPending`
- 871 `clearEvidence`
- 876 `sceneAllowed`
- 879 `sceneEvidence`
- 886 `valueFreshness`
- 889 `sentSource`
- 892 `sentStale`
- 895 `observeEvidence`
- 903 `expireEvidence`
- 924 `receive`
- 1069 `connect`
- 1097 `cancelSlider`
- 1104 `flushSliders`
- 1113 `throttleSlider`
- 1128 `selectConsoleGroup`
- 1137 `selectFixtures`

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
- 62 `showExport`
- 70 `runRead`
- 76 `runLink`
- 82 `runExport`
- 88 `guarded`

## static/static/interface.js
- 4 `panelReadTools`
- 8 `panelToolVisible`
- 10 `panelRefreshTools`

## static/static/light.js
- 4 `toolVisible`
- 16 `colorMode`
- 17 `supports`
- 28 `selected`
- 29 `attributeVisible`
- 38 `split`
- 42 `liveValues`
- 46 `valueSource`
- 48 `known`
- 61 `knownText`
- 66 `lightKey`
- 70 `unsupportedNote`
- 76 `fxName`
- 77 `allowedFixture`
- 78 `pickRow`
- 83 `SECTIONS.light`
- 87 `lightWorkspace`
- 289 `plural`
- 294 `sliderCard`
- 324 `hsv2rgb`
- 328 `rgb2hsv`
- 333 `cssRgb`
- 335 `colorCard`
- 466 `moveCard`

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
- 276 `movePresets`
- 312 `renderMove`

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
- 30 `stopPing`
- 35 `planEndEdit`
- 43 `highlightOn`
- 60 `planBeamAngle`
- 76 `hallPlan`
- 336 `tapFixture`
- 357 `planOrder`
- 358 `planCurrent`
- 364 `planLight`
- 369 `planNext`
- 383 `planStep`
- 392 `SECTIONS.hall`
- 472 `hallForm`
- 498 `groupSide`
- 524 `openGroupStore`
- 542 `beamCard`

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


