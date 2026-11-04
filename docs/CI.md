# Базовый CI

Workflow: [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
Запускается на push, pull request и вручную через Actions. Секреты не нужны;
`GITHUB_TOKEN` имеет только `contents: read`, credentials checkout не сохраняются.
Устаревший запуск для той же ветки/PR отменяется. Все три задания ограничены 10 минутами.

- Ubuntu: Python 3.12, `uv sync --locked`, полный pytest (таймаут 300 секунд),
  Node 24 и `node tests/panel-v4.cjs`.
- Браузеры Ubuntu: pinned dev-only Playwright, Chromium/WebKit, mock обоих портов1024×768; [повторяемый запуск и ограничения](browser-preflight.md).
- Windows: Python 3.12, тот же lockfile, `scripts/ci_smoke.py` (шаг до двух минут).
  Дополнительно собирается доставляемый ZIP и запускается его embedded Python.

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


## Поставка и ограничения (2026-11-04)

`CI` запускает Python/Node при push в main и для PR. Push в рабочую ветку
проверяется через PR, без второго запуска того же набора. Ручной запуск включает
все jobs. Windows и Chromium/WebKit выполняются для PR и вручную, не на каждый push.
Зависимости uv кешируются; устаревший запуск ветки отменяется. Артефакты — 7 дней.

Windows-2022 x64: адресные pytest release/update/browser_update/selfcheck/RDM;
`scripts/build_windows.py` собирает полный, USB и общий update ZIP.
Python 3.12.10 закреплён SHA256, Windows wheels — lockfile hashes, без сборки sdist.
ZIP имеет нормализованные порядок/время/атрибуты; равенство обещается при одинаковых
inputs и версии компрессора. `scripts/build_win.sh` вызывает тот же упаковщик.
`scripts/windows_delivered.py` распаковывает ZIP во временный путь с пробелами и
кириллицей: SHA256, native imports embedded Python, совпадение payload, реальный
install/rollback и сохранность пользовательских файлов и pending/target журнала,
BAT --help и отрицательный selfcheck exit code. HTTP/WS smoke запускается embedded
Python с --mock на двух свободных нестандартных портах. Отдельные pytest проверяют
сбои/восстановление; их интерпретатор — runner Python, не embedded Python.

UAC/firewall, ACL/locked files, физическое отключение питания и чистая VM без
предустановленного developer runtime остаются ручной приёмкой. MA2 не подключается.
DEL-004 нельзя закрывать без успешного фактического Windows run.

Ручной workflow input `draft_tag` (например, v3.1.0-test.REVISION) после успеха
всех трёх jobs создаёт только draft prerelease из проверенных Windows-артефактов.
Пустой input выполняет только проверки. Существующий tag не переиспользуется.
Публикация prerelease и stable — отдельное решение владельца; автоматической
публикации нет. Stable-updater не видит draft/prerelease. Hardware acceptance
не завершена, комплект нельзя считать готовым для концертной эксплуатации.
