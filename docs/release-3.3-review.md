# Независимый review — 2026-11-11

С разрешения владельца запущен один локальный `codex review`, read-only,
без Clodex и изменения модели/reasoning. База d95220f, проверенный commit 59a55ab.
Рецензент получил критерии выпуска и diff без истории основного чата.
Полный локальный журнал: /tmp/ma2-v330-independent-review.log.

Итоговое замечание одно: **P2 — устаревшая команда после transport drain**.
После таймаута новая строка могла ждать старый prompt; Blackout менял epoch,
но `MA2Link.send` затем отправлял старую строку. Воспроизведено рецензентом
на master и основным агентом на RGB; без реальной MA2.

Исправление: `send(valid=...)` повторяет проверку под transport lock и после
drain, непосредственно перед `_exchange`. Переданы ticket/контекст/freshness
из execute, MA2-групп и scene writes. Отменённая строка получает `not_sent`.
Регрессионный RED/GREEN: /tmp/ma2-v330-late-red.log и
/tmp/ma2-v330-drain-green.log; смежные проверки /tmp/ma2-v330-review-fixes.log.
Повторного помощника не запускали. Основной агент самостоятельно проверил фикс.

Дополнительные проверки основного агента: reuse с одинаковыми именами/типами,
Undo старого конфига после неизвестного Copy, причины первого CI.
Journal committing/completed/нечитаемый блокирует Go независимо от config Undo;
preparing прежней сцены в том же шоу не означает изменения target.
Windows venv запускает настоящий Python с сохранением venv через штатный
`__PYVENV_LAUNCHER__`; строгая проверка health PID сохранена.
Основание: CPython 3.12.10 [launcher.c](https://github.com/python/cpython/blob/v3.12.10/PC/launcher.c#L1855)
и [getpath.py](https://github.com/python/cpython/blob/v3.12.10/Modules/getpath.py).

Рецензент не проводил аппаратную приёмку. Native Windows и итоговый commit
подтверждаются последующим CI; ограничения физического света остаются явными.

## Короткое продолжение той же review-сессии

Тот же разрешённый рецензент (session 01a1c796-b552-7842-8890-7f8a42487b27)
проверил только исправления 59a55ab..6e8d751 и Windows watch_orphan patch:
**no findings, P2 закрыт**. Подтверждены проверка после drain до write,
конкурирующие identities, journal guard и Windows launch/handoff. Второго
помощника нет; модель/reasoning не менялись. Лог /tmp/ma2-v330-review-followup.log.
Фактический Windows source-worker всё ещё требует повторного CI.
