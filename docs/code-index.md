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
  - 168 `restart`
  - 178 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 190 `diagnostics`
  - 204 `upload_status`
  - 211 `upload_diagnostics`
    - 242 `private_names`
    - 261 `collect`
  - 275 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 316 `export_probe`
  - 335 `probe_console`
  - 352 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 356 `part`
    - 362 `read`
  - 402 `quality_snapshot`

## ma2panel/bridge.py
- 61 `is_loopback`
- 81 `create_app`
  - 99 `get_config_attrs`
  - 102 `refresh_attr_names`
  - 110 `add_strobe_attrs`
  - 163 `revision_token`
  - 166 `ActionLock`
    - 167 `__aenter__`
    - 181 `__aexit__`
  - 213 `status_msg`
  - 221 `config_revision`
  - 228 `config_msg`
  - 242 `scenes_msg`
  - 246 `values_meta`
  - 256 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 266 `invalidate_evidence`
  - 279 `shown_msg`
  - 286 `session_msg`
  - 291 `broadcast`
  - 307 `spawn_broadcast`
  - 312 `history_context`
  - 315 `history_reason`
  - 330 `history_msg`
  - 335 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 355 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 364 `light_what`
  - 369 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 384 `forget_positions`
  - 391 `highlight_zone`
  - 396 `highlight_status`
  - 401 `highlight_stuck`
  - 405 `highlight_record`
  - 411 `highlight_lines`
  - 437 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 483 `highlight_action`
  - 539 `highlight_disconnect`
  - 548 `highlight_lease`
  - 558 `show_from`
  - 567 `invalidate_profiles`
  - 593 `update_show`
  - 607 `identify_show`
  - 646 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 667 `spawn_capture`
  - 672 `on_state`
  - 710 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 749 `check_ids`
  - 756 `check_scene`
  - 760 `heads`
  - 766 `selected`
  - 772 `remember`
  - 802 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 916 `owned_scene_execs`
  - 928 `action_ticket`
  - 931 `ticket_valid`
  - 936 `execute` — Send the action's lines; None on success, else the error text.
  - 1098 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 1110 `throttled`
  - 1136 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1148 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1178 `layout_save`
  - 1187 `new_id`
  - 1191 `mover`
  - 1197 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1262 `scene_pages`
  - 1265 `list_cmd`
  - 1268 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1288 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1334 `expire_evidence`
  - 1350 `poll_simulation`
  - 1359 `poll_dmx` — What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan s
  - 1378 `poll_types` — Profile discovery remains available when live DMX readback is disabled.
  - 1396 `expire_dmx`
  - 1412 `dmx_diagnostics` — Local, read-only snapshot. Never treats cached/sent values as actual output.
  - 1464 `read_dmx` — One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset.
  - 1589 `require_scene_context`
  - 1594 `confirm_scene_show`
  - 1603 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1631 `catalogue_meta`
  - 1638 `read_ma2` — All pools must be complete; errors never turn a previous catalogue into empty.
  - 1676 `send_ma2_lines`
  - 1690 `ma2_action`
  - 1830 `invalidate_scene_offers`
  - 1836 `offer_context`
  - 1839 `find_scene_slot`
    - 1844 `emit`
  - 1893 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1908 `record`
  - 1921 `show_name`
  - 1927 `plan_path`
  - 1930 `check_show`
  - 1939 `confirm_write_show` — A fresh read under action_lock before scene mutations, never auto-bind.
  - 1947 `import_context`
  - 1950 `import_xml`
  - 1969 `confirm_import`
  - 1987 `commit_import`
  - 2029 `open_show_plan`
  - 2075 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 2087 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 2117 `fetch_fixtures`
    - 2122 `apply`
  - 2134 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 2138 `validate_editor`
    - 2164 `send`
    - 2175 `can_retry`
    - 2179 `failed`
    - 2186 `read_type_table`
    - 2241 `commit`
  - 2259 `require_patch_context`
  - 2263 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 2285 `rdm_read`
  - 2300 `patch_offer`
  - 2307 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2446 `list_shows`
  - 2465 `load_show`
  - 2564 `handle`
  - 3118 `on_result`
  - 3135 `rdm_busy`
  - 3150 `ProtocolThrottle`
    - 3151 `clear`
  - 3166 `lifespan`
  - 3198 `mask`
  - 3201 `safe_data`
  - 3213 `DiagnosticHandler`
    - 3214 `emit`
  - 3229 `updating`
  - 3239 `update_busy`
  - 3246 `update_gate`
  - 3253 `update_reopen`
  - 3257 `update_stop`
  - 3262 `perform_action_inner`
  - 3299 `operation_reply`
  - 3311 `finish_operation`
  - 3327 `perform_action`
  - 3371 `handle_load`
  - 3380 `ws_endpoint`
  - 3383 `simple_ws_endpoint`
  - 3386 `serve_ws`
    - 3396 `worker`
    - 3400 `spawn`
  - 3451 `no_cache`
  - 3472 `simple_index`
  - 3476 `simple_style`
  - 3480 `simple_script`
  - 3484 `simple_feedback_script`
  - 3488 `simple_health`
  - 3492 `update_health`
