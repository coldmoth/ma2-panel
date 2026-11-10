# Исправления review этапа 4
Основание: явное задание владельца, 2026-11-10. Выполнение самостоятельно, без помощников.

1. Интеграция: опубликованный main/v3.2.5 d95220f; исходный staged worktree
   d707ba2 + merge fff12ef (d80babb), база d919910. Трёхсторонний перенос
   backend в ma2panel/, сохранение корневого recovery launcher, resources,
   публичных исправлений DMX/диагностики, Windows release/update API.
2. A: регрессии серверного отказа dim/color/move/jog/nudge во время recovery,
   извлечённых throttle intents и остановки частичной операции при reconnect.
   Проверка blocked/execute, generation/context до каждой отправки.
3. B: регрессии повторного ID другого имени/типа, перенумерации, конфликтов
   соответствия, групп и сцен. Явный выбор сохраняет/разрывает привязки.
4. C: проверка официальной grandMA2 3.9 MasterFade/Off Time. Регрессия ручного
   Off после изменения shared Fade; обновление Masterfade непосредственно
   перед Off, без таймеров и непроверенных вариантов команд.
5. D: регрессии measured RGB=0, dimmer-only, stale/unknown/last-sent.
   Исправление общего расчёта вывода, проверка плана в Node и двух браузерах.
6. Адресные pytest/Node, mock HTTP/WS, Chromium/WebKit, миграции,
   packaging/update/rollback/journals. После стабилизации один полный pytest.
   Нативную Windows и физическую MA2 не подменять mock/эмуляцией.
7. Обновить audit/TASK_STATE/CODEMAP/spec-history и индекс. Никакого релиза,
   публикации, merge main или изменения исходных worktree.

Review focus: reconnect при ожидании action_lock/между строками; reused ID в
группах/пресетах; частичный Store/журналы; Blackout/Undo/старые клиенты;
сохранение public v3.2.5 readback/updater и стабильного launcher.
