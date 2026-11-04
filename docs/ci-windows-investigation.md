# Windows CI перед 3.1.1 — 2026-11-04

## Доказательства и границы вывода

Запуск: https://github.com/coldmoth/ma2-panel/actions/runs/41892963016
SHA: `89bc98ca219b69fb3d5eb4079c6a3ea2decc8a88`, `workflow_dispatch`, attempt 1.
Windows job `126795529087` начался 19:03:10 UTC, regression step — 19:03:24 UTC.
GitHub check annotation: `The job has exceeded the maximum execution time of 20m0s`.
Job завершён 19:28:10 UTC (25 минут, включая завершение после лимита).
Linux и browser завершились успешно; ZIP не собирался, draft-release skipped.

Подтверждён timeout job. Более нового запуска после этого run в Actions нет;
отмена новым workflow не объясняет последний сбой. Доказательств ручной отмены
последнего run нет. Предыдущие cancel/force-cancel отмечены в TASK_STATE, но
не объясняют зависание последнего запуска.

API job logs вернул `BlobNotFound`; архив run содержит только Linux/browser logs.
Windows artifact отсутствует. Статус regression step остался `in_progress` даже
после завершения job. Нельзя доказать, какой тест выполнялся, был ли traceback,
завис pytest/его потомок, запуск shell или инфраструктура runner. Пятиминутный
step timeout не обеспечил наблюдаемого завершения. Причина этой задержки неизвестна.
Ни отдельный тест, ни subprocess виновником не объявляются.

Локальный исходный набор на macOS: 113 passed, 1 Windows-only skipped,
11 subtests, 16.71 s. Зависание не воспроизведено; это не Windows-приёмка.

## Изменения

- Workflow concurrency разделена по event и ref. Push/PR сохраняют отмену устаревших
  проверок; manual runs одной ветки не отменяют выполняющуюся manual проверку.
- Создание draft дополнительно сериализовано общей группой репозитория,
  `cancel-in-progress: false`. Защита от конфликтующих публикаций сохранена.
  GitHub по умолчанию хранит только один pending run в группе: новая manual заявка
  может заменить ожидающую, но не уже выполняющуюся. Не ставить пачку запусков.
- Windows pytest запускается непосредственно Python из `.venv`, под внешним
  watchdog 240 s; лимиты Actions 5/20 минут не увеличены. Это диагностика и
  ограничение зависания, а не доказанное устранение неизвестной причины.
- `-u -vv -s` сохраняют текущий node id/вывод; faulthandler через 60 s показывает
  стек долгого теста. `pytest.log` получает stdout/stderr непосредственно в файл,
  без ожидания EOF наследуемой дочерними процессами pipe.
- Watchdog сохраняет command/PID/reason/код процесса в `result.json`, при своём
  timeout возвращает 124, снимает PID/PPID/имена процессов и завершает только
  дерево своего pytest (`taskkill /T /F` на Windows, process group на POSIX).
  Это не меняет продуктовые команды, updater или логику MA2.
- Артефакт `windows-mock-log` загружается через `always()` и на успехе.
  `test-results/windows/`: `pytest.log`, `pytest.xml`, `result.json`,
  `processes.log`/`cleanup.log` при timeout; `tmp/` сохраняет worker/startup logs.
  Если runner потерян или принудительно уничтожен, upload не гарантирован;
  тогда смотреть check annotations и runner diagnostics в GitHub.

## Единственный следующий запуск

После отдельного разрешения владельца перенести только эти исправления в очищенную
`dist/release-repo/` (публичная база `89bc98c`), отправить её main и выполнить ровно один
`workflow_dispatch` workflow `ci.yml`, ref `main`, `draft_tag` пустой.
Push автоматически выполнит обычный Linux CI; ручной запуск проверит все три jobs.
Старый run не перезапускать: он использует старый workflow.

Успех Windows: regression exit 0 → Build delivered Windows x64 and USB bundles →
Windows delivered BAT/runtime/rollback → delivered mock HTTP/WebSocket →
`windows-release-candidate` с тремя ZIP, SHA256 и build-inputs.json.
У build нет дополнительного условия: успех regression разрешает следующий шаг;
любой ненулевой код оставляет сборку заблокированной. Не применять continue-on-error.
Draft-tag пустой, поэтому ни tag, ни Release этот запуск не создаст.

До публикации 3.1.1 нужны зелёная Windows-проверка доставленных ZIP, анализ её
артефактов и отдельное разрешение владельца на публикацию. Проверки MA2/площадки
и UAC/ACL/locked files/сбоев питания не заменяются mock/локальным pytest.

## Локальные проверки 2026-11-04

- Watchdog RED: 3 теста упали из-за отсутствующего модуля; GREEN: 3 passed.
  Реальные дочерние процессы: exit 0, exit 7, timeout 124 и остановка потомка.
- Новый regression runner: 116 passed, 1 skipped, 11 subtests, 20.14 s, exit 0.
- Полный pytest: 1332 passed, 1 skipped, 11 subtests; JUnit: 1344 cases,
  failures/errors 0, 90.487 s, exit 0. Имеется прежний StarletteDeprecationWarning.
- Node `tests/panel-v4.cjs`: exit 0.
- `build_windows.py --verify-reproducible`: exit 0, три ZIP побайтно равны.
  Это кросс-сборка; embedded Python/BAT на macOS не исполнялись.
- Контрольный pytest `test_stall` с faulthandler 0.2 s и watchdog 3 s:
  node id и стек сохранены, snapshot создан, exit 124 получен ожидаемо.
- YAML разобран Ruby/Psych; `git diff --check` прошёл. Code-index пересоздан
  во временный файл и совпал с отслеживаемым (scripts в индекс не входят).
- Полные локальные логи/исходные API-ответы: `/tmp/ma2-windows-ci/`;
  regression artifacts: `test-results/windows/`. В Git сырые логи не включены.
- Независимый review и Windows runtime-проверка не проводились; субагентов/Clodex
  не было. Продуктовая логика, spec, пользовательские данные не изменены.
