# Финальный аудит 3.3.0 — 2026-11-11

База: публичный main/v3.2.5 d95220f. Исходные 95 staged-файлов сохранены и
включены в интеграцию. Основной checkout и прежние worktree не изменяются.
Ни реальная MA2, ни рабочее шоу в этой сессии не подключались.

## Подтверждённые дефекты

1. A: перенос 23→31 терял старый источник, когда новый прибор занимал 23.
   Кандидаты строятся до применения выборов; неизменные идентичности резервируются,
   конкурирующие переносы требуют явного взаимно однозначного выбора.
   Группы, MA2-группы, pos-пресеты, выделение и метаданные fixtures сцен обновляются
   одновременно. Другие сохранённые планы имеют собственный Patch и сохраняются.
2. B: ticket терялся для ma2_group_go. После Blackout/отключения клиента мог
   пройти Group. Теперь ticket проверяется после lock и чтения, до/после отправки.
   Аналогичная воспроизведённая гонка group_store_ma2 исправлена тем же механизмом.
3. C: три запуска при 100 сохранённых сценах посылали 297 Off. Теперь ровно два:
   только прежние запуски панели текущего плана/шоу. Пробы относятся к затронутым
   адресам. Неизвестный ответ Goto сохраняет возможного владельца; свежий Off
   readback исключает лишнее снятие, устаревший не исключает. Клиентский swap
   и внешние playback не расширяют область; после перезапуска владельцы неизвестны.
4. runtime-ID зависел от LF/CRLF Git checkout. Канонический CRLF сохраняет
   опубликованный Windows-ID v3.2.5 без изменения зависимостей/uv.lock.

Все A/B/C воспроизведены регрессиями до исправления. Четыре старых теста массового
Off адаптированы: предыдущая сцена реально запускается перед crossfade; клиент
не может перечислением swap выключить произвольный каталог.

## Область повторной проверки

- Сцены/crossfade/ручной Off/Blackout: scene_runtime, execute и send context;
  stage1/stage4 integration, scene probes и release33; пересечения и быстрые
  переключения проверены моделью, внешний 9.101 остаётся независимым.
- Store/replace/unknown/Programmer: резерв пустого адреса, журнал до записи,
  CueOnly copy, запрет автоматического rollback/replay; stage1 и integration.
- Undo/очереди/reconnect/WS: tickets, blackout_epoch, action_lock, throttle,
  freshness basis и multi-client tests. Patch-инвалидация history/intent сохранена.
- DMX/TTL/FixtureType: nonce, частичные блоки, retry/backoff, unknown attrs,
  RGB=0/неполный RGB; stage2 pipeline/state, dmx recovery, profile freshness.
- Pan/Tilt: независимые оси и относительные жесты; Node и browser joystick tests.
- UI/input: Node; HTTP/WS full/simple; Chromium/WebKit общие и stage3 сценарии,
  четыре viewport, touch, drag/text stability, store/rewrite/conflict/disconnect.
  PNG tablet landscape/portrait осмотрены; новых Cue/Executor строк UI не добавлено.
- Миграции/updater/backup: полный pytest и адресные release/update tests.
  Настоящий опубликованный v3.2.5 Windows ZIP проверен SHA256, его runtime guard
  и updater принимают кандидат; новый rollback возвращает 3.2.5 с побайтным
  сохранением синтетических config/settings/secret/shows/backups/diag/journals.
  Локально это host Python; native embedded Windows проверяет CI.

## Свидетельства и ограничения

Полный локальный pytest: 1525 PASS, 1 SKIP, 0 failures/errors (118.047 с);
JUnit /tmp/ma2-v330-final-pytest.xml. После правки runtime-ID и дополнения
регрессий адресный release/update/browser-update набор PASS;
/tmp/ma2-v330-runtime-focused.log и /tmp/ma2-v330-precommit.log.
Node: /tmp/ma2-v330-node.log; HTTP/WS: /tmp/ma2-v330-httpws.log.
Браузер: /tmp/ma2-v330-browser/, /tmp/ma2-v330-stage3/;
миграция с runtime guard: /tmp/ma2-v330-migration-final.log.

Независимый локальный рецензент разрешён владельцем; результат и CI добавляются
после выполнения. Clodex не применяется; счётчик подписочной квоты недоступен.
Историческая onPC 3.9.63.11 не подтверждает новую интеграцию и физический свет.
Осталась целевая MA2/зал-приёмка hardware-acceptance.md и hall-test-plan.md §12–13.
Публикация допустима только после независимого review и программных gates.
