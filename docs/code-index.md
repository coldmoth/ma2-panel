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
  - 123 `put_settings`
  - 166 `restart`
  - 176 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 187 `diagnostics`
  - 199 `upload_status`
  - 206 `upload_diagnostics`
    - 237 `private_names`
    - 255 `collect`
  - 268 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 309 `export_probe`
  - 328 `probe_console`
  - 345 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 349 `part`
    - 355 `read`

## bridge.py
- 67 `is_loopback`
- 86 `create_app`
  - 106 `add_strobe_attrs`
  - 154 `revision_token`
  - 157 `ActionLock`
    - 158 `__aenter__`
    - 171 `__aexit__`
  - 196 `status_msg`
  - 204 `config_revision`
  - 211 `config_msg`
  - 224 `scenes_msg`
  - 228 `values_meta`
  - 232 `invalidate_evidence`
  - 245 `shown_msg`
  - 251 `session_msg`
  - 256 `broadcast`
  - 272 `spawn_broadcast`
  - 277 `history_msg`
  - 280 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 293 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 302 `light_what`
  - 307 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 321 `forget_positions`
  - 328 `highlight_zone`
  - 333 `highlight_status`
  - 338 `highlight_stuck`
  - 342 `highlight_record`
  - 348 `highlight_lines`
  - 369 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 408 `highlight_action`
  - 464 `highlight_disconnect`
  - 473 `highlight_lease`
  - 483 `show_from`
  - 492 `update_show`
  - 501 `identify_show`
  - 519 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 540 `spawn_capture`
  - 545 `on_state`
  - 572 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 602 `check_ids`
  - 609 `check_scene`
  - 613 `heads`
  - 619 `selected`
  - 625 `remember`
  - 656 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 763 `execute` — Send the action's lines; None on success, else the error text.
  - 811 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 823 `swap_off`
  - 833 `throttled`
  - 859 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 870 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 900 `layout_save`
  - 909 `new_id`
  - 913 `mover`
  - 919 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 984 `scene_pages`
  - 989 `list_cmd`
  - 992 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1003 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1049 `expire_evidence`
  - 1065 `poll_dmx` — What the desk outputs, read by a Lua line every dmx_seconds: the plan shows every lit fixt
  - 1082 `expire_dmx`
  - 1098 `read_dmx` — One read; returns the wait before the next one, None when the desk refused the line.
  - 1173 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1194 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 1213 `send_ma2_lines`
  - 1223 `ma2_action`
  - 1326 `invalidate_scene_offers`
  - 1332 `offer_context`
  - 1335 `find_scene_slot`
    - 1340 `emit`
  - 1389 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1404 `record`
  - 1417 `show_name`
  - 1423 `plan_path`
  - 1426 `check_show`
  - 1433 `import_context`
  - 1436 `import_xml`
  - 1455 `confirm_import`
  - 1469 `commit_import`
  - 1490 `open_show_plan`
  - 1533 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1545 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1575 `fetch_fixtures`
  - 1584 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
  - 1630 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1639 `rdm_read`
  - 1650 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 1717 `list_shows`
  - 1736 `load_show`
  - 1829 `handle`
  - 2248 `on_result`
  - 2265 `rdm_busy`
  - 2280 `ProtocolThrottle`
    - 2281 `clear`
  - 2296 `lifespan`
  - 2323 `mask`
  - 2326 `safe_data`
  - 2338 `DiagnosticHandler`
    - 2339 `emit`
  - 2354 `updating`
  - 2364 `update_busy`
  - 2370 `update_gate`
  - 2377 `update_reopen`
  - 2381 `update_stop`
  - 2386 `perform_action_inner`
  - 2424 `operation_reply`
  - 2435 `finish_operation`
  - 2451 `perform_action`
  - 2495 `handle_load`
  - 2504 `ws_endpoint`
  - 2507 `simple_ws_endpoint`
  - 2510 `serve_ws`
    - 2520 `worker`
    - 2524 `spawn`
  - 2575 `no_cache`
  - 2595 `simple_index`
  - 2599 `simple_style`
  - 2603 `simple_script`
  - 2607 `simple_health`
  - 2611 `update_health`
