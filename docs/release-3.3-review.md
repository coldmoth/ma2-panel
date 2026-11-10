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
