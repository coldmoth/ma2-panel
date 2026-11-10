# Что программа отправляет в MA2: каждое действие панели

Базовая таблица получена `scripts/command_map.py` на mock; строки сцен/затемнения обновлены вручную по этапу 1 (2026-11-10). Полное обоснование и runtime-предпосылки: [ma2-command-evidence.md](ma2-command-evidence.md). Это не проверка реального пульта.
Приборы 12 и 14 и сцена 1.101 разрешены, `store_execs` = 2.150, allow_master и allow_page_change включены.
Классы: LIVE живой свет; LIVE* отдельный флаг; READ только чтение; STORE запись данных MA2; SHOW загрузка/сохранение шоу; SYSTEM экспорт/подсветка; PANEL только конфиг панели.

Зона подсветки ограничена приборами 12 и 14 через highlight.exclude во всех режимах; level=100.
Каждая ячейка — отдельный запуск; показаны строки последнего действия, без первоначального входа и подготовки; повторный вход и ListVar внутри show_load включены. При отказе подготовки показана его причина; последующее действие не запускается. При отказе после отправки показаны и строки, и причина. Результат mock не подтверждает работу настоящей MA2.

## Новые флаги выключены (по умолчанию)

`allow_fixture_read`, `allow_highlight`, `allow_show_load`, `allow_show_save`, `allow_group_store` = false.

