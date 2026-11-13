# Исправления независимого аудита — 2026-11-13

Исходник: `ba900da`, ветка `codex/regression-quality-gates`.
Исправления: отдельный worktree `codex/quality-audit-fixes`; исходное смешанное
дерево не менялось и в эти коммиты не включалось. Публикации/merge/release нет.

## Что исправлено

1. Стенд больше не зависит от прежних локальных правок: отдельно зафиксированы
   методы/канал simulation и отображение этой явно обозначенной модели. Проверка
   `scripts/check_reproducible.py --sha FULL_SHA --output DIR` создаёт новый чистый
   checkout, устанавливает зависимости из lockfiles в минимальном окружении,
   выполняет Chromium/WebKit и отрицательный тест импорта. Отдельный CI job
   `Clean commit reproducibility` обязателен для Candidate quality gate.
2. Stable-updater требует `stable-quality.json`: полный source SHA, SHA256 ZIP,
   все software checks (включая reproducible), приёмки площадки/review/hardware,
   tag, promotion run/attempt. Канонический хеш свидетельства сверяется через
   публичный GitHub Checks API с check `Stable quality evidence` от github-actions
   и успешным точным run `.github/workflows/promote.yml`. Tag разрешается в тот же
   SHA. Свидетельство проверяется до предложения, перед подготовкой и в worker
   перед install; ZIP хеш и `source_identity.py` должны совпасть. Обычный checksum
   не является таким свидетельством. Нет GitHub/свидетельства — нет предложения.
   Формат manifest schema 1 сохранён: v3.3.0 может установить следующий пакет;
   старый установленный updater ретроактивно изменить невозможно. Локальные
   USB/LAN-инструменты и rollback остаются явными административными операциями.
3. MA2-группы изначально есть только на тестовой консоли. Браузер читает,
   нажимает «Добавить отмеченное», проверяет `[1,2]` / `[55,56]`, выбирает группу,
   проверяет selection/output всех её приборов и неизменность прочих. Затем
   проверяется сохранение ma2groups при перезапуске процесса. Mutation отключает
   именно UI ma2_import во временной копии и обязана сломать этот сценарий.
4. Обезличивание сохраняет нумерованные Shutter/Strobe/Zoom/Focus, модели цвета,
   ChannelFunction/ChannelSet ranges, технические params и strobe map. Личные
   подписи удаляются; parse_fixture_type до/после сравнивается численно.
5. `first_run_zip.py` отдельно распаковывает настоящий Windows ZIP для pristine,
   missing/broken config и missing/broken settings. До запуска pristine файлы
   поставки не заменяются. Запускается обычный bridge без --mock; audit hook
   запрещает каждый outbound connect до сетевого вызова ОС, включая onPC на
   loopback:30000. Проверяются режим test, startup, принадлежность PID порта,
   wizard settings API и отсутствие управления MA2. Занятый порт — отказ gate.
   Обычный ci_smoke --mock сохранён. Это не UI E2E мастера: его отдельно покрывает
   clean browser profile. Локальные pytest допускают skip при занятых 8080/8090;
   отдельный Windows ZIP gate skip не допускает.
6. `release_lifecycle.py` использует неизменённый настоящий ZIP v3.3.0
   (`b4d2ce6414e65f7654875af988e846b4883f4d798b5f4831aa9a757065196280`).
   Старый updater устанавливает другой код; проверяются запуск обоих HTTP-портов,
   идентичность PID/версии, сохранность данных, rollback и os._exit во время
   удаления реального файла программы с последующим штатным recovery и запуском.
   Windows job использует доставленный python/lib; локальный запуск — host Python.
   Выявленные зависимости: разрешён старый пакетный каталог ma2panel для точного
   отката; runtime identity совместима с поставленной v3.3.0 только для закреплённого
   графа зависимостей (включая hashes), независимо от версии самого проекта.
   Любое другое изменение графа требует другого runtime. Сверены исходный lock
   публичного SHA и реальные dist-info pinned Windows ZIP
   `0dc535cb5143f5acb368ebc8a5a13cd8fceef9eef737d5616a6acb0f07163cbb`.
7. `mock_console.py` — независимые атрибуты, диапазоны, возможности 60 приборов,
   составы групп и whitelist команд для строгого quality-стенда. Они не берутся
   из attrs приложения. QA_NOT_A_MA2_RED/GREEN/BLUE, неизвестная команда,
   недопустимый Pan и Focus на dimmer отклоняются. Цвет проверяется числами;
   simulation не становится измеренным MA2 readback. Это не полный эмулятор MA2.
