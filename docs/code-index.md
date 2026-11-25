# Индекс функций

Собрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.

## ma2panel/__init__.py


## ma2panel/__main__.py


## ma2panel/api.py
- 54 `register`
  - 59 `import_file`
  - 78 `import_confirm`
  - 96 `idle`
  - 102 `get_log`
  - 106 `stop`
  - 115 `get_settings`
  - 127 `put_settings`
  - 172 `restart`
  - 187 `restart_status`
  - 199 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 211 `diagnostics`
  - 225 `upload_status`
  - 232 `upload_diagnostics`
    - 263 `private_names`
    - 282 `collect`
  - 296 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 337 `export_probe`
  - 356 `probe_console`
  - 373 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 377 `part`
    - 383 `read`
  - 423 `quality_snapshot`

## ma2panel/bridge.py
- 65 `is_loopback`
- 86 `create_app`
  - 93 `working_file`
  - 102 `save_working_plan`
  - 126 `get_config_attrs`
  - 129 `refresh_attr_names`
  - 137 `add_strobe_attrs`
  - 152 `guard`
  - 195 `revision_token`
  - 201 `ActionLock`
    - 202 `__aenter__`
    - 217 `__aexit__`
  - 251 `status_msg`
  - 259 `config_revision`
  - 266 `config_msg`
  - 280 `scenes_msg`
  - 284 `values_meta`
  - 294 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 304 `invalidate_evidence`
  - 317 `shown_msg`
  - 324 `session_msg`
  - 331 `broadcast`
  - 347 `spawn_broadcast`
  - 352 `history_context`
  - 355 `history_reason`
  - 370 `history_msg`
  - 375 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 395 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 404 `light_what`
  - 409 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 424 `forget_positions`
  - 431 `highlight_zone`
  - 436 `highlight_status`
  - 441 `highlight_stuck`
  - 445 `highlight_record`
  - 451 `highlight_lines`
  - 477 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 523 `highlight_action`
  - 579 `highlight_disconnect`
  - 588 `highlight_lease`
  - 598 `show_from`
  - 607 `invalidate_profiles`
  - 633 `update_show`
  - 649 `identify_show`
  - 688 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 709 `spawn_capture`
  - 714 `on_state`
  - 752 `reason`
  - 755 `refusal`
  - 758 `link_block`
  - 762 `show_file_block`
  - 768 `standard_block`
  - 773 `blocked` — Admission checks shared by the dispatcher and status. The link still guards every line.
  - 809 `blackout_block`
  - 815 `recovery_block`
  - 821 `readiness_status`
    - 826 `admission`
  - 850 `check_ids`
  - 857 `check_scene`
  - 861 `heads`
  - 867 `selected`
  - 873 `remember`
  - 903 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 1005 `read_scene_identity`
  - 1012 `check_scene_identity_confirmed`
  - 1016 `owned_scene_execs`
  - 1023 `scene_release_reason`
  - 1038 `action_ticket`
  - 1041 `ticket_valid`
  - 1046 `check_scene_intent`
  - 1059 `execute` — Send the action's lines; None on success, else the error text.
  - 1292 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 1304 `throttled`
  - 1330 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1342 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1372 `layout_save`
  - 1392 `new_id`
  - 1396 `mover`
  - 1402 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1487 `scene_pages`
  - 1490 `list_cmd`
  - 1493 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1513 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1558 `expire_evidence`
  - 1574 `poll_simulation`
  - 1583 `poll_dmx` — What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan s
  - 1602 `poll_types` — Profile discovery remains available when live DMX readback is disabled.
  - 1620 `expire_dmx`
  - 1636 `dmx_diagnostics` — Local, read-only snapshot. Never treats cached/sent values as actual output.
  - 1688 `read_dmx` — One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset.
  - 1813 `require_scene_context`
  - 1818 `confirm_scene_show`
  - 1827 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1855 `catalogue_meta`
  - 1862 `read_ma2` — All pools must be complete; errors never turn a previous catalogue into empty.
  - 1900 `send_ma2_lines`
  - 1914 `ma2_action`
  - 2054 `invalidate_scene_offers`
  - 2060 `offer_context`
  - 2063 `find_scene_slot`
    - 2068 `emit`
  - 2117 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 2132 `record`
  - 2145 `show_name`
  - 2151 `plan_path`
  - 2154 `show_block`
  - 2163 `check_show`
  - 2167 `confirm_write_show` — A fresh read under action_lock before scene mutations, never auto-bind.
  - 2175 `import_context`
  - 2178 `import_xml`
  - 2197 `confirm_import`
  - 2215 `commit_import`
  - 2257 `prepare_show_plan`
  - 2270 `active_plan_data`
  - 2273 `accept_show_plan`
  - 2294 `plan_draft_active`
  - 2299 `open_show_plan`
  - 2326 `plan_selection_status`
  - 2337 `choose_existing_plan`
    - 2355 `report`
  - 2440 `follow_desk_show` — Caller holds action_lock. Only observation paths may select a local plan.
  - 2457 `require_import_show`
  - 2464 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 2494 `fetch_fixtures`
    - 2499 `apply`
  - 2511 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 2515 `validate_editor`
    - 2541 `send`
    - 2552 `can_retry`
    - 2556 `failed`
    - 2563 `read_type_table`
    - 2618 `commit`
  - 2636 `require_patch_context`
  - 2640 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 2662 `rdm_read`
  - 2677 `patch_offer`
  - 2684 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2823 `list_shows`
  - 2842 `load_show`
  - 2941 `handle`
  - 3545 `on_result`
  - 3565 `rdm_busy`
  - 3580 `ProtocolThrottle`
    - 3581 `clear`
  - 3596 `lifespan`
  - 3628 `mask`
  - 3631 `safe_data`
  - 3643 `DiagnosticHandler`
    - 3644 `emit`
  - 3659 `updating`
  - 3667 `update_block`
  - 3673 `update_busy`
  - 3680 `restart_busy`
  - 3713 `update_gate`
  - 3720 `update_reopen`
  - 3724 `update_stop`
  - 3729 `perform_action_inner`
  - 3766 `operation_reply`
  - 3794 `finish_operation`
  - 3810 `perform_action`
  - 3855 `handle_load`
  - 3864 `ws_endpoint`
  - 3867 `simple_ws_endpoint`
  - 3870 `serve_ws`
    - 3880 `worker`
    - 3884 `spawn`
  - 3939 `no_cache`
  - 3960 `simple_index`
  - 3964 `simple_style`
  - 3968 `simple_script`
  - 3972 `simple_feedback_script`
  - 3976 `simple_health`
  - 3980 `update_health`
