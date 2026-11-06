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
  - 182 `diagnostics`
  - 196 `upload_status`
  - 203 `upload_diagnostics`
    - 234 `private_names`
    - 252 `collect`
  - 265 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 306 `export_probe`
  - 325 `probe_console`
  - 342 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 346 `part`
    - 352 `read`

## ma2panel/bridge.py
- 56 `is_loopback`
- 75 `create_app`
  - 93 `get_config_attrs`
  - 96 `refresh_attr_names`
  - 104 `add_strobe_attrs`
  - 152 `revision_token`
  - 155 `ActionLock`
    - 156 `__aenter__`
    - 170 `__aexit__`
  - 202 `status_msg`
  - 210 `config_revision`
  - 217 `config_msg`
  - 231 `scenes_msg`
  - 235 `values_meta`
  - 245 `known_shown` — Only unexpired panel-sent attributes; this is never output readback.
  - 255 `invalidate_evidence`
  - 268 `shown_msg`
  - 274 `session_msg`
  - 279 `broadcast`
  - 295 `spawn_broadcast`
  - 300 `history_context`
  - 303 `history_reason`
  - 316 `history_msg`
  - 321 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 340 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 349 `light_what`
  - 354 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 368 `forget_positions`
  - 375 `highlight_zone`
  - 380 `highlight_status`
  - 385 `highlight_stuck`
  - 389 `highlight_record`
  - 395 `highlight_lines`
  - 421 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 467 `highlight_action`
  - 523 `highlight_disconnect`
  - 532 `highlight_lease`
  - 542 `show_from`
  - 551 `invalidate_profiles`
  - 571 `update_show`
  - 585 `identify_show`
  - 603 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 624 `spawn_capture`
  - 629 `on_state`
  - 658 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 687 `check_ids`
  - 694 `check_scene`
  - 698 `heads`
  - 704 `selected`
  - 710 `remember`
  - 742 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 852 `action_ticket`
  - 855 `ticket_valid`
  - 860 `execute` — Send the action's lines; None on success, else the error text.
  - 967 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 979 `swap_off`
  - 992 `throttled`
  - 1018 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1030 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1060 `layout_save`
  - 1069 `new_id`
  - 1073 `mover`
  - 1079 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1144 `scene_pages`
  - 1147 `list_cmd`
  - 1150 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1170 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1216 `expire_evidence`
  - 1232 `poll_dmx` — What the desk outputs, read by a Lua line every dmx_seconds: the plan shows every lit fixt
  - 1249 `expire_dmx`
  - 1265 `read_dmx` — One read; returns the wait before the next one, None when the desk refused the line.
  - 1349 `require_scene_context`
  - 1354 `confirm_scene_show`
  - 1363 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1391 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 1410 `send_ma2_lines`
  - 1420 `ma2_action`
  - 1530 `invalidate_scene_offers`
  - 1536 `offer_context`
  - 1539 `find_scene_slot`
    - 1544 `emit`
  - 1593 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1608 `record`
  - 1621 `show_name`
  - 1627 `plan_path`
  - 1630 `check_show`
  - 1637 `import_context`
  - 1640 `import_xml`
  - 1660 `confirm_import`
  - 1675 `commit_import`
  - 1696 `open_show_plan`
  - 1742 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1754 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1784 `fetch_fixtures`
    - 1789 `apply`
  - 1801 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 1823 `send`
    - 1867 `commit`
  - 1882 `require_patch_context`
  - 1886 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1908 `rdm_read`
  - 1923 `patch_offer`
  - 1930 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2066 `list_shows`
  - 2085 `load_show`
  - 2184 `handle`
  - 2633 `on_result`
  - 2650 `rdm_busy`
  - 2665 `ProtocolThrottle`
    - 2666 `clear`
  - 2681 `lifespan`
  - 2708 `mask`
  - 2711 `safe_data`
  - 2723 `DiagnosticHandler`
    - 2724 `emit`
  - 2739 `updating`
  - 2749 `update_busy`
  - 2756 `update_gate`
  - 2763 `update_reopen`
  - 2767 `update_stop`
  - 2772 `perform_action_inner`
  - 2809 `operation_reply`
  - 2821 `finish_operation`
  - 2837 `perform_action`
  - 2881 `handle_load`
  - 2890 `ws_endpoint`
  - 2893 `simple_ws_endpoint`
  - 2896 `serve_ws`
    - 2906 `worker`
    - 2910 `spawn`
  - 2961 `no_cache`
  - 2982 `simple_index`
  - 2986 `simple_style`
  - 2990 `simple_script`
  - 2994 `simple_feedback_script`
  - 2998 `simple_health`
  - 3002 `update_health`
- 3014 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3036 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3048 `local_addresses`
- 3055 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3075 `stop_running`
- 3087 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3100 `main`

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

## ma2panel/diagnostic_relay.py
- 11 `Relay`
  - 12 `put`

## ma2panel/diagnostic_setup.py
- 15 `_protect`
- 28 `configure` — Validate destination before replacing credentials; never print the token.
- 53 `main`

## ma2panel/diagnostic_upload.py
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

## ma2panel/exports.py
- 23 `bind`
  - 24 `export_folders` — Where an export may land: ma2.export_dir first, then every existing folder matching ma2.ex
  - 32 `listing`
  - 47 `save_diag_json`
  - 55 `export_type` — One Export FixtureType under a one-off name. The documentation puts fixture types in their
  - 96 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 125 `run_export`
  - 174 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 196 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

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
- 159 `runtime`
- 163 `_json`
- 167 `build`
- 178 `write_zip`
- 189 `write_tree`
- 201 `write_windows_launcher` — Stable outer entry point; updates keep operating inside program/.
- 216 `_object`
- 225 `check`
- 232 `_check`
- 271 `_runtime_files`
- 287 `record_runtime`
- 291 `verify_runtime`

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
- 38 `known`
- 49 `knownText`
- 54 `lightKey`
- 58 `unsupportedNote`
- 64 `fxName`
- 65 `allowedFixture`
- 66 `pickRow`
- 71 `SECTIONS.light`
- 250 `plural`
- 255 `sliderCard`
- 283 `hsv2rgb`
- 287 `rgb2hsv`
- 292 `cssRgb`
- 294 `colorCard`
- 418 `moveCard`

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
- 273 `movePresets`
- 309 `renderMove`

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
- 309 `tapFixture`
- 330 `planOrder`
- 331 `planCurrent`
- 337 `planLight`
- 342 `planNext`
- 356 `planStep`
- 365 `SECTIONS.hall`
- 445 `hallForm`
- 463 `groupSide`
- 489 `openGroupStore`
- 507 `beamCard`

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


