# Индекс функций

Собрано `scripts/codemap.py` (не править руками). Описание устройства: `docs/CODEMAP.md`.

## api.py
- 50 `register`
  - 55 `import_file`
  - 71 `idle`
  - 77 `get_log`
  - 81 `stop`
  - 90 `get_settings`
  - 103 `put_settings`
  - 146 `restart`
  - 156 `export_report` — Everything about reading the fixtures that is already known, without sending anything to t
  - 167 `diagnostics`
  - 176 `link_test` — Read-only: the connection attempts so far, who holds port 30000 on this PC, and one bare T
  - 217 `export_probe`
  - 236 `probe_console`
  - 253 `diagnostic_package` — Only reads what is already on disk or in memory: nothing is sent to the console. One faili
    - 257 `part`
    - 263 `read`

## bridge.py
- 48 `is_loopback`
- 67 `create_app`
  - 82 `add_strobe_attrs`
  - 134 `status_msg`
  - 141 `config_msg`
  - 153 `shown_msg`
  - 159 `session_msg`
  - 164 `broadcast`
  - 175 `spawn_broadcast`
  - 180 `history_msg`
  - 183 `add_history` — kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: n
  - 196 `light_diff` — {fid: the old values of what changed since the snapshot}; a value the panel did not know b
  - 205 `light_what`
  - 210 `undo_light` — Send the old values back, fixture by fixture; the first refusal stops it.
  - 224 `forget_positions`
  - 231 `highlight_zone`
  - 236 `highlight_status`
  - 241 `highlight_stuck`
  - 245 `highlight_record`
  - 251 `highlight_lines`
  - 272 `release_highlight` — Caller holds action_lock; only the recorded zone and known panel values may leave here.
  - 311 `highlight_action`
  - 365 `highlight_disconnect`
  - 374 `highlight_lease`
  - 384 `show_from`
  - 393 `update_show`
  - 404 `identify_show`
  - 421 `capture_replies` — Read-only lines whose reply format the code still guesses; replies go to field-data/auto/
  - 442 `spawn_capture`
  - 447 `on_state`
  - 473 `blocked` — Reason an action is refused in the current mode, else None. link.guard repeats this for ev
  - 497 `check_ids`
  - 504 `check_scene`
  - 508 `heads`
  - 514 `selected`
  - 520 `remember`
  - 549 `lines_for` — MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.
  - 655 `execute` — Send the action's lines; None on success, else the error text.
  - 680 `no_attribute` — Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attrib
  - 692 `swap_off`
  - 701 `throttled`
  - 709 `fade_starts` — [(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then t
  - 720 `play_fade` — Values from each start to the target, one per throttle tick; the throttle sends them like
  - 739 `layout_save`
  - 748 `new_id`
  - 752 `mover`
  - 758 `config_edit` — New values for the changed config keys; raises ActionError before anything changes.
  - 823 `scene_pages`
  - 828 `list_cmd`
  - 831 `list_execs` — onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2
  - 842 `poll_running` — Scene state and show name from the console, so a Go or a LoadShow from another tablet or t
  - 869 `poll_dmx` — What the desk outputs, read by a Lua line every dmx_seconds: the plan shows every lit fixt
  - 884 `read_dmx` — One read; returns the wait before the next one, None when the desk refused the line.
  - 925 `read_scenes` — Existing scenes_import reader; caller holds action_lock and saves atomically.
  - 946 `read_ma2` — Read all three pools under action_lock; raw replies also stay in link diagnostics.
  - 965 `send_ma2_lines`
  - 975 `ma2_action`
  - 1078 `invalidate_scene_offers`
  - 1084 `offer_context`
  - 1087 `find_scene_slot`
    - 1092 `emit`
  - 1141 `store_checked` — Check fresh console data while the caller holds action_lock, in every write mode.
  - 1156 `record`
  - 1169 `show_name`
  - 1175 `plan_path`
  - 1179 `check_show`
  - 1186 `import_xml`
  - 1210 `open_show_plan`
  - 1246 `follow_desk_show` — Caller holds action_lock. A show made or loaded on the desk since: read its name now and m
  - 1258 `plan_copy` — Placement and marks from another show's plan for fixtures with the same number here. Nothi
  - 1286 `fetch_fixtures`
  - 1294 `read_types` — Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureT
  - 1325 `send_planned` — One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once.
  - 1334 `rdm_read`
  - 1345 `patch_action` — Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action loc
  - 1412 `list_shows`
  - 1431 `load_show`
  - 1517 `handle`
  - 1904 `on_result`
  - 1915 `lifespan`
  - 1956 `mask`
  - 1959 `safe_data`
  - 1971 `DiagnosticHandler`
    - 1972 `emit`
  - 1981 `handle_load`
  - 2016 `ws_endpoint`
  - 2019 `simple_ws_endpoint`
  - 2022 `serve_ws`
    - 2032 `worker`
    - 2036 `spawn`
  - 2080 `no_cache`
  - 2089 `simple_index`
  - 2093 `simple_style`
  - 2097 `simple_script`
- 2105 `probe` — Send read-only commands and write the raw replies to probe.txt: the replies are the format
- 2127 `backup_config` — One copy of config.json per day in backups/, the last `keep` days.
- 2139 `local_addresses`
- 2146 `check` — Read nothing from the console: only prints the settings and tests that the Telnet port acc
- 2166 `stop_running`
- 2178 `main`

## commands.py
- 21 `ActionError`
- 25 `nudge_step`
- 35 `_value`
- 42 `fade_suffix` — Programmer fade for dim and colour; "" when absent or 0. `At 50 Fade 2`: MA2 3.9 manual p.
- 50 `find`
- 57 `page_number`
- 64 `exec_page`
- 68 `store_lines` — No SaveShow: saving the whole show is the operator's decision, never the panel's.
- 76 `_reply_lines` — Ignore standalone prompts and List command echoes (possibly prefixed by a prompt).
- 84 `exec_verdict`
- 96 `unrecognised_lines`
- 106 `parse_executors` — (exec, label) from a `List Executor` reply. ponytail: reply format guessed, check in the h
- 117 `can_move` — Heads: the old moves flag, or Pan/Tilt among the parameters read from the MA2 export.
- 122 `parse_ma2_objects` — Catalogue rows from the site's assumed List format; never infer fixture membership.
- 138 `group_slot_empty` — Only an explicit empty response is safe; echoes/prompts alone prove nothing.
- 152 `parse_running` — exec -> running, only for lines that carry a status word. ponytail: status word guessed, c
- 166 `movers`
- 171 `scale`
- 177 `attr_lines`
- 182 `head_lines` — Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line.
- 197 `select_line`
- 201 `apply_move`
- 207 `check_move`
- 215 `check_jog` — Joystick step in degrees since the last one: relative, so the desk and the panel can turn
- 225 `mirrored` — Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns
- 232 `pan_flip`
- 236 `rel_lines` — Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down)
- 253 `parse_label`
- 260 `build`
- 328 `targets`
- 339 `validate_hall`
- 353 `parse_positions` — x and y both null take the fixture off the plan, back to the tray.
- 385 `is_error_reply`
- 389 `load_config`
- 420 `absolute` — "1.289" -> 289, "2.001" -> 513.
- 426 `dmx_span` — (first address, count) covering every patched fixture of the plan.
- 432 `dmx_lua` — One Lua line per chunk of DMX_CHUNK addresses.
- 437 `parse_dmx` — {absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out.
- 447 `live_from_dmx` — What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without
- 468 `check_dmx_map` — {dim, r, g, b}: channel numbers 1-64 or absent.
- 482 `dmx_text` — 289 -> "1.289".
- 487 `parse_address` — "1.290", "290" or 290 -> absolute 1-based address; anything else is refused.
- 495 `check_uid`
- 502 `patch_rows` — One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entere
- 524 `patch_plan` — What a readdress changes, checked against every other fixture of the plan. token: the plan
- 555 `parse_type_footprints` — {type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-wid
- 572 `type_no`
- 577 `parse_rdm_list` — RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so onl

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

## fixtures.py
- 9 `local`
- 13 `describe` — What the file contains, for the error text and the diagnostics: the real MA2 XML layout ha
- 24 `dmx_address` — "200" -> "1.200", as List Fixture shows it. ponytail: absolute address assumed ((universe-
- 37 `guess_head`
- 41 `parse_group_export` — {group number: [fixture ids]} from an `Export Group` XML. listed: {n: name} from List Grou
- 62 `parse_export` — Fixtures with a Fixture ID. skipped, if given, gets the names of <Fixture> entries without
- 106 `parse_fixture_type` — {dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<C
- 148 `merge_fixtures`
- 169 `save_config`

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
  - 125 `ready`
  - 128 `mask`
  - 131 `_set`
  - 137 `run`
  - 193 `_login` — logged_in only when the login reply has no error AND ListVar names the configured user.
  - 224 `_sleep` — Waits before the next attempt; link_connect cuts it short.
  - 232 `disconnect` — Closes only this bridge's Telnet session. The console, its network and other sessions are
  - 238 `connect`
  - 242 `new_action`
  - 245 `close`
  - 249 `_raw`
  - 252 `_result`
  - 256 `send` — (ok, reply or reason). ok means status "sent". gen: the link generation the caller started
  - 301 `_drain` — Late answer to a timed-out line, so it is not read as the next line's answer. True when it
  - 311 `_pump`
  - 324 `_exchange`
  - 336 `_collect` — (reply, prompt seen). The reply ends at the command prompt ("[Channel]>").

## mock.py
- 14 `MockMA2`
  - 15 `__init__`
  - 59 `_handle`
  - 91 `_wire`
  - 96 `_reply`
  - 102 `_answer`
  - 216 `_real_list` — Rows as the hall console printed them; executor rows were never captured, so those keep th
  - 232 `drop`
- 237 `start_mock`

## safety.py
- 67 `load_secret` — Password from the MA2_PASSWORD variable or secret.env (one line MA2_PASSWORD=...). Never g
- 80 `load_settings`
- 92 `effective_safety`
- 105 `redact` — Hide the password in diagnostics without eating ordinary text.
- 117 `make_guard` — guard(line) -> None when the line may be sent, else the reason it is blocked.
  - 136 `guard`
- 201 `without_passwords`
- 209 `validate_settings` — Validate the entire replacement before touching disk or the running link.

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

## update.py
- 17 `UpdateError`
- 21 `allowed`
- 32 `validate_zip`
- 53 `normalize_url`
- 64 `download`
- 76 `settings`
- 81 `version`
- 86 `idle`
- 96 `prepare_bridge`
- 120 `local_archive` — An update zip from a USB stick; a .sha256 next to it is checked when present.
- 135 `backup_user_data` — Copies this panel's own data before an update; MA2 files are never touched. Returns the fo
- 148 `remove`
- 155 `install`
- 191 `rollback`
- 215 `run`
- 245 `main`

## static/app.js
- 19 `on`
- 25 `h`
- 40 `add`
- 57 `icon`
- 64 `pageOf`
- 65 `bridgeUp`
- 67 `linkReady`
- 68 `connected`
- 69 `fixtures`
- 70 `fixture`
- 72 `canMove`
- 73 `hasFixtures`
- 74 `safe`
- 81 `linkLine`
- 91 `send`
- 101 `sendRaw`
- 104 `busy`
- 106 `feedback`
- 110 `notice`
- 119 `actionFeature`
- 123 `featureReason`
- 129 `go`
- 139 `render`
- 180 `renderBanners`
- 204 `renderSection`
- 246 `readFromMa2`
- 247 `SECTIONS.start`
- 294 `setupSteps`
- 310 `safetyText`
- 317 `ma2Card`
- 341 `pagesList`
- 345 `SECTIONS.scenes`
- 386 `masterControl`
- 404 `setFill`
- 409 `openSceneEdit`
- 436 `cancelStore`
- 440 `openStore`
- 477 `SECTIONS.history`
- 490 `sameName`
- 491 `SECTIONS.shows`
- 556 `discardPending`
- 562 `receive`
- 636 `connect`
- 664 `cancelSlider`
- 671 `flushSliders`
- 680 `throttleSlider`
- 695 `selectFixtures`

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
- 52 `moveStop`
- 65 `moveShell`
- 204 `movePresets`
- 239 `renderMove`

## static/patch.js
- 4 `patchKey`
- 14 `dmxText`
- 15 `closeDialog`
- 17 `rdmCard`
- 39 `patchTable`
- 57 `patchPick`
- 63 `patchEditor`
- 95 `patchDialog`
- 121 `patchResult`
- 131 `SECTIONS.patch`

## static/plan.js
- 6 `planKind`
- 13 `placed`
- 14 `hallOf`
- 15 `planKey`
- 21 `planBeginEdit`
- 27 `stopPing`
- 32 `planEndEdit`
- 40 `highlightOn`
- 57 `hallPlan`
- 189 `tapFixture`
- 210 `planOrder`
- 211 `planCurrent`
- 217 `planLight`
- 222 `planNext`
- 236 `planStep`
- 245 `SECTIONS.hall`
- 320 `hallForm`
- 338 `groupSide`
- 364 `openGroupStore`
- 382 `beamCard`

## static/settings.js
- 7 `status`
- 8 `saved`
- 9 `clearErrors`
- 16 `fieldError`
- 26 `warning`
- 27 `csv`
- 28 `fill`
- 60 `load`

## static/simple.js


