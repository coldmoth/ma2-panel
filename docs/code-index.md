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
  - 182 `diagnostics`
  - 194 `upload_status`
  - 201 `upload_diagnostics`
    - 232 `private_names`
    - 250 `collect`
  - 263 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 304 `export_probe`
  - 323 `probe_console`
  - 340 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 344 `part`
    - 350 `read`

## bridge.py
- 67 `is_loopback`
- 86 `create_app`
  - 104 `get_config_attrs`
  - 107 `refresh_attr_names`
  - 115 `add_strobe_attrs`
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
  - 285 `session_msg`
  - 290 `broadcast`
  - 306 `spawn_broadcast`
  - 311 `history_context`
  - 314 `history_reason`
  - 327 `history_msg`
  - 332 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 351 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 360 `light_what`
  - 365 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 379 `forget_positions`
  - 386 `highlight_zone`
  - 391 `highlight_status`
  - 396 `highlight_stuck`
  - 400 `highlight_record`
  - 406 `highlight_lines`
  - 432 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 478 `highlight_action`
  - 534 `highlight_disconnect`
  - 543 `highlight_lease`
  - 553 `show_from`
  - 562 `invalidate_profiles`
  - 582 `update_show`
  - 596 `identify_show`
  - 614 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 635 `spawn_capture`
  - 640 `on_state`
  - 669 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 698 `check_ids`
  - 705 `check_scene`
  - 709 `heads`
  - 715 `selected`
  - 721 `remember`
  - 753 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 863 `action_ticket`
  - 866 `ticket_valid`
  - 871 `execute` — Send the action's lines; None on success, else the error text.
  - 978 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 990 `swap_off`
  - 1003 `throttled`
  - 1029 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 1041 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 1071 `layout_save`
  - 1080 `new_id`
  - 1084 `mover`
  - 1090 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 1155 `scene_pages`
  - 1158 `list_cmd`
  - 1161 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 1181 `poll_running` — One shared reader. Exact configured addresses avoid guessed range boundaries.
  - 1227 `expire_evidence`
  - 1243 `poll_dmx` — What the desk outputs, read by a Lua line every dmx_seconds: the plan shows every lit fixt
  - 1260 `expire_dmx`
  - 1276 `read_dmx` — One read; returns the wait before the next one, None when the desk refused the line.
  - 1360 `require_scene_context`
  - 1365 `confirm_scene_show`
  - 1374 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 1402 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 1421 `send_ma2_lines`
  - 1431 `ma2_action`
  - 1541 `invalidate_scene_offers`
  - 1547 `offer_context`
  - 1550 `find_scene_slot`
    - 1555 `emit`
  - 1604 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1619 `record`
  - 1632 `show_name`
  - 1638 `plan_path`
  - 1641 `check_show`
  - 1648 `import_context`
  - 1651 `import_xml`
  - 1671 `confirm_import`
  - 1686 `commit_import`
  - 1707 `open_show_plan`
  - 1753 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1765 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1795 `fetch_fixtures`
    - 1800 `apply`
  - 1812 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
    - 1834 `send`
    - 1878 `commit`
  - 1893 `require_patch_context`
  - 1897 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1919 `rdm_read`
  - 1934 `patch_offer`
  - 1941 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 2077 `list_shows`
  - 2096 `load_show`
  - 2195 `handle`
  - 2644 `on_result`
  - 2661 `rdm_busy`
  - 2676 `ProtocolThrottle`
    - 2677 `clear`
  - 2692 `lifespan`
  - 2719 `mask`
  - 2722 `safe_data`
  - 2734 `DiagnosticHandler`
    - 2735 `emit`
  - 2750 `updating`
  - 2760 `update_busy`
  - 2767 `update_gate`
  - 2774 `update_reopen`
  - 2778 `update_stop`
  - 2783 `perform_action_inner`
  - 2820 `operation_reply`
  - 2831 `finish_operation`
  - 2847 `perform_action`
  - 2891 `handle_load`
  - 2900 `ws_endpoint`
  - 2903 `simple_ws_endpoint`
  - 2906 `serve_ws`
    - 2916 `worker`
    - 2920 `spawn`
  - 2971 `no_cache`
  - 2992 `simple_index`
  - 2996 `simple_style`
  - 3000 `simple_script`
  - 3004 `simple_health`
  - 3008 `update_health`
