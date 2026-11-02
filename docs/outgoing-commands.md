# Что программа отправляет в MA2: каждое действие панели

Сгенерировано `scripts/command_map.py` на имитации пульта (mock): это реальные строки, которые уходят в Telnet.
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
| LIVE | Сцена Go (1.101) | `ClearAll`<br>`Go Executor 1.101` | `ClearAll`<br>`Go Executor 1.101` | `ClearAll`<br>`Go Executor 1.101` |
| LIVE | Сцена Off (1.101) | `Off Executor 1.101` | `Off Executor 1.101` | `Off Executor 1.101` |
| LIVE | «Погасить всё» | `Off Executor 1.101`<br>`Fixture 12 + 14`<br>`At 0` | `Off Executor 1.101`<br>`Fixture 12 + 14`<br>`At 0` | `Off Executor 1.101`<br>`Fixture 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12 + 13 + 14 + 15 + 16 + 17 + 18 + 19 + 20 + 21 + 22 + 23 + 24`<br>`At 0` |
| LIVE* | Общая яркость 50 (allow_master) | `Master 2.1 At 50` | `Master 2.1 At 50` | `Master 2.1 At 50` |
| LIVE* | Открыть страницу 2 (allow_page_change) | `Page 2` | `Page 2` | `Page 2` |
| LIVE | Остановить передачу | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | Обновить сцены из пульта | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` |
| STORE | Перезапись сцены (отключена) | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor |
| STORE | Новая сцена (exec+confirm, проверка пустого места) | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | `List Executor 2.150`<br>`StoreLook Executor 2.150 Cue 1 /Source=Output`<br>`Label Executor 2.150 "Тест"` | `List Executor 2.150`<br>`StoreLook Executor 2.150 Cue 1 /Source=Output`<br>`Label Executor 2.150 "Тест"` |
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
| LIVE | Сцена Go (1.101) | `ClearAll`<br>`Go Executor 1.101` | `ClearAll`<br>`Go Executor 1.101` | `ClearAll`<br>`Go Executor 1.101` |
| LIVE | Сцена Off (1.101) | `Off Executor 1.101` | `Off Executor 1.101` | `Off Executor 1.101` |
| LIVE | «Погасить всё» | `Off Executor 1.101`<br>`Fixture 12 + 14`<br>`At 0` | `Off Executor 1.101`<br>`Fixture 12 + 14`<br>`At 0` | `Off Executor 1.101`<br>`Fixture 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10 + 11 + 12 + 13 + 14 + 15 + 16 + 17 + 18 + 19 + 20 + 21 + 22 + 23 + 24`<br>`At 0` |
| LIVE* | Общая яркость 50 (allow_master) | `Master 2.1 At 50` | `Master 2.1 At 50` | `Master 2.1 At 50` |
| LIVE* | Открыть страницу 2 (allow_page_change) | `Page 2` | `Page 2` | `Page 2` |
| LIVE | Остановить передачу | ничего не уходит | ничего не уходит | ничего не уходит |
| READ | Обновить сцены из пульта | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` | `ListVar`<br>`List Page`<br>`List Executor 1.1 Thru 1.250` |
| STORE | Перезапись сцены (отключена) | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor | ОТКАЗ: перезапись существующей сцены отключена: запишите новую сцену в пустой executor |
| STORE | Новая сцена (exec+confirm, проверка пустого места) | ОТКАЗ: запись в пульт и служебные действия заблокированы в режиме test | `List Executor 2.150`<br>`StoreLook Executor 2.150 Cue 1 /Source=Output`<br>`Label Executor 2.150 "Тест"` | `List Executor 2.150`<br>`StoreLook Executor 2.150 Cue 1 /Source=Output`<br>`Label Executor 2.150 "Тест"` |
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