- 4000 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 4022 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 4034 `local_addresses`
- 4041 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 4061 `stop_running`
- 4073 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 4087 `main`

## ma2panel/browser_update.py
- 39 `trusted_url`
- 46 `GitHubRedirect`
  - 47 `redirect_request`
- 52 `_open`
- 57 `supported_platform`
- 61 `version_key`
- 78 `newer`
- 82 `download`
- 96 `fetch_json`
- 118 `release_info`
- 150 `latest`
- 197 `test_updates`
- 203 `verify_quality`
- 213 `status`
- 226 `progress`
- 234 `release_lock`
- 238 `prepare`
- 276 `launch`
- 293 `stop_child`
- 304 `health`
  - 308 `record`
- 341 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 343 `__init__`
  - 348 `start`
    - 352 `Handler`
      - 353 `log_message`
      - 356 `do_GET`
  - 390 `stop`
- 398 `apply`
- 453 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 474 `wait`
- 486 `worker`
- 505 `Updater`
  - 506 `__init__`
  - 511 `begin`
  - 520 `_run`
- 564 `recover_pending`
- 584 `watch_orphan`
- 615 `orphan_worker`
- 645 `register`
  - 650 `select`
  - 657 `local`
  - 668 `denied`
  - 672 `update_channel`
  - 678 `set_update_channel`
  - 694 `update_health`
  - 698 `update_status`
  - 704 `check_update`
  - 716 `updater_idle`
  - 722 `quiesce`
  - 731 `start_update`

