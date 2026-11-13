# Отдельный review инфраструктуры регрессий

Review **не проведён**. Помощники и платные вызовы не запускались.
Цель — независимая оценка диагностического архива, переноса данных и критериев
выпуска до использования stable. Коммиты этой задачи начинаются после `d707ba2`;
ветка `codex/regression-quality-gates`. Итоговые SHA — в TASK_STATE/Git.

Важно: в исходной ветке уже было большое незакоммиченное дерево. Оно сохранено.
В новых коммитах только наша дельта; интеграционные проверки запускались на
**полном текущем рабочем дереве**, а не на изолированном checkout этих коммитов.
Для файлов со смешанными изменениями staged был только собственный diff;
для пересекающихся блоков — эквивалентное изменение поверх HEAD, без присвоения
прежнего незакоммиченного UI/модели mock. Не публиковать локальную историю.

## Что проверить

1. `quality_diagnostics.py`, регистрация в `api.py`, `static/quality-diagnostics.js`:
   отсутствие команд MA2, контекст lifecycle/cancellation, согласованный снимок
   без гонки с WS, localhost/Host gate, лимиты/cached ZIP identity и TTL,
   закрытый словарь данных/PII, маркировка mock/unknown, fidelity преобразованных XML.
2. `data_transfer.py`: приватные ACL и права, отсутствие удаления источника,
   проверка всего архива до публикации, хеши, Unicode/case/путь/коллизии,
   symlink/junction, Windows lock/rename, rollback при ошибке и явная маркировка
   частичного назначения при аварийном завершении. Не обещать автоматического
   восстановления незавершённого restore; повтор — в новую пустую установку.
3. `scripts/quality_gate.py`, CI и promote: обязательные jobs без skip на main,
   чистый SHA без скрытых untracked source, проверенные ZIP/build-inputs,
   отсутствие пересборки при promotion, отдельные receipts review/hardware/V3,
   RC не виден stable-updater. Требуются настройки GitHub branch protection и
   reviewers окружения stable-review; YAML их сам не устанавливает.
4. Browser suite: реальные controls/backend/transport/output; hooks только
   в изолированной временной копии с --mock, token и network guard;
   собственные PID останавливаются, состояние движков изолировано;
   утверждения о физическом свете или сохранении mock look после рестарта отсутствуют.
5. Сохранены исходные MA2 safety/action_lock/throttle, Show/Cue/Programmer;
   изменение production UI ограничено отсутствием плана в «Сценах».

## Воспроизведение

Из корня рабочей копии, без настоящей MA2:

```sh
uv run pytest -q -p no:cacheprovider tests/test_quality_diagnostics.py tests/test_data_transfer.py tests/test_quality_gates.py tests/test_quality_lifecycle.py tests/test_quality_delivery.py tests/test_field_fixture_dataset.py
node tests/panel-v4.cjs
uv run python scripts/browser_smoke.py --output /tmp/ma2-review-smoke
uv run python scripts/run_quality_browser.py --output /tmp/ma2-review-scenarios
```

Полный pytest, отчёты и пределы доказательств —
[результаты](quality-verification-2026-11-12.md).
Windows x64/delivered ZIP должен выполнить CI после безопасной интеграции базы.
Собственный общий patch: `/tmp/ma2-quality-own-review.patch` (после финального коммита).
Исходные версии смешанных файлов: `/tmp/ma2-quality-own-base/`;
собственные hunk-пакеты: `/tmp/ma2-quality-own-patches/`.
Все эти временные пути локальны; для передачи использовать проверенную дельту,
не рабочие config/settings/secret.env/field-data.