8. Reconnect сравнивает весь поток с закрытым whitelist чтения. Транспортные тесты
   покрывают Goto Cue, Off Executor, ClearAll, Fixture At, Master At, StoreLook, Go:
   разрыв до отправки, после применения до ответа и внутри составного scene_go.
   Unknown не становится completed; команда не повторяется.

## Данные площадки

По подтверждению владельца `big room v2` функционально эквивалентен V3.
Отдельный экспорт только ради имени не нужен. Реальный V2-профиль содержит
24 Fixture/Patch, но не полный набор FixtureType и не подтверждённые составы
всех групп. Их полнота остаётся unknown, синтетика это ограничение не закрывает.
Исторический ключ receipt `field_v3: confirmed` означает подтверждение фактических
данных площадки; допускается эквивалентный V2. Это не требование переименовать шоу.

## GitHub: проверенные факты и действия владельца

API 2026-11-13: main protection — HTTP 404 `Branch not protected`, rulesets — `[]`,
environments — `total_count: 0`. Защита **не включена**. Для текущего нового SHA
Windows CI не запускался; локальная история не публикуется. Сначала требуется
безопасная интеграция в очищенный public repo `dist/release-repo/` с сохранением
существующей публичной структуры, затем CI именно этого публичного SHA.

Владелец на GitHub Settings → Branches/Rulesets для `main` должен включить:

- Require a pull request; минимум один approving review; dismiss stale approvals;
- Require status checks: **Candidate quality gate**, приложение GitHub Actions;
  strict/up-to-date branch; без разрешённых обходов и с enforce administrators;
- запрет force-push и удаления main; ограничение прямого push;
- Settings → Environments → **stable-review**: required reviewers, prevent
  self-review, запрет bypass администраторами; deployment только protected main.
  Если тариф не поддерживает reviewer protection — stable не разрешать, пока
  эквивалентное ограничение не будет обеспечено.

После настройки проверить API, а не только наличие YAML:

```sh
gh api repos/coldmoth/ma2-panel/branches/main/protection
gh api repos/coldmoth/ma2-panel/rulesets
gh api repos/coldmoth/ma2-panel/environments/stable-review
```

Свидетельство опирается на HTTPS, права репозитория и доверенный GitHub Actions
app. Оно предотвращает публикацию ZIP без соответствующего check, но не может
защитить от владельца, который изменяет сам доверенный workflow/программу.
[Поля Checks API](https://docs.github.com/en/rest/checks/runs) используются без
добавления криптографической библиотеки или нового локального signing secret.

## Проверка и независимый review

Полные результаты и точный SHA сохраняются в локальных артефактах, перечисленных
в TASK_STATE и ответе. Промежуточные результаты не подменяют финальную проверку
чистого checkout. Полный pytest запускается один раз после правок; Windows/BAT
не выдаются за локальный PASS macOS. Квота подписки недоступна через инструменты;
проценты экономии не вычислялись. Помощники и Clodex не использовались.

Патч требует отдельного независимого review перед stable: доверие к GitHub check,
проверки worker до install, runtime compatibility alias, разрешение legacy
ma2panel в snapshot/rollback, network guards/PID и Windows lifecycle. Текущая
самопроверка не является независимым review. Для площадки остаётся приёмка
[hall-test-plan §12–13](hall-test-plan.md); настоящий пульт/шоу не использовались.

Локальные результаты 2026-11-13: полный pytest — 1435 PASS, 3 SKIP, 8 FAIL
только в fixture фиксированного списка документов; после её обновления
`test_release.py` — 28 PASS/1 SKIP. Дополнительная ошибка Group в oracle
воспроизведена отдельным тестом; после исправления 18 адресных проверок PASS.
Полный pytest после этого не повторялся. Node PASS. Сводный browser — 38 PASS
(clean 6, V2 4, synthetic 28 в Chromium/WebKit), отрицательный ma2_import
выявляет поломку. YAML обоих workflows разобран; CLI stable evidence проверен
на совпадение хеша check/proof и отказ при failed Windows gate.

Артефакты: `/tmp/ma2-audit-final-pytest.{log,xml}`,
`/tmp/ma2-audit-release-recheck.{log,xml}`, `/tmp/ma2-audit-final-node.log`,
`/tmp/ma2-audit-final-browser-summary.json`, `/tmp/ma2-audit-lifecycle3/result.json`.
После фиксации чистого SHA его окончательные результаты записывает
`/tmp/ma2-audit-clean/reproducibility.json` (все браузеры, отрицательный импорт,
новый ZIP и настоящий межверсионный lifecycle). Этот файл содержит проверенный
SHA и SHA256 кандидата; промежуточный dirty ZIP не является release evidence.