## ma2panel/commands.py
- 35 `failure`
- 39 `ActionError`
  - 40 `__init__`
- 46 `nudge_step`
- 56 `_value`
- 63 `fade_suffix` — Programmer fade for dim and colour; "" when absent or 0. `At 50 Fade 2`: MA2 3.9 manual p.
- 71 `find`
- 78 `page_number`
- 85 `exec_page`
- 89 `store_lines` — No SaveShow: saving the whole show is the operator's decision, never the panel's.
- 97 `_reply_lines` — Ignore standalone prompts and List command echoes (possibly prefixed by a prompt).
- 105 `exec_verdict`
- 117 `unrecognised_lines`
- 130 `parse_executors` — (exec, label) from a `List Executor` reply. ponytail: reply format guessed, check in the h
- 141 `can_move` — Heads: explicit fixture attributes/flag, or Pan+Tilt from a current confirmed type.
- 148 `parse_ma2_objects` — Catalogue rows from the site's assumed List format; never infer fixture membership.
- 164 `group_slot_empty` — Only an explicit empty response is safe; echoes/prompts alone prove nothing.
- 178 `parse_running` — exec -> running, only for lines that carry a status word. ponytail: status word guessed, c
- 200 `movers`
- 205 `scale`
- 211 `attr_lines`
- 216 `head_lines` — Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line.
- 231 `select_line`
- 235 `apply_move`
- 241 `check_move`
- 249 `check_jog` — Joystick step in degrees since the last one: relative, so the desk and the panel can turn
- 259 `mirrored` — Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns
- 266 `pan_flip`
- 270 `rel_lines` — Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down)
- 287 `parse_label`
- 294 `build`
- 366 `targets`
- 377 `validate_hall`
- 396 `parse_positions` — x and y both null take the fixture off the plan, back to the tray.
- 428 `is_error_reply`
- 432 `load_config`
- 463 `absolute` — "1.289" -> 289, "2.001" -> 513.
- 469 `dmx_intervals` — Sorted (start, count) ranges, without reading holes in a sparse patch.
- 483 `dmx_span` — (first address, count) covering every patched fixture of the plan.
- 489 `dmx_lua` — One Lua line per chunk of DMX_CHUNK addresses.
- 496 `parse_dmx` — {absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out.
- 514 `live_from_dmx` — What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without
- 548 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 562 `dmx_text` — 289 -> "1.289".
- 567 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 575 `check_uid`
- 582 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 606 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
  - 628 `fits`
- 659 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 677 `parse_type_names` — Unique exact LongName -> number from the recorded MA2 FixtureType table.
- 695 `type_no`
- 700 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

## ma2panel/data_transfer.py
- 21 `_linked`
- 25 `_files`
- 32 `_private`
- 45 `_root`
- 52 `_name`
- 63 `_settled`
- 88 `backup`
- 132 `inspect`
- 161 `restore`
- 199 `main`

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
  - 182 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 204 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

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
- 183 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
  - 194 `unchanged`
- 279 `save_config`

## ma2panel/hall_trial.py


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
  - 129 `ready`
  - 133 `authenticated_socket` — The authenticated transport is still open, including before the drop callback.
  - 139 `connection_phase` — Operator-facing phase; the legacy transport state and send gate stay unchanged.
  - 152 `halted`
  - 156 `halted`
  - 161 `mask`
  - 164 `_set`
  - 170 `run`
  - 235 `_login` — logged_in only when the login reply has no error AND ListVar names the configured user.
  - 277 `_sleep` — Waits before the next attempt; link_connect cuts it short.
  - 285 `disconnect` — Closes only this bridge's Telnet session. The console, its network and other sessions are
  - 291 `connect`
  - 295 `new_action`
  - 298 `close`
  - 302 `_raw`
  - 305 `_result`
  - 309 `send` — (ok, reply or reason). ok means status "sent". gen: the link generation the caller started
  - 377 `_drain` — Late answer to a timed-out line, so it is not read as the next line's answer. True when it
  - 387 `_pump`
  - 400 `_exchange`
  - 412 `_collect` — (reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

## ma2panel/migrations.py
- 19 `_read`
- 28 `merge_settings` — Current site settings win at each leaf, without discarding legacy siblings.
- 38 `_backup`
- 48 `legacy_archive_path` — Raw unnamed legacy snapshots are backups, not owner-checked show plans.
- 61 `migrate_config` — Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

## ma2panel/mock.py
- 16 `MockMA2`
  - 17 `__init__`
  - 81 `output` — Small LTP/soft-transfer test model; not a console emulator or evidence.
  - 110 `configure_simulation` — Synthetic fixture-space output; never DMX or evidence from a console.
  - 133 `simulation_output`
  - 158 `_simulate`
  - 219 `_handle`
  - 258 `_wire`
  - 263 `_reply`
  - 276 `_answer`
  - 457 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 473 `drop`
- 478 `start_mock`

## ma2panel/mock_console.py
- 25 `is_read_only`
- 29 `validate`

## ma2panel/onboarding.py
- 11 `tablet_urls`
- 29 `register`
  - 32 `local`
  - 35 `urls`
  - 39 `status`
  - 51 `qr`

## ma2panel/quality_diagnostics.py
- 19 `digest`
- 23 `recovery_pending`
- 32 `capability`
- 67 `readiness`
  - 69 `add`
- 107 `_num`
- 111 `technical_attribute`
- 116 `_xml`
  - 119 `node`
- 144 `collect` — Allowlist numeric structure; no credentials, arbitrary strings, paths or logs.
- 223 `pack`
- 231 `register`
  - 235 `lifespan`
  - 249 `local`
  - 252 `status`
  - 257 `preview`
  - 268 `download`

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
  - 67 `add`
  - 82 `walk`
- 157 `identity`
- 172 `runtime`
- 190 `_json`
- 194 `build`
- 210 `write_zip`
- 221 `write_tree`
- 233 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 248 `_object`
- 257 `check`
- 264 `_check`
- 303 `_runtime_files`
- 319 `record_runtime`
- 323 `verify_runtime`

## ma2panel/release_quality.py
- 17 `fingerprint`
- 21 `check_link`
- 33 `validate`
- 55 `authenticate`
- 76 `validate_candidate`
- 96 `authenticate_candidate`
- 116 `verify_archive`

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

## ma2panel/scene_recovery.py
- 16 `journal_path`
- 20 `archived_journal_path`
- 24 `generation_path`
- 29 `read_record`
- 40 `SceneIdentityState`
  - 48 `require_confirmed`
- 58 `archive_fingerprint`
- 63 `scene_identity_state` — Read every record for the target. Only a verified generation can cover archives.
- 116 `recover_scene` — Only run with the bridge stopped, after an operator has verified Cue 1 on MA2.
  - 153 `check_plan`
- 168 `main`

## ma2panel/scene_runtime.py
- 9 `probe_command`
- 25 `is_probe_command`
- 31 `read_nonce`
- 44 `confirm_manual_scene`
- 61 `transition_lines`
- 71 `store_scene` — Prepare away from the live target. Keep the spare, including the old Cue 1.
- 89 `GrandMasterBlackout` — Snapshot/restore Grand, leaving the independent native B.O. mask untouched.
  - 95 `__init__`
  - 101 `read`
  - 112 `toggle`

## ma2panel/scenes.py
- 8 `canonical_exec`
- 17 `exec_key`
- 21 `ordered_scenes`
- 26 `identify_scenes` — Give legacy rows a persistent identity without changing their IDs.
- 39 `new_scene`
- 44 `merge_scenes`
- 60 `slot_candidates`

## ma2panel/selfcheck.py
- 16 `check`
- 21 `get`
- 26 `main` — Read cached readiness; never run WS actions or infer safety from missing logs.
- 46 `cli`

## ma2panel/show_files.py
- 15 `fingerprint`
- 19 `regular`
- 26 `validate`
- 42 `snapshot` — Exclusive verified copy; source must stay unchanged throughout the read.
- 74 `publish` — Publish complete file atomically without replacing any existing directory entry.

## ma2panel/show_plans.py
- 10 `read_plan` — Read the revision and owner from the same file contents.
- 24 `_plan_paths`
- 33 `_read_legacy`
- 43 `plan_path` — Prefer the canonical name, with a read-only owner-checked legacy fallback.
- 56 `auto_plan` — Resolve an existing plan with a revision, refusing conflicting same-owner copies.
- 71 `validate_auto_plan`
  - 72 `require`
  - 76 `rows`
  - 83 `positive`
  - 86 `named`
  - 89 `string_fields`

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
- 183 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 210 `remove`
- 217 `sync_directory`
- 226 `sync_tree`
- 239 `durable_replace`
- 254 `atomic_json`
- 265 `copy_entry`
- 276 `safe_targets`
- 285 `snapshot_meta`
- 295 `check_snapshot`
- 307 `restore_snapshot`
- 318 `transaction`
- 327 `process_alive`
- 354 `recover` — Restore an interrupted replacement before the bridge opens any interfaces.
- 395 `install`
- 460 `acquire_lock` — Publish an already populated owner directory atomically (also survives pre-status crashes)
- 477 `serialized`
  - 479 `call`
- 503 `rollback`
- 534 `run`
- 573 `main`

## ma2panel/windows_asyncio.py
- 16 `install_windows_transport_recovery`
  - 23 `delegate`
  - 29 `recover`
- 59 `_traceback_frames`

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
- 173 `hasFixtures`
- 174 `safe`
- 181 `linkLine`
- 193 `send`
- 228 `sendRaw`
- 242 `busy`
- 244 `feedback`
- 248 `renderOperationFeedback`
- 259 `notice`
- 277 `actionFeature`
- 281 `featureReason`
- 287 `go`
- 299 `render`
- 349 `renderBanners`
- 378 `renderSection`
- 427 `readFromMa2`
- 428 `fixtureImportComplete`
- 439 `fixtureImportChoices`
- 469 `SECTIONS.start`
- 522 `setupSteps`
- 538 `safetyText`
- 545 `ma2Card`
- 569 `pagesList`
- 574 `SECTIONS.prepare`
- 587 `SECTIONS.help`
- 598 `transitionControl`
- 611 `SECTIONS.scenes`
- 693 `masterControl`
- 712 `setFill`
- 717 `openSceneEdit`
- 746 `cancelStore`
- 750 `openStore`
- 790 `SECTIONS.history`
- 802 `SECTIONS.shows`
- 863 `discardPending`
- 877 `clearEvidence`
- 882 `sceneAllowed`
- 885 `sceneEvidence`
- 892 `valueFreshness`
- 895 `sentSource`
- 898 `sentStale`
- 901 `observeEvidence`
- 909 `expireEvidence`
- 930 `receive`
- 1076 `connect`
- 1104 `cancelSlider`
- 1111 `flushSliders`
- 1120 `throttleSlider`
- 1135 `selectConsoleGroup`
- 1144 `selectFixtures`

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
- 3 `readDisplayPrefs`
- 15 `toolVisible`
- 16 `panelToolVisible`
- 17 `saveDisplayPrefs`
- 20 `interfaceControls`
- 35 `refreshDisplayPrefs`

## static/static/light.js
- 15 `colorMode`
- 16 `supports`
- 27 `showTool`
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
- 300 `plural`
- 305 `sliderCard`
- 335 `hsv2rgb`
- 339 `rgb2hsv`
- 344 `cssRgb`
- 346 `colorCard`
- 477 `moveCard`

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
- 77 `hallPlan`
- 338 `tapFixture`
- 359 `planOrder`
- 360 `planCurrent`
- 366 `planLight`
- 371 `planNext`
- 385 `planStep`
- 394 `SECTIONS.hall`
- 474 `hallForm`
- 500 `groupSide`
- 526 `openGroupStore`
- 544 `beamCard`

## static/static/quality-diagnostics.js


## static/static/settings.js
- 7 `status`
- 8 `saved`
- 9 `clearErrors`
- 16 `fieldError`
- 26 `warning`
- 27 `csv`
- 28 `fill`
- 60 `load`
- 160 `importElement`
- 166 `importComplete`
- 178 `renderImportChoices`
- 232 `importResult`

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


