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

| Файл | Что внутри |
|---|---|
| `commands.py` | Чистое: `build(action, cfg)` → строки MA2; множества `SIMPLE`/`FULL`/`SLIDERS` (какие действия существуют); `parse_*` ответов `List ...`; `validate_hall`; `fade_suffix`. Новое действие начинается тут |
| `safety.py` | `DEFAULT_SAFETY`, `DEFAULT_MA2` (шаблоны команд и регулярки ответов), `make_guard` (белый список строк), `load_settings`, `validate_settings`, `redact` |
| `link.py` | `MA2Link` (вход, одна строка за раз, ждёт `]>`), `Throttle` (последнее значение слайдера, `rate_hz`), `READY`/`NO_LINK`/`HALTED` |
| `fixtures.py` | `parse_export` (XML MA2), `merge_fixtures`, `guess_head`, `save_config` (атомарно) |
| `bridge.py` | `create_app` — одно большое замыкание (≈1850 строк), `main`, `probe`, `check`. Ниже его блоки |
| `exports.py` | Файлы экспорта пульта: `bind(...)` внутри `create_app` даёт `export_folders`, `export_once`, `run_export`, `export_type` (тип прибора), `run_export_probe` (диагностика), `listing`, `snapshot`, `save_diag_json` |
| `api.py` | `/api/*`: settings, diag, diag.zip, probe, link_test, import_file, stop, restart. `register(app, c, is_loopback)` получает снимок локальных переменных `create_app` |
| `mock.py` | Поддельный MA2 (`--mock`, `MA2_MOCK_REAL=1` — формат живого пульта) |
| `update.py`, `selfcheck.py` | Обновление с USB; проверка на площадке |
| `scripts/` | `build_win.sh`, `serve_update.sh` (берут все корневые `*.py`), `command_map.py` (→ `docs/outgoing-commands.md`), `codemap.py`, `clodex.py` |

## Блоки внутри `create_app` (искать по имени функции)

