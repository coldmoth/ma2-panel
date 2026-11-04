# Передача на независимый review

2026-11-04. Независимый review ещё не выполнен. Тестовый выпуск не означает
приёмку updater или готовность к концертной эксплуатации.

## Область

Локальные изменения после `f6c6772`: CI/build_windows/windows_delivered,
browser_update.py, static/update.js/settings.html и связанные тесты.
Публичный снимок имеет отдельную очищенную историю; сравнивать CI/updater commits
после `0a20a79`, без локальной истории разработки. Команды MA2 не менялись.

## Проверить

- Единственный официальный repo, TLS и allowlist redirects; SHA256 не выдаётся
  за независимую подпись. Недоверенный HTML release notes остаётся текстом.
- Numeric version selection: не предлагать ту же/старую версию или prerelease;
  версии manifest/tag согласованы; пользователь подтверждает выбранный тег,
  смена latest требует новой проверки. Нет установки по результату GET/check.
- Никаких блокирующих сетевых вызовов в event loop, ограничения времени/размера;
  нехватка места/сеть/пакет отказывают до закрытия gate/остановки моста.
- Existing gate не обходит Fade/RDM/pending/Highlight/active work. Старый
  транзакционный install, точный rollback и recovery не заменены.
- USB updater, внешний worker и embedded _pth/imports; последствия прерывания
  и доступности recovery при отсутствующих файлах. Нет повторной установки
  после потерянного ответа. Полезны отдельные Windows kill-worker/NTFS/UAC проверки.
- Данные не входят в payload; текущие настройки/секреты/шоу/планы/rdm-search.json
  не откатываются поверх текущих файлов. Backup/previous/recovery сохраняются.
- Два независимых build с pinned Python/lock, полный ZIP vs update payload,
  embedded native imports, Unicode пути, BAT/exit codes; runner pytest
  не должен выдаваться за выполнение всего набора на embedded Python.
- Workflow jobs/permissions, PR input isolation, неизменяемость существующего
  tag, draft-only публикация после трёх успешных jobs, отсутствие stable publish.

## Проверки и откат патча

RED→GREEN: tests/test_online_update.py и tests/update-ui.cjs; полный pytest,
Node suite и Chromium/WebKit --mock. Локальные логи/JUnit сохранены в /tmp,
фактические CI run URLs и результаты — в локальном TASK_STATE.md.
Windows completion подтверждается только реальным run с доставленным ZIP.

До приёмки не публиковать prerelease/stable и не обновлять рабочую установку.
Для отката исходников сделать обычный revert связанных публичных commits;
не переписывать историю. Для установки использовать существующий rollback.bat/
recovery и сохранённый предыдущий комплект, не удалять пользовательские данные
и pending/target журнал. Не повторять неизвестную физическую RDM-операцию.
