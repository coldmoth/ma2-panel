# Карта кода ma2-panel

Читать это перед любой правкой, в код лезть только по указанным местам. Точные строки: `docs/code-index.md` (генерируется: `python3 scripts/codemap.py > docs/code-index.md`, после правок кода обновить). Контракт: `docs/spec.md`.

## Поток одного действия

```
браузер --WS {a: "...", ...}--> api/ws_endpoint (bridge.py) --> handle() (bridge.py)
   handle: разбор JSON -> halt/resume/link_* -> highlight_action -> blocked(a) (режим защиты, features)
        -> SLIDERS (dim/color/move/...) идут в Throttle (link.py), остальное сразу
        -> действие без строк MA2 (layout_save, group_save, fixture_flag, scene_create...) правит config.json и рассылает config
        -> иначе execute() -> lines_for() -> commands.build() -> link.send() -> make_guard() (safety.py) -> Telnet
   ответ {"ok": ...} + broadcast: status / config / shown / running / last
```

Правило: панель шлёт только действия, строки MA2 собирает мост (`commands.build`), последний фильтр строк `safety.make_guard`.

## Файлы

Backend расположен в `ma2panel/`; имена модулей ниже относятся к этому пакету.
Корневой `bridge.py` — стабильный launcher с recovery до импорта backend.
`windows_asyncio.py` завершает прерванный cleanup серверного Proactor-транспорта
только после Windows 10054 в Python 3.12; остальные ошибки делегируются штатно.
Шаблоны и mock-данные — `ma2panel/resources/`, BAT — `scripts/win/`, relay — `scripts/relay/`.


| Файл | Что внутри |
|---|---|
| `commands.py` | Чистое: `build(action, cfg)` → строки MA2; множества `SIMPLE`/`FULL`/`SLIDERS` (какие действия существуют); `parse_*` ответов `List ...`; `validate_hall`; `fade_suffix`. Новое действие начинается тут |
| `safety.py` | `DEFAULT_SAFETY`, `DEFAULT_MA2` (шаблоны команд и регулярки ответов), `make_guard` (белый список строк), `load_settings`, `validate_settings`, `redact` |
| `scene_runtime.py` | Проверка List Executor (Normal/LTP, SoftLTP, Chaser), nonce/Cue Part CMD, bounded read-only readback, native fade/Off, резерв/commit с CueOnly, чтение/журнал/возврат Grand. Вызывается под action_lock; регрессии test_stage1_scenes.py. |
| `status_evidence.py` | Источник подтверждения, монотонное устаревание через 6 с и метаданные; используется мостом для сцен и источников значений |
| `link.py` | `MA2Link` (вход, одна строка за раз, ждёт `]>`), `Throttle` (последнее значение слайдера, `rate_hz`), `READY`/`NO_LINK`/`HALTED` |
| `migrations.py`, `show_plans.py` | Проверенная миграция config v1–4→v5 с резервными копиями; перенос настроек площадки; безопасные пути планов с проверкой поля show и чтением legacy |
| `fixtures.py` | `parse_export` (XML MA2), `merge_fixtures`, `guess_head`, `save_config` (атомарно) |
| `bridge.py` | `create_app` — одно большое замыкание (≈1850 строк), `main`, `probe`, `check`. Ниже его блоки |
| `exports.py` | Файлы экспорта пульта: `bind(...)` внутри `create_app` даёт `export_folders`, `export_once`, `run_export`, `export_type` (тип прибора), `run_export_probe` (диагностика), `listing`, `snapshot`, `save_diag_json` |
| `api.py` | `/api/*`: settings, diag, diag.zip, diag/upload, diag/send, probe, link_test, import_file, stop, restart. `register(app, c, is_loopback)` получает снимок локальных переменных `create_app` |
| `mock.py` | Поддельный MA2 (`--mock`, `MA2_MOCK_REAL=1` — формат живого пульта) |
| `diagnostic_upload.py`, `diagnostic_relay.py` | Обезличенный отчёт, постоянный журнал UUID/повторов; `Uploader.enqueue/retry/run` — очередь на ПК и доставка раз в минуту без браузера через фиксированный HTTPS-приёмник, без локального GitHub-доступа; старые неоднозначные прямые отправки остаются GET-only |
| `scripts/relay/app.py`, `scripts/relay/ma2-diagnostics.service` | Отдельный серверный приёмник: строгая схема, постоянные квоты и SQLite-очередь, идемпотентные UUID, приватные квитанции, ограниченная доставка в закрытый GitHub с отдельным журналом на отчёт; однократный доступ владельца — `scripts/setup_diagnostic_relay.py`; старый `diagnostic_setup.py` оставлен для совместимости |
| `update.py`, `browser_update.py`, `release.py`, `firewall.py`, `selfcheck.py` | Транзакции/точный откат, внешний updater и локальные API/UI, единый payload/manifest/runtime identity, firewall по портам; проверка на площадке |
| `onboarding.py`, `static/setup.*` | Локальный мастер подключения: пассивный `/api/setup`, актуальные IPv4 URL и офлайн QR (`segno`), сохранение через settings API, перезапуск с проверкой нового instance. Внешний Windows start.bat вызывает program/start.bat; `--open-browser` открывает мастер после готовности HTTP |
| `show_files.py`, `show_transfer.py`, `static/show-files.js` | Настоящие `.show.gz`: ограниченная проверка gzip, неизменяемый снимок, публикация без замены; HTTP upload/prepare/confirm/status/download. Подтверждение связано с подключением/stop ticket; `bridge.load_show` проверяет файл непосредственно перед командой. Только локальная onPC с явным shows_dir; mock — внутри каталога своего config |
| `scripts/` | `build_win.sh`, `serve_update.sh` (payload: `ma2panel/`, static, BAT и standalone updater), `command_map.py` (→ `docs/outgoing-commands.md`), `codemap.py`, `clodex.py` |

