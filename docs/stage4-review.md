# Повторное независимое review — пакетная интеграция, 2026-11-10

Работать с codex/stage4-review-fixes, база публичного main/v3.2.5 d95220f,
worktree /path/to/ma2-panel
Это задание следующему reviewer, не заключение о прохождении review.
Не подключать MA2, не запускать без --mock, не публиковать локальную историю.

Проверить ma2panel/bridge.py, commands.py, fixtures.py, scene_runtime.py,
link.py, safety.py, exports.py, update.py, release.py; static/ и новые регрессии.
Root bridge.py остаётся штатным launcher до импорта backend. Особое внимание:

1. Recovery до/после action_lock, между строками, transport lock, поздний WS
   после завершения recovery; совместимость актуального и старого клиента.
2. Reused ID/неполные legacy метаданные, неоднозначная/уникальная перенумерация,
   ссылки групп и positional presets, сохранность конфигурации при отказе диска.
3. plan_epoch после импорта и его принятие только синхронным Patch readback:
   gen/show/stop остаются исходными, после их смены новых команд нет.
4. Manual Off: Masterfade из серверного общего Fade перед каждой Off;
   ошибки/быстрые повторения не создают отложенных команд или replay.
5. Blackout/crossfade/Undo/Store: признаки unknown, безопасные резервы Cue,
   журналы до записи и сохранность при update/rollback; несовместимый контекст.
6. RGB=0, dimmer-only, отсутствующие каналы, stale/unknown/last-sent;
   UI не изменяет измеренный Dimmer ради условного свечения.
7. Публичные исправления 3.2.5, resources/launcher/updater/Windows payload,
   отсутствие root backend-возврата и потери пользовательских данных.
8. Концертный UI этапа 3: видимость сцен рядом с планом, выбор/поиск,
   жесты/текст, все инструменты подготовки и персональная видимость.

Свежие результаты и ограничения — docs/stage4-audit.md и TASK_STATE.md.
Нативная Windows x64 и целевая MA2/зал остаются отдельными проверками.

---

## Историческое задание исходного stage4-audit

# Передача на независимый review этапа 4 — 2026-11-10

**Это задание reviewer, не заключение о прохождении.** Полное задание пользователя
и матрица: stage4-audit.md. Исходная версия d919910; объединяются d707ba2 и
fff12ef (включает d80babb). Работать в codex/stage4-audit; исходный dirty checkout
не трогать. Не подключать MA2 и не запускать мост без --mock.

## Граница патча

Проверить полный совместный diff относительно d919910 и отдельно исправления
этапа 4: bridge.py, scene_runtime.py, link.py, safety.py, mock.py, selfcheck.py,
static/app.js, static/simple.js/html, static/light.js, release.py, update.py,
scripts/windows_delivered.py, регрессии и документы. Никаких config/settings/
secret.env, пользовательских шоу и сырых диагностик во внешнем пакете.

## Приоритеты review

1. Источник команд и guards: CueOnly обязателен, Overwrite только Cue 1→1,
   mode/store_execs не расширены; общая Lua/NoConfirm не открыты.
2. read_nonce: только однозначный свежий nonce; максимум 3 completed ListVar,
   пауза 50 мс; ошибка транспорта/свежий unknown не запускает повтор записи.
3. Probe: реальный List Executor и его Normal/SoftLTP/Chaser; единственная
   Cue 1/Go, CMD единственной части по точному имени. Nil slot 0 допустим лишь
   с подтверждённой Cue 1; чужие/неизвестные топологии не считаются безопасными.
4. Store: новый Output/spare, старый Cue 2, журнал до commit, отказ диска,
   label failure, Stop/reconnect/show/ticket между каждой стадией. Нет Delete
   target, автоматического повтора/компенсации неизвестного результата.
5. Grand: исходные 0/дробный уровень, известное %; журнал перед записью;
   максимум 3 новых замера target без повторного At. Чужой Grand/новый контекст,
   stale/missing nonce, restart и unknown не должны разрешать восстановление.
6. Epoch/barrier: pending/fades/извлечённый intent/in-flight/Undo/MA2 preset,
   поздний WS и второй клиент; сброс доказательств не выдаётся за ClearAll пульта.
7. Login: второй Please login prompt, фрагменты/тайм-аут/отказ; login не
   пересылается, ListVar подтверждает пользователя. Проверить custom login_ok
   и require_prompt=false, закрытие соединения и отмену фоновых задач.
8. Shared Fade/revision и новые поколения swatch/RGB slider: поздние события
   запрещены, новое намерение работает в сохранённом DOM; unknown в обоих UI.
9. Миграции/legacy данные и Windows: selfcheck cp1252/report, строгая cleanup
   граница; test body failures не маскируются. user_data_names сохраняет Blackout
   и точные имена scene-write journals, в том числе с повреждённым содержимым.
   Проверить backup/restore/transfer/update/rollback. Отличать emulation от native x64.

## Свидетельства и границы

Актуальные проверки/числа — stage4-audit.md и TASK_STATE.md. Python/Node,
Chromium/WebKit и onPC 3.9.63.11 проверяются отдельно. Реальные Cue пустые,
приборам/Output, физическим fade/DMX/Pan/Tilt и целевой 3.9.60 это не приёмка.
Нет независимого reviewer: Clodex почти исчерпан, платного вызова не было.
Особенно не принимать отсутствие ошибки MA2 или занятый Executor за проверку
содержимого. Полный лог с паролями/настройками reviewer не нужен.

Результат reviewer: Critical/Important с file:line, сценарием воспроизведения,
последствиями и минимальным исправлением; отдельно необязательные замечания.
Нужен явный список непроверенного и оценка готовности к коммиту/следующему этапу.
Не коммитить, не менять контракт, не запускать команды на рабочем шоу.
