# CI и тестовая поставка

Обновлено 2026-11-04. `.github/workflows/ci.yml` — единственная система CI/подготовки draft.

- Push в `main` и PR: полный pytest, импорты runtime, Node DOM/regression suite.
- PR и ручной запуск: Windows x64 delivery и Chromium/WebKit, оба интерфейса,
  мастер подключения, release notes и отсутствие нового stable-релиза, только mock.
- Рабочие ветки проверяются через PR, без второго push-запуска того же набора.
- uv cache, concurrency с отменой устаревших запусков, timeouts 5–20 минут,
  диагностические артефакты и ZIP — 7 дней, обычный GITHUB_TOKEN — contents:read.
- `draft-release` имеет contents:write/actions:read только в ручном запуске с
  непустым draft_tag и зависит от успеха всех трёх проверок. Публикации stable нет.

Правила событий/permissions: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Windows

Windows-2022 x64 сначала выполняет адресные pytest release/update/browser_update/
selfcheck/RDM. Это runner Python. Затем `scripts/build_windows.py --verify-reproducible`
собирает полный, USB и общий update ZIP дважды: в dist и независимом временном каталоге.
Сравниваются все три ZIP побайтно. Python 3.12.10 закреплён SHA256, Windows wheels —
lockfile hashes, sdist запрещён. ZIP нормализует порядок/время/атрибуты. Равенство
обещается при одинаковых inputs и версии компрессора, не между разными toolchains.
`build-inputs.json` фиксирует полный commit, runtime/lock, embedded Python hash, uv,
Python и zlib. `scripts/build_win.sh` вызывает тот же упаковщик.

`scripts/windows_delivered.py` распаковывает именно ZIP во временный путь с пробелами
и кириллицей: SHA256, native imports embedded Python, соответствие payload общему
update ZIP, install/rollback и сохранность пользовательских файлов и pending/target
журнала, BAT --help и отрицательный selfcheck exit code. Отдельный HTTP/WS smoke
запускает embedded Python с --mock на двух свободных нестандартных портах.
Положительный selfcheck и исключения update/recovery также проверяются адресным
pytest; его интерпретатор — runner Python, не embedded Python.

UAC/firewall, ACL/locked files, физическое отключение питания и чистая VM без
developer runtime остаются ручной приёмкой. MA2 не подключается. DEL-004 нельзя
закрывать без успешного фактического Windows run; зелёный исходный mock его не заменяет.

## Локально и публикация

```sh
uv sync --locked
uv run pytest -q -p no:cacheprovider
node tests/panel-v4.cjs
uv run python scripts/ci_smoke.py --log /tmp/ma2-ci-mock.log
uv run python scripts/build_windows.py --verify-reproducible
# Только Windows:
uv run python scripts/windows_delivered.py
uv run python scripts/ci_smoke.py --bundle dist/ma2-panel-win/ma2-panel/program
```

Smoke никогда не читает локальные настройки/шоу/секреты. Он использует отдельную
временную установку, шаблоны, loopback, свободные порты, --mock, собственный export_dir
и завершает свой процесс. Пароль и PYTHONPATH не наследуются.

Публичный `coldmoth/ma2-panel/main` имеет собственную очищенную историю в
`dist/release-repo/`. Исходная локальная история не публикуется. Переносить только
проверенные публичные файлы, связанные тесты/fixtures и инструменты, не рабочую папку.
Проверять документационные зависимости упаковщика и выполнять проверки в снимке.

Онлайн-путь, доверие, recovery и тестовый выпуск: [online-updates.md](online-updates.md).
Текущая аппаратная приёмка не завершена; draft/prerelease не доступны stable-updater.