## Блоки внутри `create_app` (искать по имени функции)

| Тема | Функции |
|---|---|
| Состояние и рассылка | `status_msg`, `config_msg`, `shown_msg`, `scenes_msg`, `values_meta`, `invalidate_evidence`, `expire_evidence`, `broadcast`, `state`, `sessions`, `clients`; сцены bool/null + метаданные, рассылки упорядочены, медленный клиент закрывается |
| Разрешение действия | `blocked`, `check_ids`, `check_scene`, `features`, `safety`/`mode` |
| Свет (строки + «что показано») | `lines_for` (`jog`/`nudge` → `commands.rel_lines`), `execute`, `no_attribute` (Error #14), `remember`, `throttled`, `heads`, `selected` |
| Сцены | `scene_pages`, `list_execs`, `poll_running`, `read_scenes`, `scene_runtime.transition_lines` (штатный fade/Off), `GrandMasterBlackout`, ветки `scene_*`/`page_save` в `handle` |
| Правка конфига (группы, пресеты, луч) | `config_edit`, `layout_save`, `mover`, ветка `fixture_flag` в `handle` |
| Чтение MA2 (группы, пресеты, сцены) | `read_ma2`, `catalogue_meta` (complete/empty/partial/error/stale), `ma2_action` (свежий состав группы), `store_checked` |
| Подсветка в редакторе | `highlight_*`, `release_highlight`, `highlight_action`, `highlight_lease` |
| Шоу | `identify_show`, `list_shows`, `load_show`, `open_show_plan`, `check_show`, `import_xml` |
| Экспорт приборов | `fetch_fixtures`, `read_types` (каналы/ограниченные повторы), `commit_import` (все ссылки IDs, атомарность); сами экспорты — `exports.py` |
| Патч и RDM (спека 21) | `patch_action`, `send_planned`, `rdm_read` |
| Поиск RDM (2026-11-03) | `rdm` (`RDMSearch`, `rdm_search.py`): prepare/start/stop/check, журнал `rdm-search.json`; ветка в `handle` до `blocked`, строка `rdm_search` в `status_msg`, `rdm_extra`/`RDM_GLOBAL` в `safety.make_guard`; UI — `rdmCard`/`rdmSearchBanner` в `patch.js`; тесты `test_rdm_search.py`, `test_rdm_integration.py`, `rdm-search-ui.cjs` |
| Запись ответов пульта (спека 23) | `capture_replies`, `spawn_capture`; включает `main()` (`capture=not args.mock`), файлы в `field-data/auto/` |
| История (откат) | `history`, `add_history`, `light_diff`, `undo_light`, ветка `undo` в `handle`, снимок конфига в `handle_load`; `HISTORY_*` над `create_app` |
| Транспорт | `ws_endpoint`, `handle_load`, `on_state`, `on_result`, `lifespan`, `record` (журнал), `mask`/`safe_data` |

## Панель (`static/`, без сборки, глобальные функции)

| Файл | Что |
|---|---|
| `index.html` | каркас, подключает скрипты по порядку |
| `app.js` | `state`, `h()` (DOM-хелпер), `send()`, `render()`, `receive()` (разбор сообщений моста), `connect()`; разделы `SECTIONS.start` (Площадка), `scenes`, `shows` |
| `command-feedback.js` | Общая трактовка `command_evidence`, понятные названия действий, ожидание/регистрация запроса; используется основной и простой панелью. Не подтверждает применение команды или причинность readback |
| `light.js` | `SECTIONS.light`: выбор, `sliderCard`, `colorCard`, `moveCard` |
| `move.js` | джойстик Pan/Tilt (`jog`, «Точно», «Зеркально», «наоборот»), шаги, пресеты позиции |
| `plan.js` | `hallPlan` (схема), `SECTIONS.hall` (расстановка, группы, луч) |
| `patch.js` | `SECTIONS.patch` (спека 21): таблица патча, RDM, поиск RDM (подтверждение, фазы, восстановление), режим правки, окно плана; бэкенд — `patch_action` и координатор `rdm` в `bridge.py`, `patch_plan`/`patch_rows`/`parse_rdm_list` в `commands.py` |
| `simple.html`, `simple.js` | простой режим для учителей (спека 24): второй порт `simple_port`, только сцены и «Погасить всё»; мост (`serve_ws(simple=True)`, проверка в начале `handle`) отклоняет всё остальное |
| `settings.*`, `diag.*`, `log.html` | отдельные страницы для ПК; `diag-upload.js` — отправка/проверка диагностики, без действий MA2 |
| `style.css`, `concert.css` | токены дизайна в `:root`; концертная компоновка в `concert.css`; правила дизайна в `DESIGN.md`, продукта в `PRODUCT.md` |

## Интерфейс 3.2.0

`static/atlas.css` — адаптивный «Сценический атлас», `static/interface.js` — личная
видимость инструментов, `static/command-feedback.js` — достоверные статусы действий.
Регрессии выбора/плана/движения включены в `tests/panel-v4.cjs`.
Отдельные локальные прототипы и demo-адаптер не входят в публичную поставку.

## Данные

- `config.json` — план шоу: `fixtures` (`id,label,type,x,y,moves,moves_auto,service,rot,beam,address,channels,missing`), `groups`, `scenes` (`id,exec,label`), `presets`, `hall`, `pages`, `show`, `attrs`. Шоу хранятся в `shows/plan-<SHA256 имени>.json`; старые `shows/<очищенное имя>.json` читаются только при совпадении поля `show`. Бэкапы в `backups/`.
- `settings.json` — площадка: `safety` (режим, разрешённые приборы и сцены), `ma2` (хост, шаблоны), `features`, `rate_hz`, `poll_seconds`, `master`. Версия config — 5; настройки площадки `port`, `rate_hz`, `ma2`, `master` при миграции удаляются из плана. Пароль только в `secret.env`.
- `config.json`, `settings.json`, `secret.env` и рабочие данные игнорируются Git; для новой установки копировать `config.example.json` и `settings.example.json`. `AGENTS.md` — локальные инструкции разработки.

## Куда идти за типовой правкой

| Нужно | Правка |
|---|---|
| Новое действие панели | `commands.py` (`SIMPLE`/`FULL`, `build`), `bridge.py` (`blocked`, ветка в `handle` или `lines_for`), если строка новая — `safety.make_guard`, `static/app.js` (`send`), тест |
| Новая команда MA2 | `safety.py` (шаблон в `DEFAULT_MA2` и белый список), `docs/outgoing-commands.md` (`scripts/command_map.py`) |
| Другой формат ответа пульта | `DEFAULT_MA2` регулярки + `commands.parse_*`; реальные ответы в `field-data/` |
| Новая кнопка в разделе | `static/<раздел>.js`, стили `style.css` |
| Настройка площадки | `safety.validate_settings`, `settings.html`/`settings.js` |

## Тесты

`perl -e 'alarm 300; exec @ARGV' uv run pytest -q -p no:cacheprovider` (≈45 с, ≈525 тестов). `tests/conftest.py` укорачивает ожидания зала (`link.RECONNECT_S`, `link.REPLY_S`, `bridge.SHOW_POLL_S`, `api.BARE_CONNECT_S`, `timeout`/`export_wait` в `DEFAULT_MA2`); тест, которому нужно настоящее значение, задаёт его сам. `tests/test_bridge.py` — основа (`bridge_cfg` фикстура + `ask(ws, action)`), `test_commands.py` — чистые функции, `test_safety.py` — белый список, `test_real_ma2.py` — формат живого пульта, `tests/panel-v4.cjs` — скрипты панели на фальшивом DOM (нужен node). Тесты импортируют `from ma2panel import bridge` и патчат `bridge.HERE`, `bridge.is_loopback`, `bridge.MA2Link`, `bridge.start_mock`, `bridge.save_config`: эти имена должны оставаться в `bridge.py`.

`tests/test_diag_upload.py` — обезличивание, доставка/постоянный журнал, старый доступ, локальные HTTP-ограничения. `tests/test_diagnostic_relay.py` — новая установка без credentials, квитанции/повторы, legacy pending; `tests/test_diagnostic_relay_server.py` — серверная очередь/квоты/миграция; `tests/test_relay_setup.py` — безопасная установка токена владельцем. `tests/diag-upload.cjs` включён в `panel-v4.cjs`. На новой установке credentials не нужны. Старый `diagnostic-upload.json` рядом с settings сохраняется для проверки прежних неоднозначных отправок; журнал — `diag/upload-state.json` рядом с config. Удаление журнала теряет идентификаторы повторов. Инструкции: [приёмник](../scripts/relay/README.md), [история диагностики](audit-step9-diagnostics.md).

`tests/test_release.py`, `tests/test_update.py`, `tests/test_browser_update.py`, `tests/test_firewall.py` —
упаковка/совместимость, сохранность/восстановление, локальные API и реальный detached-worker mock,
firewall. `tests/update-ui.cjs` входит в Node-набор. `scripts/package_release.py` общий для ZIP;
`runtime.json`/`runtime-files.json` создаются полным комплектом, не заменяются update-пакетом.
`tests/test_onboarding.py` и `tests/setup-ui.cjs` проверяют мастера, смену адресов,
ограничения localhost, сохранение неизвестных настроек и честное состояние при обрыве.
Browser preflight также проверяет мастер на 1024×768 и 390×844, сохранение и offline/reconnect.
Журналы и стабильный recovery — `.updates/`, предыдущая программа — `previous/`;
не удалять их во время операции. Подробности: [блок Б](audit-block-b-updates.md).

## Подводные камни

- Порядок в `handle`: `halt` и `resume` обходят все блокировки; слайдеры ждут `Throttle`, остальное сначала `throttle.flush_all()`.
- `action_lock` держит строки одного действия вместе; нигде не `await` пульта без него.
- Ничего не отправляется повторно после `unknown`; `/Overwrite` и `SaveShow` — только по явным разрешениям.
- Реальный пульт (onPC 3.9.60): ответ начинается `Executing : <cmd>` и кончается `[Group]>`; `List Executor 1.1 Thru 1.250` даёт Error #9 (мост сам уменьшает диапазон); адрес в XML абсолютный DMX.
- Стробоскоп (спека 24) идёт не по шаблону `attrs.strobe`, а по `dmx_map[тип].strobe` из `Export FixtureType` (`fixtures.parse_fixture_type`, ветка `strobe` в `lines_for`); `has` там же прячет слайдеры в панели (`attributeVisible` в `light.js`). Формат `ChannelSet` в экспорте 3.9.60 не проверен: сырой файл лежит в `diag/fixture_type_<n>.xml`.
- Что не проверено на пульте: переход на настоящих приборах и содержимое резервов Copy. На изолированной onPC 3.9.63.11 проверены свойства Cue/Grand, синтаксис Goto/Masterfade/Off и Copy/CueOnly пустых Cue; целевая 3.9.60 ещё не принята. См. ma2-command-evidence.md. Угаданные головы по имени типа также требуют проверки.

Блок В: `tests/test_migration_v5.py`, `test_data_startup.py`, `test_plan_path.py`,
`test_import_confirm.py` проверяют реальные миграции/startup, переключение планов,
prepare/confirm (WS и loopback HTTP), stale/replay и соответствия приборов.
`tests/import-confirm-ui.cjs` входит в Node-набор.
`POST /api/fixtures/import_confirm` применяет выбор ручного XML без команд MA2.
Подробности и ограничения: [audit-block-v-data.md](audit-block-v-data.md).

## Локальная подготовка 3.1

`bridge.py`: `ActionLock`/`revision_token` проверяют версию правки до записи; `perform_action`/`operation_reply`/`finish_operation` связывают ID, свидетельства исполнения и терминальные ответы. `status.operations` показывает активные действия. `read_dmx` обходит `commands.dmx_intervals` по одной порции, `expire_dmx` удаляет устаревшие адреса независимо от опроса; `parse_dmx(span=...)` принимает только текущую переменную. Первичное чтение типов ограничено `max_types=1`.

`static/move.js`: переключатель джойстика и абсолютных независимых осей, отдельные каналы ограничения отправки и отмена ожидающих значений. `aim` принимает непустое подмножество pan/tilt. Транспорт и очередь правок — `static/app.js`, снимок версии редактора — `static/plan.js`.

Регрессии: `tests/test_protocol.py`, `tests/test_absolute_axes.py`, `tests/test_dmx_intervals.py`; `tests/protocol-panel.cjs` и `tests/absolute-axes.cjs` включены в основной Node-набор. Настоящие движки: `scripts/browser_smoke.py`/`.cjs`, dev-only pinned Playwright в `scripts/browser_smoke/`; [повторяемый запуск](browser-preflight.md).

[Подготовка и первый сеанс зала](pre-hall-3.1.md), [заметки кандидата](RELEASE-3.1.md). Лицензия исходников — root LICENSE, в программном payload — docs/LICENSE.txt.

## Защита от регрессий и перенос (2026-11-12)

`quality_diagnostics.py`: пассивная готовность и обезличенный локальный snapshot,
preview/download SHA256; регистрация из `api.register`, UI `static/quality-diagnostics.js`.
`data_transfer.py`: явный приватный backup/preview/restore с проверкой байтов,
без изменения legacy-путей. Проверки `tests/test_quality_*.py`, `test_data_transfer.py`.
`scripts/quality_dataset.py` и `tests/data/ma2-v2/manifest.json` фиксируют происхождение V2.
`scripts/run_quality_browser.py` переиспользует browser_smoke runner; тестовые
управляющие hooks из `regression_server.py` доступны только во временной mock-копии.
`scripts/quality_gate.py` связывает checks и ZIP с SHA; `.github/workflows/promote.yml`
готовит только draft после отдельной приёмки. [Критерии](QUALITY-GATES.md),
[установка и восстановление](OPERATIONS.md), [аудит](testing-infrastructure-audit.md).

Исправления quality-аудита: `release_quality.py`, `scripts/stable_evidence.py`
— GitHub-bound stable evidence; `mock_console.py` — независимый oracle;
`check_reproducible.py`, `check_import_regression.py`, `first_run_zip.py`,
`release_lifecycle.py` — чистый SHA, отрицательный import, pristine ZIP, реальный v3.3.0 lifecycle.
Тесты: `test_stable_quality.py`, `test_audit_regressions.py`, `test_committed_mock.py`,
`test_first_run_zip.py`, `test_reconnect_stream.py`.

Исправления после чистой установки (2026-11-13): `bridge.py` — ограниченный повтор
ошибок FixtureType, продолжение получения типов без Lua/readback; `fixtures.py` —
подтверждённые Pan+Tilt в `has.pos`; `commands.can_move` и `static/app.js` учитывают
только текущую карту. `static/interface.js` — локальное отображение инструментов,
`light.js` — постоянно видимые способы выбора. Регрессии: `test_field_capabilities.py`,
`field-interface.cjs`, `field_regression_browser.cjs` (пустая панель),
`check_field_regression.py` (удаление RGB). Они включены в существующие Node/quality
и clean-SHA runners; реальные V2 Patch и синтетические FixtureType разделены.

## Этап 2: readback и синхронизация (2026-11-10)

`read_dmx`/`dmx_cycle`: retry и TTL отдельных блоков, dmx_wake при reconnect.
`dmx_diagnostics`: адреса, карты и состояние блоков; /api/diag → export.dmx_read.
`fixtures.merge_fixtures`: неизменяемые исходные записи при перестановке IDs;
`commit_import` обновляет локальные и MA2-ссылки, сохраняет прежние карты.
`identify_show`/`blocked`: recovering до подтверждения контекста и refresh Patch.
Регрессии: test_stage2_state, test_stage2_pipeline, test_dmx_recovery_regression,
test_read_recovery; полная браузерная приёмка относится к этапу 4.


## Исправления review этапа 4 (2026-11-10)

Публичная база v3.2.5: backend только в ma2panel/, root bridge.py — recovery launcher.
`on_state` отменяет transport epoch и старые клиентские токены; `execute` проверяет
recovery после lock/перед строкой. `confirm_import` общий для HTTP/WS; `commit_import`
переносит/разрывает ссылки групп/позиционных пресетов и меняет plan_epoch.
`patch_action.applied` принимает только собственный синхронный импорт, сохраняя
исходные gen/show/stop для последующих readback. `build(scene_off)` задаёт Masterfade
перед Off; `hallPlan` не подсвечивает нулевой/неполный RGB.
Регрессии: test_stage4_review_fixes, live-output.cjs, stage4-integration.cjs;
браузер: scripts/stage3_browser.cjs, scripts/browser_smoke.py (только mock/копии).
