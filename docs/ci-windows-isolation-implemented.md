# Временная изоляция Windows CI — 2026-11-05

Реализация согласованного `ci-windows-isolation-plan.md`; исходное зависание
Windows всё ещё не объяснено. Watchdog patch применён отдельным коммитом.
Продуктовая логика MA2 и доставляемые скрипты не менялись.

| Job / группа | Исходные IDs | Сейчас | Тест, s | Группа, s |
|---|---:|---:|---:|---:|
| Windows diagnostic (release) | 18 | 18 | 20 | 180 |
| Windows diagnostic (update) | 32 | 32 | 30 | 180 |
| Windows diagnostic (browser-unit) | 8 | 8 | 30 | 180 |
| Windows diagnostic (browser-worker) | 1 | 1 | 90 | 120 |
| Windows diagnostic (selfcheck) | 5 | 5 | 30 | 180 |
| Windows diagnostic (rdm) | 50 | 50 | 15 | 180 |
| Windows diagnostic (watchdog) | 3 | 4 | 30 | 120 |
| Всего | 117 | 118 | | |

Watchdog: новый blocked-console regression. Все прежние node IDs сохранены.
`scripts/ci_windows_groups.json` хранит количество и SHA256 отсортированных
полных IDs каждой группы вместо огромных RDM параметров. На каждом runner
реальная collection всех шести прежних файлов сверяется с этим manifest:
неизвестный, пропущенный, повторный или переименованный тест даёт ошибку.
Полные IDs загружаются в artifacts. Для изменения состава нужен осмотр manifest,
автоматически принимать новую collection как эталон нельзя.

Каждый тест запускается отдельным pytest, его ID выбирается plugin по SHA256:
это позволяет не передавать RDM параметры размером более Windows command-line
limit. Проверяется выбор ровно одного теста; его исходный skip/failure сохраняется.
Отдельные каталоги содержат stdout+stderr, result.json, JUnit, tmp/worker logs;
JSONL немедленно фиксирует старт/окончание. Ошибка теста не останавливает остальные
тесты группы, пока хватает общего бюджета. Timeout — ошибка; оставшиеся тесты
не объявляются прошедшими. Kill/снимок процессов имеют собственные ограничители;
их завершение может немного выйти за бюджет теста/группы, но шаг ограничен 4 min.

Matrix создаёт семь отдельных jobs, `fail-fast: false`, `max-parallel: 1`.
Каждый job ограничен 10 min вместе с checkout/setup/uploads, collection —
watchdog 45 s и step 2 min, выполнение группы — step 4 min. Checkpoints до/после
pytest печатают время; после записывается job status. Bootstrap, Python probe,
план загружаются отдельными immutable artifacts ДО тестов; финальный upload
через `always()` включает hidden-файлы только из изолированного test-results.
У каждого upload лимит 1 min, никакого continue-on-error нет.
При гибели runner финальные файлы могут потеряться: `always()` не даёт гарантии
их доставки. Название и статус отдельного job останутся указателем на группу.

`windows-mock` зависит от успеха всей matrix. Только он один собирает полный
Windows/USB/update комплект с воспроизводимостью и затем проверяет извлечённый
ZIP: embedded Python, BAT, selfcheck, update/rollback, сохранение пользовательских
и RDM данных, HTTP/WebSocket mock. Эти прежние проверки сохранены.
`draft-release` явно needs и matrix, и delivered job, и прежние Linux/browser jobs.
Нет обхода стандартного success-gate через always/continue-on-error.
См. [семантику needs](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
и [fail-fast](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations#handling-failures).

Локальные проверки 2026-11-05:
- Watchdog RED blocked console → GREEN, все 4 regression прошли.
- Отдельный опыт: непрочитанные stdout/stderr, exit 124; ровно 2 МиБ сохранены,
  result.json/processes.log/cleanup.log на месте.
- Полный pytest: 1340 passed, 1 skipped, exit 0; Node exit 0.
- actionlint 1.7.12: workflow принят; временный бинарник вне проекта, checksum
  официального release проверен; зависимости проекта не менялись.
- Все семь групп прошли новым запускателем; прежние 117 IDs проверены точным
  сравнением с исходным manifest. Только новый regression добавлен, прежний skip сохранён.
- Семь тестов изолятора: точная collection; пропуск/дубль/неизвестный/переименование;
  реальные failure/timeout/success в одной группе; исчерпание общего бюджета.
- DAG: семь групп, один build job, явные needs, нет continue-on-error/обхода
  success-gate; failure/cancelled/skipped обязательного Windows job блокирует draft.

Ограничения: Windows/taskkill, embedded runtime и BAT ещё требуют реального
GitHub runner; MA2/зал не проверялись и не затрагивались. Независимого review нет;
субагенты запрещены. Счётчик квоты модели недоступен, Clodex не использовался.

Следующий шаг после отдельного разрешения на перенос изменений и запуск:
один `workflow_dispatch` workflow CI на согласованном SHA с пустым `draft_tag`.
Он проверит все группы, затем один доставляемый комплект, Linux/browser; ничего
не публикует. Push/Actions/теги/Release в этой задаче не выполнялись.
После установления и исправления причины зависания оценить возврат к одному
Windows test job: семь setup/collection/uploads и отдельные pytest — временная
цена диагностики, не постоянная схема и не основание объявлять релиз готовым.
