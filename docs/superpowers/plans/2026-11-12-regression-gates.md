# Regression Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** находить поломки пользовательских сценариев до выпуска и явно показывать непроверенное.
**Architecture:** расширить текущий mock/Playwright/диагностику/обновление. Пассивные проверки отделены от команд; реальные V2 и синтетические возможности имеют разное происхождение. Gate связывает результаты с исходниками и ZIP.
**Tech Stack:** Python 3.12, stdlib, существующие FastAPI/pytest/Playwright/Node; без новых зависимостей.
**Spec:** [согласованный проект](../../testing-infrastructure-audit.md), подтверждение владельца 2026-11-12.

## Global Constraints

- Реальная MA2 и рабочее шоу не используются; только собственные mock-копии и loopback.
- Не публиковать local history, не выпускать stable и не делать merge main.
- Существующие пользовательские изменения не включать в коммиты.
- Старые пути данных сохраняются; перенос только явно, источник сохраняется.
- Нет автоматических помощников/Clodex. Независимый review остаётся отдельным обязательным этапом.

## Review Focus

- Секреты/PII в произвольных строках: только структурированный allowlist, псевдонимы, без сырых логов.
- Недостающие V3 данные: manifest неполноты, отсутствие фиктивного PASS.
- Конфликт переноса и symlink: отказ до записи; journal нельзя молча потерять.
- Подмена/отсутствие отчёта: SHA/хеш ZIP и обязательные статусы, fail closed.
- Перезапуск модели: локальное сохранение списка сцен не выдавать за сохранение look на onPC.

### 1. Исходные регрессии и стенд

- [x] Аудит, полный pytest/Node, воспроизведение browser failure.
- [x] Изолировать историю Pan от simulation; отдельный Chromium/WebKit PASS; коммит 762313b.
- [x] Разобрать оставшиеся два FixtureType failure и устаревшие browser-селекторы через существующие тесты.
- [x] Добавить `tests/data/ma2-v2/manifest.json` и `test_field_fixture_dataset.py`: hash/24 fixtures/адреса/происхождение, V3 явно отсутствует.
- [x] Подключить профиль данных к существующему runner, не копируя приватные файлы.

### 2. Пассивная готовность и безопасный тестовый архив

- [x] RED: `tests/test_quality_diagnostics.py`: неправильное шоу, offline, unknown vs unsupported, stale, hidden/blocked; archive PII/secrets и отсутствие команд; localhost/Host gate, preview/download identity.
- [x] `quality_diagnostics.py`: `readiness(cfg, settings, state, link)` и `collect(cfg, settings, state, link)`; snapshot только из памяти/allowlist.
- [x] Подключить локальные routes из `api.register`; diag UI показывает причины и preview ZIP. Ничего не отправлять на MA2.
- [x] Проверить подсистемы diagnostics/onboarding и визуальный результат.

### 3. Явный перенос данных

- [x] RED: `tests/test_data_transfer.py`: byte equality вложенных данных, конфликт, symlink, interrupted transaction, неполная копия.
- [x] `data_transfer.py`: CLI `backup SOURCE DEST` и `restore ARCHIVE DEST --confirm`; preview manifest/hashes, атомарная публикация, отсутствуют удаление источника и перезапись конфликтов.
- [x] Включить пользовательские файлы, backups и recovery-состояния по согласованной политике, задокументировать её; проверить вместе с update/migrations.

### 4. Сквозные сценарии

- [x] `scripts/regression_browser.cjs` и расширение существующего runner: UI → настоящий backend → mock state → WS → computed CSS, 22 сценария/явные blockers.
- [x] Первое включение отдельно от готовой конфигурации, restart/reload/external fault через runner, не через fake receive.
- [x] Chromium/WebKit, ноутбук/планшет, screenshot/results JSON/логи; поведение цвета должно падать при недоступном поддерживаемом приборе.

### 5. Выпуск и доставка

- [x] RED: `tests/test_quality_gates.py`: missing/skipped/failure/другой SHA/другой ZIP/блокер запрещают stable.
- [x] `scripts/quality_gate.py`: машинный отчёт и проверка одного кандидата; отдельные software и hardware/review статусы.
- [x] CI без пропуска browser/Windows на main; E2E на исходниках и доставленном ZIP; artifact identity, документация, миграции/перенос.
- [x] Существующий RC prerelease сохраняется; stable-updater отвергает RC; публикацию не выполнять.

### 6. Проверка и передача

- [x] Обновить QUALITY-GATES, SETUP/USAGE и нужный spec/history по согласованному изменению; включить документы в ZIP.
- [x] Адресные проверки; полный pytest один раз после итоговых изменений; Node и Chromium/WebKit; индекс и свой diff.
- [x] Коммитить логические части только своим diff; обновить TASK_STATE (≤40 строк).
- [x] Финал: результаты/CI/непроверенное/однократные данные V3/еженедельные 10–15 минут/review и порядок выпуска.

## Ledger

2026-11-12: проект согласован; выполнять самостоятельно. Старые модификации остаются исходной базой, без включения в новые коммиты. Текущий remote CI относится к другому SHA, его нельзя засчитать текущему дереву.

2026-11-12: реализация и локальные проверки выполнены; отдельный независимый review, Windows CI точного исходного снимка и реальные V3/аппаратные данные остаются непроведёнными внешними этапами. Публикация локальной истории запрещена; сравнение с публичным main подтвердило различия прежней базы. Подробности: docs/quality-verification-2026-11-12.md.