- 2623 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 2645 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 2657 `local_addresses`
- 2664 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 2684 `stop_running`
- 2696 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 2709 `main`

## browser_update.py
- 27 `download`
- 38 `fetch_json`
- 54 `latest`
- 69 `status`
- 82 `progress`
- 90 `release_lock`
- 94 `prepare`
- 119 `launch`
- 130 `stop_child`
- 141 `health`
- 157 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 159 `__init__`
  - 164 `start`
    - 168 `Handler`
      - 169 `log_message`
      - 172 `do_GET`
  - 206 `stop`
- 214 `apply`
- 267 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 288 `wait`
- 300 `worker`
- 319 `Updater`
  - 320 `__init__`
  - 324 `begin`
  - 333 `_run`
- 372 `recover_pending`
- 392 `watch_orphan`
- 415 `orphan_worker`
- 445 `register`
  - 451 `local`
  - 462 `denied`
  - 466 `update_health`
  - 470 `update_status`
  - 476 `check_update`
  - 487 `updater_idle`
  - 493 `quiesce`
  - 502 `start_update`

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
- 107 `parse_executors` — (exec, label) from a `List Executor` reply. ponytail: reply format guessed, check in the h
- 118 `can_move` — Heads: the old moves flag, or Pan/Tilt among the parameters read from the MA2 export.
- 123 `parse_ma2_objects` — Catalogue rows from the site's assumed List format; never infer fixture membership.
- 139 `group_slot_empty` — Only an explicit empty response is safe; echoes/prompts alone prove nothing.
- 153 `parse_running` — exec -> running, only for lines that carry a status word. ponytail: status word guessed, c
- 167 `movers`
- 172 `scale`
- 178 `attr_lines`
- 183 `head_lines` — Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line.
- 198 `select_line`
- 202 `apply_move`
- 208 `check_move`
- 216 `check_jog` — Joystick step in degrees since the last one: relative, so the desk and the panel can turn
- 226 `mirrored` — Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns
- 233 `pan_flip`
- 237 `rel_lines` — Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down)
- 254 `parse_label`
- 261 `build`
- 333 `targets`
- 344 `validate_hall`
- 358 `parse_positions` — x and y both null take the fixture off the plan, back to the tray.
- 390 `is_error_reply`
- 394 `load_config`
- 425 `absolute` — "1.289" -> 289, "2.001" -> 513.
- 431 `dmx_intervals` — Sorted (start, count) ranges, without reading holes in a sparse patch.
- 445 `dmx_span` — (first address, count) covering every patched fixture of the plan.
- 451 `dmx_lua` — One Lua line per chunk of DMX_CHUNK addresses.
- 456 `parse_dmx` — {absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out.
- 469 `live_from_dmx` — What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without
- 490 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 504 `dmx_text` — 289 -> "1.289".
- 509 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 517 `check_uid`
- 524 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 546 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
- 577 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 594 `type_no`
- 599 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

## diagnostic_relay.py
- 11 `Relay`
  - 12 `put`

## diagnostic_setup.py
- 15 `_protect`
- 28 `configure` — Validate destination before replacing credentials; never print the token.
- 53 `main`

## diagnostic_upload.py
- 38 `UploadError`
  - 39 `__init__`
- 45 `_uuid`
- 56 `marker`
- 60 `_number`
- 67 `build_report`
  - 71 `clean`
  - 76 `choice`
- 139 `collect_report` — Reuse startup captures as explicitly historical evidence; never run a probe.
- 187 `Github`
  - 188 `__init__`
  - 191 `request`
  - 232 `check_private`
  - 237 `find`
  - 261 `create`
- 270 `Uploader`
  - 271 `__init__`
  - 277 `_credentials`
  - 291 `_load`
  - 317 `_save`
  - 341 `_process_lock`
  - 369 `_result`
  - 386 `enqueue` — Persist explicit consent and a snapshot without making any network request.
  - 425 `retry` — Deliver only explicitly queued reports; uncertain POSTs remain GET-only.
  - 455 `wake`
  - 459 `run`
  - 468 `status`
  - 485 `submit`
  - 504 `_uses_relay`
  - 510 `_direct_credentials`
  - 518 `_submit_relay`
  - 551 `_submit`

## exports.py
- 22 `bind`
  - 23 `export_folders` — Where an export may land: ma2.export_dir first, then every existing folder matching ma2.ex
  - 31 `listing`
  - 46 `save_diag_json`
  - 54 `export_type` — One Export FixtureType under a one-off name. The documentation puts fixture types in their
  - 91 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 120 `run_export`
  - 166 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 188 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

## firewall.py
- 7 `apply`

## fixtures.py
- 9 `local`
- 13 `describe` — What the file contains, for the error text and the diagnostics: the real MA2 XML layout ha
- 24 `dmx_address` — "200" -> "1.200", as List Fixture shows it. ponytail: absolute address assumed ((universe-
- 37 `guess_head`
- 41 `parse_group_export` — {group number: [fixture ids]} from an `Export Group` XML. listed: {n: name} from List Grou
- 62 `parse_export` — Fixtures with a Fixture ID. skipped, if given, gets the names of <Fixture> entries without
- 106 `parse_fixture_type` — {dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<C
- 148 `merge_fixtures` — Preserve placement; only a one-to-one name/type match can be automatic.
- 201 `save_config`

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
  - 320 `_drain` — Late answer to a timed-out line, so it is not read as the next line's answer. True when it
  - 330 `_pump`
  - 343 `_exchange`
  - 355 `_collect` — (reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

## migrations.py
- 19 `_read`
- 28 `merge_settings` — Current site settings win at each leaf, without discarding legacy siblings.
- 38 `_backup`
- 48 `legacy_archive_path` — Raw unnamed legacy snapshots are backups, not owner-checked show plans.
- 61 `migrate_config` — Return ``(config, settings)`` after validated, backed-up v1..v4 migration.

## mock.py
- 14 `MockMA2`
  - 15 `__init__`
  - 61 `_handle`
  - 93 `_wire`
  - 98 `_reply`
  - 104 `_answer`
  - 227 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 243 `drop`
- 248 `start_mock`

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
- 15 `RuntimeMismatch`
- 19 `_path`
- 38 `_names`
- 51 `payload`
  - 57 `add`
- 105 `identity`
- 119 `runtime`
- 123 `_json`
- 127 `build`
- 138 `write_zip`
- 149 `write_tree`
- 161 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 176 `_object`
- 185 `check`
- 192 `_check`
- 231 `_runtime_files`
- 247 `record_runtime`
- 251 `verify_runtime`

## safety.py
- 70 `load_secret` — Password from the MA2_PASSWORD variable or secret.env (one line MA2_PASSWORD=...). Never g
- 83 `load_settings`
- 95 `effective_safety`
- 108 `redact` — Hide the password in diagnostics without eating ordinary text.
- 120 `make_guard` — guard(line) -> None when the line may be sent, else the reason it is blocked.
  - 142 `guard`
- 215 `without_passwords`
- 223 `validate_settings` — Validate the entire replacement before touching disk or the running link.

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
- 66 `normalize_url`
- 77 `download`
- 89 `settings`
- 94 `version`
- 99 `idle`
- 109 `prepare_bridge`
- 137 `local_archive` — An update zip from a USB stick; a .sha256 next to it is checked when present.
- 152 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 179 `remove`
- 186 `sync_directory`
- 195 `sync_tree`
- 208 `durable_replace`
- 223 `atomic_json`
- 234 `copy_entry`
- 245 `safe_targets`
- 254 `snapshot_meta`
- 264 `check_snapshot`
- 276 `restore_snapshot`
- 287 `transaction`
- 296 `process_alive`
- 323 `recover` — Restore an interrupted replacement before the bridge opens any interfaces.
- 364 `install`
- 429 `acquire_lock` — Publish an already populated owner directory atomically (also survives pre-status crashes)
- 446 `serialized`
  - 448 `call`
- 472 `rollback`
- 503 `run`
- 542 `main`

## static/app.js
- 16 `captureRevision`
- 24 `pumpConfigQueue`
- 43 `on`
- 49 `h`
- 64 `add`
- 81 `icon`
- 88 `pageOf`
- 89 `bridgeUp`
- 91 `linkReady`
- 92 `connected`
- 93 `fixtures`
- 94 `fixture`
- 96 `canMove`
- 97 `hasFixtures`
- 98 `safe`
- 105 `linkLine`
- 115 `send`
- 133 `sendRaw`
- 140 `busy`
- 142 `feedback`
- 146 `notice`
- 155 `actionFeature`
- 159 `featureReason`
- 165 `go`
- 175 `render`
- 216 `renderBanners`
- 241 `renderSection`
- 283 `readFromMa2`
- 284 `fixtureImportComplete`
- 295 `fixtureImportChoices`
- 325 `SECTIONS.start`
- 374 `setupSteps`
- 390 `safetyText`
- 397 `ma2Card`
- 421 `pagesList`
- 425 `SECTIONS.scenes`
- 466 `masterControl`
- 484 `setFill`
- 489 `openSceneEdit`
- 516 `cancelStore`
- 520 `openStore`
- 557 `SECTIONS.history`
- 569 `SECTIONS.shows`
- 630 `discardPending`
- 639 `clearEvidence`
- 644 `sceneAllowed`
- 647 `sceneEvidence`
- 654 `valueFreshness`
- 657 `sentSource`
- 660 `observeEvidence`
- 668 `expireEvidence`
- 684 `receive`
- 799 `connect`
- 827 `cancelSlider`
- 834 `flushSliders`
- 843 `throttleSlider`
- 858 `selectFixtures`

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

## static/light.js
- 15 `colorMode`
- 16 `supports`
- 22 `selected`
- 23 `attributeVisible`
- 32 `split`
- 37 `known`
- 48 `knownText`
- 53 `lightKey`
- 57 `unsupportedNote`
- 63 `fxName`
- 64 `allowedFixture`
- 65 `pickRow`
- 70 `SECTIONS.light`
- 193 `plural`
- 198 `sliderCard`
- 226 `hsv2rgb`
- 230 `rgb2hsv`
- 235 `cssRgb`
- 237 `colorCard`
- 361 `moveCard`

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
- 273 `movePresets`
- 309 `renderMove`

## static/patch.js
- 5 `patchKey`
- 40 `dmxText`
- 41 `closeDialog`
- 43 `rdmSearchPending`
- 44 `rdmSearchBusy`
- 45 `rdmSearchBegin`
- 51 `rdmRecoveryText`
- 54 `rdmSearchBanner`
- 62 `rdmResults`
- 66 `rdmCard`
- 100 `patchTable`
- 118 `patchPick`
- 124 `patchEditor`
- 157 `patchDialog`
- 183 `patchResult`
- 193 `SECTIONS.patch`

## static/plan.js
- 6 `planKind`
- 13 `placed`
- 14 `hallOf`
- 15 `planKey`
- 21 `planBeginEdit`
- 28 `stopPing`
- 33 `planEndEdit`
- 41 `highlightOn`
- 58 `hallPlan`
- 195 `tapFixture`
- 216 `planOrder`
- 217 `planCurrent`
- 223 `planLight`
- 228 `planNext`
- 242 `planStep`
- 251 `SECTIONS.hall`
- 326 `hallForm`
- 344 `groupSide`
- 370 `openGroupStore`
- 388 `beamCard`

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