| Тема | Функции |
|---|---|
| Состояние и рассылка | `status_msg`, `config_msg`, `shown_msg`, `broadcast`, `state`, `sessions`, `clients` |
| Разрешение действия | `blocked`, `check_ids`, `check_scene`, `features`, `safety`/`mode` |
| Свет (строки + «что показано») | `lines_for` (`jog`/`nudge` → `commands.rel_lines`), `execute`, `no_attribute` (Error #14), `remember`, `throttled`, `heads`, `selected` |
| Сцены | `scene_pages`, `list_execs`, `poll_running`, `read_scenes`, `swap_off` (плавный переход), ветки `scene_*`/`page_save` в `handle` |
| Правка конфига (группы, пресеты, луч) | `config_edit`, `layout_save`, `mover`, ветка `fixture_flag` в `handle` |
| Чтение MA2 (группы, пресеты, сцены) | `read_ma2`, `ma2_action`, `store_checked` |
| Подсветка в редакторе | `highlight_*`, `release_highlight`, `highlight_action`, `highlight_lease` |
| Шоу | `identify_show`, `list_shows`, `load_show`, `open_show_plan`, `check_show`, `import_xml` |
| Экспорт приборов | `fetch_fixtures`, `read_types` (каналы цвета по типам); сами экспорты — `exports.py` |
| Патч и RDM (спека 21) | `patch_action`, `send_planned`, `rdm_read` |
| Запись ответов пульта (спека 23) | `capture_replies`, `spawn_capture`; включает `main()` (`capture=not args.mock`), файлы в `field-data/auto/` |
| История (откат) | `history`, `add_history`, `light_diff`, `undo_light`, ветка `undo` в `handle`, снимок конфига в `handle_load`; `HISTORY_*` над `create_app` |
| Транспорт | `ws_endpoint`, `handle_load`, `on_state`, `on_result`, `lifespan`, `record` (журнал), `mask`/`safe_data` |

## Панель (`static/`, без сборки, глобальные функции)

| Файл | Что |
|---|---|
| `index.html` | каркас, подключает скрипты по порядку |
| `app.js` | `state`, `h()` (DOM-хелпер), `send()`, `render()`, `receive()` (разбор сообщений моста), `connect()`; разделы `SECTIONS.start` (Площадка), `scenes`, `shows` |
| `light.js` | `SECTIONS.light`: выбор, `sliderCard`, `colorCard`, `moveCard` |
| `move.js` | джойстик Pan/Tilt (`jog`, «Точно», «Зеркально», «наоборот»), шаги, пресеты позиции |
| `plan.js` | `hallPlan` (схема), `SECTIONS.hall` (расстановка, группы, луч) |
| `patch.js` | `SECTIONS.patch` (спека 21): таблица патча, RDM, режим правки, окно плана; бэкенд — `patch_action` в `bridge.py`, `patch_plan`/`patch_rows`/`parse_rdm_list` в `commands.py` |
| `simple.html`, `simple.js` | простой режим для учителей (спека 24): второй порт `simple_port`, только сцены и «Погасить всё»; мост (`serve_ws(simple=True)`, проверка в начале `handle`) отклоняет всё остальное |
| `settings.*`, `diag.*`, `log.html` | отдельные страницы для ПК |
| `style.css` | токены дизайна в `:root`; правила дизайна в `DESIGN.md`, продукта в `PRODUCT.md` |

## Данные

- `config.json` — план шоу: `fixtures` (`id,label,type,x,y,moves,moves_auto,service,rot,beam,address,channels,missing`), `groups`, `scenes` (`id,exec,label`), `presets`, `hall`, `pages`, `show`, `attrs`. Шоу хранятся в `shows/<имя>.json`. Бэкапы в `backups/`.
- `settings.json` — площадка: `safety` (режим, разрешённые приборы и сцены), `ma2` (хост, шаблоны), `features`, `rate_hz`, `poll_seconds`. Пароль только в `secret.env`.
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

`perl -e 'alarm 300; exec @ARGV' uv run pytest -q -p no:cacheprovider` (≈45 с, ≈525 тестов). `tests/conftest.py` укорачивает ожидания зала (`link.RECONNECT_S`, `link.REPLY_S`, `bridge.SHOW_POLL_S`, `api.BARE_CONNECT_S`, `timeout`/`export_wait` в `DEFAULT_MA2`); тест, которому нужно настоящее значение, задаёт его сам. `tests/test_bridge.py` — основа (`bridge_cfg` фикстура + `ask(ws, action)`), `test_commands.py` — чистые функции, `test_safety.py` — белый список, `test_real_ma2.py` — формат живого пульта, `tests/panel-v4.cjs` — скрипты панели на фальшивом DOM (нужен node). Тесты патчат `bridge.HERE`, `bridge.is_loopback`, `bridge.MA2Link`, `bridge.start_mock`, `bridge.save_config`: эти имена должны оставаться в `bridge.py`.

## Подводные камни

- Порядок в `handle`: `halt` и `resume` обходят все блокировки; слайдеры ждут `Throttle`, остальное сначала `throttle.flush_all()`.
- `action_lock` держит строки одного действия вместе; нигде не `await` пульта без него.
- Ничего не отправляется повторно после `unknown`; `/Overwrite` и `SaveShow` — только по явным разрешениям.
- Реальный пульт (onPC 3.9.60): ответ начинается `Executing : <cmd>` и кончается `[Group]>`; `List Executor 1.1 Thru 1.250` даёт Error #9 (мост сам уменьшает диапазон); адрес в XML абсолютный DMX.
- Стробоскоп (спека 24) идёт не по шаблону `attrs.strobe`, а по `dmx_map[тип].strobe` из `Export FixtureType` (`fixtures.parse_fixture_type`, ветка `strobe` в `lines_for`); `has` там же прячет слайдеры в панели (`attributeVisible` в `light.js`). Формат `ChannelSet` в экспорте 3.9.60 не проверен: сырой файл лежит в `diag/fixture_type_<n>.xml`.
- Что не проверено на пульте: `Goto Cue 1 Executor N Fade T` (плавные сцены; синтаксис из руководства MA2 3.9, с. 1110), угаданные головы по имени типа.
