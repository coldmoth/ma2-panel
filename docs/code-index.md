# Индекс функций

Собрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.

## api.py
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
  - 195 `upload_status`
  - 202 `upload_diagnostics`
    - 233 `private_names`
    - 252 `collect`
  - 266 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 307 `export_probe`
  - 326 `probe_console`
  - 343 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 347 `part`
    - 353 `read`

## bridge.py
- 69 `is_loopback`
- 88 `create_app`
  - 106 `get_config_attrs`
  - 109 `refresh_attr_names`
  - 117 `add_strobe_attrs`
  - 166 `revision_token`
  - 169 `ActionLock`
    - 170 `__aenter__`
    - 184 `__aexit__`
  - 216 `status_msg`
  - 224 `config_revision`
  - 231 `config_msg`
  - 245 `scenes_msg`
  - 249 `values_meta`
  - 259 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 269 `invalidate_evidence`
  - 282 `shown_msg`
  - 288 `session_msg`
  - 293 `broadcast`
  - 309 `spawn_broadcast`
  - 314 `history_context`
  - 317 `history_reason`
  - 330 `history_msg`
  - 335 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 354 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 363 `light_what`
  - 368 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
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
  - 587 `update_show`
  - 601 `identify_show`
  - 619 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 640 `spawn_capture`
  - 645 `on_state`
  - 674 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 703 `check_ids`
  - 710 `check_scene`
  - 714 `heads`
  - 720 `selected`
  - 726 `remember`
  - 758 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 868 `action_ticket`
  - 871 `ticket_valid`
  - 876 `execute` — Send the action's lines; None on success, else the error text.
  - 983 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 995 `swap_off`
  - 1008 `throttled`
  - 1034 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1046 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1076 `layout_save`
  - 1085 `new_id`
  - 1089 `mover`
  - 1095 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1160 `scene_pages`
  - 1163 `list_cmd`
  - 1166 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1186 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1232 `expire_evidence`
  - 1248 `poll_dmx` — What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan s
  - 1262 `expire_dmx`
  - 1278 `read_dmx` — One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset.
  - 1388 `require_scene_context`
  - 1393 `confirm_scene_show`
  - 1402 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1430 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 1449 `send_ma2_lines`
  - 1459 `ma2_action`
  - 1569 `invalidate_scene_offers`
  - 1575 `offer_context`
  - 1578 `find_scene_slot`
    - 1583 `emit`
  - 1632 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1647 `record`
  - 1660 `show_name`
  - 1666 `plan_path`
  - 1669 `check_show`
  - 1676 `import_context`
  - 1679 `import_xml`
  - 1699 `confirm_import`
  - 1714 `commit_import`
  - 1735 `open_show_plan`
  - 1781 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1793 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1823 `fetch_fixtures`
    - 1828 `apply`
  - 1840 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 1862 `send`
    - 1871 `can_retry`
    - 1875 `failed`
    - 1920 `commit`
  - 1935 `require_patch_context`
  - 1939 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1961 `rdm_read`
  - 1976 `patch_offer`
  - 1983 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2119 `list_shows`
  - 2138 `load_show`
  - 2237 `handle`
  - 2686 `on_result`
  - 2703 `rdm_busy`
  - 2718 `ProtocolThrottle`
    - 2719 `clear`
  - 2734 `lifespan`
  - 2761 `mask`
  - 2764 `safe_data`
  - 2776 `DiagnosticHandler`
    - 2777 `emit`
  - 2792 `updating`
  - 2802 `update_busy`
  - 2809 `update_gate`
  - 2816 `update_reopen`
  - 2820 `update_stop`
  - 2825 `perform_action_inner`
  - 2862 `operation_reply`
  - 2874 `finish_operation`
  - 2890 `perform_action`
  - 2934 `handle_load`
  - 2943 `ws_endpoint`
  - 2946 `simple_ws_endpoint`
  - 2949 `serve_ws`
    - 2959 `worker`
    - 2963 `spawn`
  - 3014 `no_cache`
  - 3035 `simple_index`
  - 3039 `simple_style`
  - 3043 `simple_script`
  - 3047 `simple_feedback_script`
  - 3051 `simple_health`
  - 3055 `update_health`
- 3067 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3089 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3101 `local_addresses`
- 3108 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3128 `stop_running`
- 3140 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3153 `main`

## browser_update.py
- 29 `trusted_url`
- 36 `GitHubRedirect`
  - 37 `redirect_request`
- 42 `_open`
- 47 `supported_platform`
- 51 `version_key`
- 59 `newer`
- 63 `download`
- 77 `fetch_json`
- 99 `latest`
- 126 `status`
- 139 `progress`
- 147 `release_lock`
- 151 `prepare`
- 185 `launch`
- 196 `stop_child`
- 207 `health`
  - 211 `record`
- 244 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 246 `__init__`
  - 251 `start`
    - 255 `Handler`
      - 256 `log_message`
      - 259 `do_GET`
  - 293 `stop`
- 301 `apply`
- 354 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 375 `wait`
- 387 `worker`
- 406 `Updater`
  - 407 `__init__`
  - 411 `begin`
  - 420 `_run`
- 461 `recover_pending`
- 481 `watch_orphan`
- 504 `orphan_worker`
- 534 `register`
  - 540 `local`
  - 551 `denied`
  - 555 `update_health`
  - 559 `update_status`
  - 565 `check_update`
  - 577 `updater_idle`
  - 583 `quiesce`
  - 592 `start_update`

## commands.py
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

## diagnostic_readback.py
- 6 `_number`
- 12 `_errors`
- 16 `build_readback`
- 107 `_valid`
- 129 `valid_readback`