- 3505 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3527 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3539 `local_addresses`
- 3546 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3566 `stop_running`
- 3578 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3591 `main`

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
- 121 `can_move` — Heads: explicit fixture attributes/flag, or Pan+Tilt from a current confirmed type.
- 128 `parse_ma2_objects` — Catalogue rows from the site's assumed List format; never infer fixture membership.
- 144 `group_slot_empty` — Only an explicit empty response is safe; echoes/prompts alone prove nothing.
- 158 `parse_running` — exec -> running, only for lines that carry a status word. ponytail: status word guessed, c
- 180 `movers`
- 185 `scale`
- 191 `attr_lines`
- 196 `head_lines` — Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line.
- 211 `select_line`
- 215 `apply_move`
- 221 `check_move`
- 229 `check_jog` — Joystick step in degrees since the last one: relative, so the desk and the panel can turn
- 239 `mirrored` — Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns
- 246 `pan_flip`
- 250 `rel_lines` — Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down)
- 267 `parse_label`
- 274 `build`
- 346 `targets`
- 357 `validate_hall`
- 371 `parse_positions` — x and y both null take the fixture off the plan, back to the tray.
- 403 `is_error_reply`
- 407 `load_config`
- 438 `absolute` — "1.289" -> 289, "2.001" -> 513.
- 444 `dmx_intervals` — Sorted (start, count) ranges, without reading holes in a sparse patch.
- 458 `dmx_span` — (first address, count) covering every patched fixture of the plan.
- 464 `dmx_lua` — One Lua line per chunk of DMX_CHUNK addresses.
- 471 `parse_dmx` — {absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out.
- 489 `live_from_dmx` — What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without
- 523 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 537 `dmx_text` — 289 -> "1.289".
- 542 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 550 `check_uid`
- 557 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 581 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
  - 603 `fits`
- 634 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 652 `parse_type_names` — Unique exact LongName -> number from the recorded MA2 FixtureType table.
- 670 `type_no`
- 675 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

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
- 183 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
  - 194 `unchanged`
- 279 `save_config`

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
  - 59 `add`
  - 72 `walk`
- 145 `identity`
- 160 `runtime`
- 178 `_json`
- 182 `build`
- 198 `write_zip`
- 209 `write_tree`
- 221 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 236 `_object`
- 245 `check`
- 252 `_check`
- 291 `_runtime_files`
- 307 `record_runtime`
- 311 `verify_runtime`

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
- 691 `masterControl`
- 710 `setFill`
- 715 `openSceneEdit`
- 744 `cancelStore`
- 748 `openStore`
- 788 `SECTIONS.history`
- 800 `SECTIONS.shows`
- 861 `discardPending`
- 875 `clearEvidence`
- 880 `sceneAllowed`
- 883 `sceneEvidence`
- 890 `valueFreshness`
- 893 `sentSource`
- 896 `sentStale`
- 899 `observeEvidence`
- 907 `expireEvidence`
- 928 `receive`
- 1074 `connect`
- 1102 `cancelSlider`
- 1109 `flushSliders`
- 1118 `throttleSlider`
- 1133 `selectConsoleGroup`
- 1142 `selectFixtures`

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