- 3020 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 3042 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 3054 `local_addresses`
- 3061 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 3081 `stop_running`
- 3093 `open_start_page` — Open only after the listener is ready; failure does not stop the bridge.
- 3106 `main`

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
- 223 `StatusRelay` — Read-only loopback status on the original port while the bridge is absent.
  - 225 `__init__`
  - 230 `start`
    - 234 `Handler`
      - 235 `log_message`
      - 238 `do_GET`
  - 272 `stop`
- 280 `apply`
- 333 `wait_parent` — Acquire a Windows process handle before acknowledging readiness (no PID reuse race).
  - 354 `wait`
- 366 `worker`
- 385 `Updater`
  - 386 `__init__`
  - 390 `begin`
  - 399 `_run`
- 440 `recover_pending`
- 460 `watch_orphan`
- 483 `orphan_worker`
- 513 `register`
  - 519 `local`
  - 530 `denied`
  - 534 `update_health`
  - 538 `update_status`
  - 544 `check_update`
  - 556 `updater_idle`
  - 562 `quiesce`
  - 571 `start_update`

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
- 23 `bind`
  - 24 `export_folders` — Where an export may land: ma2.export_dir first, then every existing folder matching ma2.ex
  - 32 `listing`
  - 47 `save_diag_json`
  - 55 `export_type` — One Export FixtureType under a one-off name. The documentation puts fixture types in their
  - 96 `export_once` — One export under a name nobody has used, read from the console's folders, then removed. Ca
  - 125 `run_export`
  - 174 `snapshot` — {path: (size, mtime)} of the files under roots, bounded. No disk-wide scan: only the conso
  - 196 `run_export_probe` — Active diagnostics: sends a few export lines under unique names and reports which files ap

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
  - 61 `_handle`
  - 93 `_wire`
  - 98 `_reply`
  - 104 `_answer`
  - 228 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 244 `drop`
- 249 `start_mock`

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
- 116 `send`
- 134 `sendRaw`
- 141 `busy`
- 143 `feedback`
- 147 `notice`
- 165 `actionFeature`
- 169 `featureReason`
- 175 `go`
- 185 `render`
- 226 `renderBanners`
- 253 `renderSection`
- 295 `readFromMa2`
- 296 `fixtureImportComplete`
- 307 `fixtureImportChoices`
- 337 `SECTIONS.start`
- 386 `setupSteps`
- 402 `safetyText`
- 409 `ma2Card`
- 433 `pagesList`
- 437 `SECTIONS.scenes`
- 478 `masterControl`
- 499 `setFill`
- 504 `openSceneEdit`
- 531 `cancelStore`
- 535 `openStore`
- 572 `SECTIONS.history`
- 584 `SECTIONS.shows`
- 645 `discardPending`
- 654 `clearEvidence`
- 659 `sceneAllowed`
- 662 `sceneEvidence`
- 669 `valueFreshness`
- 672 `sentSource`
- 675 `sentStale`
- 678 `observeEvidence`
- 686 `expireEvidence`
- 706 `receive`
- 819 `connect`
- 847 `cancelSlider`
- 854 `flushSliders`
- 863 `throttleSlider`
- 878 `selectFixtures`

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
- 6 `planKind`
- 13 `placed`
- 14 `hallOf`
- 15 `planKey`
- 21 `planBeginEdit`
- 28 `stopPing`
- 33 `planEndEdit`
- 41 `highlightOn`
- 58 `planBeamAngle`
- 74 `hallPlan`
- 225 `tapFixture`
- 246 `planOrder`
- 247 `planCurrent`
- 253 `planLight`
- 258 `planNext`
- 272 `planStep`
- 281 `SECTIONS.hall`
- 356 `hallForm`
- 374 `groupSide`
- 400 `openGroupStore`
- 418 `beamCard`

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