## diagnostic_relay.py
- 11 `Relay`
  - 12 `put`

## diagnostic_setup.py
- 15 `_protect`
- 28 `configure` — Validate destination before replacing credentials; never print the token.
- 53 `main`

## diagnostic_upload.py
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

## exports.py
- 23 `bind`
  - 24 `export_folders` — Where an export may land: ma2.export_dir first, then every existing folder matching ma2.ex
  - 36 `listing`
  - 51 `save_diag_json`
  - 59 `export_type` — One Export FixtureType under a one-off name. The documentation puts fixture types in their
  - 100 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 129 `run_export`
  - 178 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 200 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

## firewall.py
- 7 `apply`

## fixtures.py
- 9 `local`
- 13 `describe` — What the file contains, for the error text and the diagnostics: the real MA2 XML layout ha
- 24 `dmx_address` — "200" -> "1.200", as List Fixture shows it. ponytail: absolute address assumed ((universe-
- 37 `guess_head`
- 41 `parse_group_export` — {group number: [fixture ids]} from an `Export Group` XML. listed: {n: name} from List Grou
- 62 `parse_export` — Fixtures with a Fixture ID. skipped, if given, gets the names of <Fixture> entries without
- 108 `parse_fixture_type` — {dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<C
- 152 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
- 210 `save_config`

## link.py
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

## migrations.py
- 19 `_read`
- 28 `merge_settings` — Current site settings win at each leaf, without discarding legacy siblings.
- 38 `_backup`
- 48 `legacy_archive_path` — Raw unnamed legacy snapshots are backups, not owner-checked show plans.
- 61 `migrate_config` — Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

## mock.py
- 14 `MockMA2`
  - 15 `__init__`
  - 63 `_handle`
  - 102 `_wire`
  - 107 `_reply`
  - 113 `_answer`
  - 241 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 257 `drop`
- 262 `start_mock`

## onboarding.py
- 11 `tablet_urls`
- 29 `register`
  - 32 `local`
  - 35 `urls`
  - 39 `status`
  - 51 `qr`

## rdm_search.py
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

## release.py
- 17 `RuntimeMismatch`
- 21 `_path`
- 40 `_names`
- 53 `payload`
  - 59 `add`
- 132 `identity`
- 146 `runtime`
- 150 `_json`
- 154 `build`
- 165 `write_zip`
- 176 `write_tree`
- 188 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 203 `_object`
- 212 `check`
- 219 `_check`
- 258 `_runtime_files`
- 274 `record_runtime`
- 278 `verify_runtime`

## safety.py
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

## scenes.py
- 7 `canonical_exec`
- 16 `exec_key`
- 20 `ordered_scenes`
- 25 `merge_scenes`
- 47 `slot_candidates`

## selfcheck.py
- 20 `check`
- 25 `get`
- 30 `log_lines`
- 35 `ask`
- 45 `fixtures_report`
- 60 `main`
- 100 `cli`

## show_files.py
- 15 `fingerprint`
- 19 `regular`
- 26 `validate`
- 42 `snapshot` — Exclusive verified copy; source must stay unchanged throughout the read.
- 74 `publish` — Publish complete file atomically without replacing any existing directory entry.

## show_plans.py
- 8 `_owner`
- 18 `plan_path` — Use a bounded ASCII SHA256 name; legacy names are read only and owner-checked.

## show_transfer.py
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

## status_evidence.py
- 5 `Evidence`
  - 6 `__init__`
  - 10 `observe`
  - 13 `invalidate`
  - 20 `snapshot`

## update.py
- 21 `UpdateError`
- 25 `allowed`
- 38 `validate_zip`
- 71 `normalize_url`
- 82 `download`
- 94 `settings`
- 99 `version`
- 104 `idle`
- 114 `prepare_bridge`
- 142 `local_archive` — An update zip from a USB stick; a .sha256 next to it is checked when present.
- 157 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 184 `remove`
- 191 `sync_directory`
- 200 `sync_tree`
- 213 `durable_replace`
- 228 `atomic_json`
- 239 `copy_entry`
- 250 `safe_targets`
- 259 `snapshot_meta`
- 269 `check_snapshot`
- 281 `restore_snapshot`
- 292 `transaction`
- 301 `process_alive`
- 328 `recover` — Restore an interrupted replacement before the bridge opens any interfaces.
- 369 `install`
- 434 `acquire_lock` — Publish an already populated owner directory atomically (also survives pre-status crashes)
- 451 `serialized`
  - 453 `call`
- 477 `rollback`
- 508 `run`
- 547 `main`

## static/app.js
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

## static/command-feedback.js
- 2 `commandOperationName`
- 20 `commandFeedback`
- 47 `commandWaiting`
- 58 `commandWaitMs`

## static/diag-upload.js


## static/diag.js
- 8 `replyList`
- 18 `refresh`
- 41 `exportText`
- 56 `showExport`
- 64 `runRead`
- 70 `runLink`
- 76 `runExport`
- 82 `guarded`

## static/interface.js
- 4 `panelReadTools`
- 8 `panelToolVisible`
- 10 `panelRefreshTools`

## static/light.js
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

## static/move.js
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

## static/patch.js
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

## static/plan.js
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

## static/settings.js
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

## static/setup.js


## static/show-files.js
- 4 `showFilesPaint`
- 5 `showFilesRemember`
- 6 `showFilesRequest`
- 15 `showFilesPoll`
- 22 `showFilesRefresh`
- 37 `showFilesConfirm`
- 55 `showFilesPrepare`
- 66 `showFilesUpload`
- 81 `showFilesCard`

## static/simple.js


## static/update.js