| Класс | Действие панели | test | store | full |
|---|---|---|---|---|
| LIVE | Выбор группы/приборов | ничего не уходит | ничего не уходит | ничего не уходит |
| LIVE | Снять выбор | ничего не уходит | ничего не уходит | ничего не уходит |
| LIVE | Dim 40 | `Fixture 12 + 14`<br>`At 40` | `Fixture 12 + 14`<br>`At 40` | `Fixture 12 + 14`<br>`At 40` |
| LIVE | Dim 40, переход 3 с | `Fixture 12 + 14`<br>`At 40 Fade 3` | `Fixture 12 + 14`<br>`At 40 Fade 3` | `Fixture 12 + 14`<br>`At 40 Fade 3` |
| LIVE | Цвет R100 G0 B50 | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` |
| LIVE | Strobe 20 | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` |
| LIVE | Шаг Pan + | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` |
| LIVE | Задать позицию | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` |
| LIVE | Pan/Tilt (пад) | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` |
| LIVE | Zoom 60 | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` |
| LIVE | Focus 60 | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` |
| LIVE | Сцена Cue 1 (1.101) | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` |
| LIVE | Сцена Off (1.101), текущий серверный Fade T | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` |
| LIVE | «Blackout MA2» / возврат | ОТКАЗ: нужен full | ОТКАЗ: нужен full | Фиксированное nonce-чтение Grand с %, журнал → `SpecialMaster 2.1 At 0` → чтение. Повтор: прежний уровень при том же контексте и текущем 0; B.O./Programmer/Executor сохраняются. |
| LIVE* | Общая яркость 50 (allow_master) | `Master 2.1 At 50` | `Master 2.1 At 50` | `Master 2.1 At 50` |
| LIVE* | Открыть страницу 2 (allow_page_change) | `Page 2` | `Page 2` | `Page 2` |
| LIVE | Остановить передачу | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | Обновить сцены из пульта | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` |
| STORE | Перезапись сцены (отключена) | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor |
| STORE | Новая сцена (exec+confirm, selected) | ОТКАЗ: режим test | Свежие ListVar + `List Executor 2.150` → `Fixture 12 + 14` → `Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected` → `Assign Cue 1 Executor 2.150 /Trig=Go` → Label и проверка Cue | Свежие ListVar + `List Executor 2.150` → `Fixture 12 + 14` → `Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected` → `Assign Cue 1 Executor 2.150 /Trig=Go` → Label и проверка Cue |
| STORE | Переименовать сцену | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме store | `Label Executor 1.101 "X"` |
| STORE | Назвать страницу | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме store | `Label Page 2 "X"` |
| SYSTEM | fixtures_fetch (после show_bind) | ОТКАЗ: получение приборов заблокировано: allow_fixture_read | ОТКАЗ: получение приборов заблокировано: allow_fixture_read | ОТКАЗ: получение приборов заблокировано: allow_fixture_read |
| READ | show_identify | `ListVar` | `ListVar` | `ListVar` |
| SYSTEM | highlight: первый выбор 12 (после edit_begin) | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight |
| SYSTEM | highlight: смена 12 → 14 | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight |
| SYSTEM | highlight_off (после edit_begin и highlight 12) | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight | ОТКАЗ: подсветка заблокирована: allow_highlight |
| READ | shows_list | `ListShows` | `ListShows` | `ListShows` |
| SHOW | show_load Demo (confirm_name="Demo", ack_unsaved=true) | ОТКАЗ: загрузка заблокирована: allow_show_load | ОТКАЗ: загрузка заблокирована: allow_show_load | ОТКАЗ: загрузка заблокирована: allow_show_load |
| SHOW | show_save (после show_identify, confirm_name="Mock show") | ОТКАЗ: сохранение заблокировано: allow_show_save | ОТКАЗ: сохранение заблокировано: allow_show_save | ОТКАЗ: сохранение заблокировано: allow_show_save |
| PANEL | Запомнить пресет (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Новая группа панели (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Расстановка на плане (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Убрать сцену из панели (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Форма зала (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Служебный прибор (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | ma2_read: группы и пресеты MA2 | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` |
| READ | ma2_import: группа 1, пресеты (+ запись в config.json) | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` |
| LIVE | Пресет цвета MA2 4.1 для выбора | `Fixture 12 + 14`<br>`At Preset 4.1` | `Fixture 12 + 14`<br>`At Preset 4.1` | `Fixture 12 + 14`<br>`At Preset 4.1` |
| SHOW | group_store_ma2: группа панели → Group 11 (проверка пустого номера) | ОТКАЗ: запись группы заблокирована: allow_group_store | ОТКАЗ: запись группы заблокирована: allow_group_store | ОТКАЗ: запись группы заблокирована: allow_group_store |

## Новые флаги включены

`allow_fixture_read`, `allow_highlight`, `allow_show_load`, `allow_show_save`, `allow_group_store` = true.

| Класс | Действие панели | test | store | full |
|---|---|---|---|---|
| LIVE | Выбор группы/приборов | ничего не уходит | ничего не уходит | ничего не уходит |
| LIVE | Снять выбор | ничего не уходит | ничего не уходит | ничего не уходит |
| LIVE | Dim 40 | `Fixture 12 + 14`<br>`At 40` | `Fixture 12 + 14`<br>`At 40` | `Fixture 12 + 14`<br>`At 40` |
| LIVE | Dim 40, переход 3 с | `Fixture 12 + 14`<br>`At 40 Fade 3` | `Fixture 12 + 14`<br>`At 40 Fade 3` | `Fixture 12 + 14`<br>`At 40 Fade 3` |
| LIVE | Цвет R100 G0 B50 | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` | `Fixture 12 + 14`<br>`Attribute "ColorRGB1" At 100`<br>`Attribute "ColorRGB2" At 0`<br>`Attribute "ColorRGB3" At 50` |
| LIVE | Strobe 20 | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` | `Fixture 12 + 14`<br>`Attribute "Strobe" At 20` |
| LIVE | Шаг Pan + | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` | `Fixture 12 + 14`<br>`Attribute "Pan" At + 2` |
| LIVE | Задать позицию | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` | `Fixture 12 + 14`<br>`Attribute "Pan" At 0`<br>`Attribute "Tilt" At 0` |
| LIVE | Pan/Tilt (пад) | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` | `Fixture 12 + 14`<br>`Attribute "Pan" At 27`<br>`Attribute "Tilt" At -13.5` |
| LIVE | Zoom 60 | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` | `Fixture 12 + 14`<br>`Attribute "Zoom" At 60` |
| LIVE | Focus 60 | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` | `Fixture 12 + 14`<br>`Attribute "Focus" At 60` |
| LIVE | Сцена Cue 1 (1.101) | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` | Свежее ListVar + фиксированное nonce-чтение ручной Cue 1/LTP/Soft LTP/Cmd; `Masterfade T Executor` прежних запусков панели в текущем плане/шоу → `Goto Cue 1 Executor 1.101 Fade T` → их `Off Executor` |
| LIVE | Сцена Off (1.101), текущий серверный Fade T | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` | `Masterfade T Executor 1.101`<br>`Off Executor 1.101` |
| LIVE | «Blackout MA2» / возврат | ОТКАЗ: нужен full | ОТКАЗ: нужен full | Фиксированное nonce-чтение Grand с %, журнал → `SpecialMaster 2.1 At 0` → чтение. Повтор: прежний уровень при том же контексте и текущем 0; B.O./Programmer/Executor сохраняются. |
| LIVE* | Общая яркость 50 (allow_master) | `Master 2.1 At 50` | `Master 2.1 At 50` | `Master 2.1 At 50` |
| LIVE* | Открыть страницу 2 (allow_page_change) | `Page 2` | `Page 2` | `Page 2` |
| LIVE | Остановить передачу | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | Обновить сцены из пульта | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` |
| STORE | Перезапись сцены (отключена) | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor |
| STORE | Новая сцена (exec+confirm, selected) | ОТКАЗ: режим test | Свежие ListVar + `List Executor 2.150` → `Fixture 12 + 14` → `Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected` → `Assign Cue 1 Executor 2.150 /Trig=Go` → Label и проверка Cue | Свежие ListVar + `List Executor 2.150` → `Fixture 12 + 14` → `Store Executor 2.150 Cue 1 /Source=Output /Use=Allforselected` → `Assign Cue 1 Executor 2.150 /Trig=Go` → Label и проверка Cue |
| STORE | Переименовать сцену | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме store | `Label Executor 1.101 "X"` |
| STORE | Назвать страницу | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме store | `Label Page 2 "X"` |
| SYSTEM | fixtures_fetch (после show_bind) | `ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013308"`<br>`List FixtureType` | `ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013308"`<br>`List FixtureType` | `ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013308"`<br>`List FixtureType` |
| READ | show_identify | `ListVar` | `ListVar` | `ListVar` |
| SYSTEM | highlight: первый выбор 12 (после edit_begin) | `Fixture 14`<br>`At 0`<br>`Fixture 12`<br>`At 100` | `Fixture 14`<br>`At 0`<br>`Fixture 12`<br>`At 100` | `Fixture 14`<br>`At 0`<br>`Fixture 12`<br>`At 100` |
| SYSTEM | highlight: смена 12 → 14 | `Fixture 12`<br>`At 0`<br>`Fixture 14`<br>`At 100` | `Fixture 12`<br>`At 0`<br>`Fixture 14`<br>`At 100` | `Fixture 12`<br>`At 0`<br>`Fixture 14`<br>`At 100` |
| SYSTEM | highlight_off (после edit_begin и highlight 12) | `Fixture 12 + 14`<br>`Off Fixture 12 + 14` | `Fixture 12 + 14`<br>`Off Fixture 12 + 14` | `Fixture 12 + 14`<br>`Off Fixture 12 + 14` |
| READ | shows_list | `ListShows` | `ListShows` | `ListShows` |
| SHOW | show_load Demo (confirm_name="Demo", ack_unsaved=true) | `ListShows`<br>`LoadShow "Demo" /nosave`<br>`login "panel" ""`<br>`ListVar`<br>`ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013311"`<br>`List FixtureType` | `ListShows`<br>`LoadShow "Demo" /nosave`<br>`login "panel" ""`<br>`ListVar`<br>`ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013314"`<br>`List FixtureType` | `ListShows`<br>`LoadShow "Demo" /nosave`<br>`login "panel" ""`<br>`ListVar`<br>`ListVar`<br>`Export Fixture 1 Thru 9999 "panel_fixtures_013318"`<br>`List FixtureType` |
| SHOW | show_save (после show_identify, confirm_name="Mock show") | `ListVar`<br>`SaveShow` | `ListVar`<br>`SaveShow` | `ListVar`<br>`SaveShow` |
| PANEL | Запомнить пресет (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Новая группа панели (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Расстановка на плане (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Убрать сцену из панели (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Форма зала (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| PANEL | Служебный прибор (только config.json) | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | ma2_read: группы и пресеты MA2 | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999` |
| READ | ma2_import: группа 1, пресеты (+ запись в config.json) | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999`<br>`Export Group 1 Thru 999 "panel_groups_013319"` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999`<br>`Export Group 1 Thru 999 "panel_groups_013319"` | `List Group 1 Thru 999`<br>`List Preset 4.1 Thru 4.999`<br>`List Preset 2.1 Thru 2.999`<br>`Export Group 1 Thru 999 "panel_groups_013319"` |
| LIVE | Пресет цвета MA2 4.1 для выбора | `Fixture 12 + 14`<br>`At Preset 4.1` | `Fixture 12 + 14`<br>`At Preset 4.1` | `Fixture 12 + 14`<br>`At Preset 4.1` |
| SHOW | group_store_ma2: группа панели → Group 11 (проверка пустого номера) | `List Group 11`<br>`Fixture 12`<br>`Store Group 11 "G"` | `List Group 11`<br>`Fixture 12`<br>`Store Group 11 "G"` | `List Group 11`<br>`Fixture 12`<br>`Store Group 11 "G"` |

Обновление (`scene_create replace:true`) не использует Delete target: сначала
новый Cue 1 в проверенном пустом spare, резерв target Cue 1 → spare Cue 2,
затем Copy spare Cue 1 → target Cue 1 /CueOnly /Overwrite. Backup также использует /CueOnly; интерактивный выбор метода не допускается. Перед стадиями читается шоу.
Другие формы Overwrite не разрешены. Spare остаётся для ручного восстановления.

Уточнение 2026-11-11: область Masterfade/Off ограничена прежними попытками Goto
панели в текущем плане/шоу; каталог и клиентский swap не дают права на Off.
Свежий Off-readback снимает владение, устаревший/неизвестный — нет. После смены
контекста и перезапуска владельцы не угадываются.
