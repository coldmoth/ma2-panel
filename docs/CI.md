# Базовый CI

Workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
Запускается на push, pull request и вручную через Actions. Секреты не нужны;
`GITHUB_TOKEN` имеет только `contents: read`, credentials checkout не сохраняются.
Устаревший запуск для той же ветки/PR отменяется. Все три задания ограничены 10 минутами.

- Ubuntu: Python 3.12, `uv sync --locked`, полный pytest (таймаут 300 секунд),
  Node 24 и `node tests/panel-v4.cjs`.
- Браузеры Ubuntu: pinned dev-only Playwright, Chromium/WebKit, mock обоих портов1024×768; [повторяемый запуск и ограничения](browser-preflight.md).
- Windows: Python 3.12, тот же lockfile, `scripts/ci_smoke.py` (шаг до двух минут).
  Это проверка исходников на стандартном runner, а не embeddable Python из ZIP.

Smoke копирует корневые Python-модули, `static/` и публичные шаблоны во временную
папку. Локальные config/settings, пароли, шоу и диагностика не читаются.
`ma2.export_dir` задаётся внутри временной папки; оба HTTP-порта свободные,
bind — `127.0.0.1`. Запуск всегда с `--mock`. Переменные пароля, формата mock,
Python path/оптимизации не наследуются дочерним процессом.

Проверяются HTML и MIME CSS/JS обоих интерфейсов, реальный WebSocket на обоих
портах, `mock=true`, вход mock MA2, начальный список сцен, ответ на неизвестное
действие. Затем `/api/stop` должен завершить процесс с кодом 0 и удалить PID.
При ошибке процесс принудительно останавливается, временная папка удаляется.

Локальная проверка:

```sh
uv sync --locked
uv run --no-sync python scripts/ci_smoke.py --log /tmp/ma2-ci-mock.log
```

В Actions при ошибке Python/Windows сохраняются JUnit pytest или stdout/stderr mock на три дня. Браузерный job сохраняет PNG/JSON/mock.log на три дня также при успехе. Конфиги, секреты, шоу и каталоги диагностики не загружаются.
Локальный путь `--log` выбирать вне рабочих данных; в Windows можно использовать
`--log test-results/mock.log`.

## Публичный снимок и Windows-комплект

Цель — публичный `coldmoth/ma2-panel`, ветка `main` (проверено 2026-11-02).
Исходный локальный репозиторий не имеет remote; очищенный снимок расположен
в `dist/release-repo/` и имеет собственную Git-историю. Его не обновлять push
из локальной истории разработки.

При следующем переносе в очищенный снимок включить `.github/workflows/ci.yml`,
`scripts/ci_smoke.py`, этот документ, актуальные Python-модули, `static/`,
`config.example.json`, `settings.example.json`, `pyproject.toml`, `uv.lock`
и полный согласованный набор тестов/fixtures. Тесты и инструменты переносить
парами: например, `tests/test_clodex.py` требует `scripts/clodex.py`, но не `.env`.
Перед публикацией выполнить CI-команды из корня именно очищенного снимка.
Не копировать всю рабочую папку и `.git`; этот патч ничего не публикует.

`scripts/build_win.sh` и `scripts/serve_update.sh` включают корневые `*.py`,
`static/` и выбранные документы; `.github/` и smoke в установочные ZIP не нужны.
Сборка ZIP и проверка embeddable runtime относятся к шагу 26 аудита.
Успешный smoke исходников не подтверждает ZIP, настоящий MA2 или планшеты.

Отсутствующий `ma2.export_dir` обработан в блокеВ: по умолчанию используется `importexport` рядом с config. Smoke всё равно задаёт свой временный export_dir для изоляции; он не заменяет Windows-приёмку чистой установки.
