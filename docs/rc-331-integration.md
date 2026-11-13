# Кандидат 3.3.1: публичная интеграция

2026-11-13. Публичная база 4cd7cd7; входящие исправления d707ba2..a3366ae.
Владелец выбрал интеграцию в ma2panel/ с сохранением публичных исправлений и тестов.
Исходная локальная история не публикуется. [Карта путей](public-rc-source-map.json)
учитывает всю входящую дельту, кроме локального TASK_STATE и пересобранного индекса.
Это трёхсторонняя интеграция, а не побайтовый снимок a3366ae.

Сохранены публичные пределы повторов чтения, missing-guards и точное распознавание
Pan/Tilt. Отменённые профили не кэшируются; фоновое чтение ждёт редактор/scene offer.
Персонализация сохраняет старую и вложенную схему, layout preferences и отменяет
жесты при обновлении видимости; устранено двойное подключение скрипта настроек.

Строгий mock дополнен точными Lua read-only шаблонами и native-командами сцен 3.3.0.
Произвольная Lua и неизвестные команды остаются ошибкой. Native playback сохраняет
Programmer; браузерный тест явно моделирует его очистку оператором на mock-пульте
перед сценами. Приложение не добавляет автоматический ClearAll.

CI проверяет SHA head PR, связывает ZIP/manifest/quality evidence с этим SHA.
Windows запускает embedded Python, настоящие start.bat и start-mock.bat, HTTP/WS,
чистый первый запуск, импорт/свет и реальную v3.3.0 upgrade/rollback/recovery.
Старый delivery workflow больше не публикует stable, permissions=contents:read.
Promote требует software/field/review/hardware receipts точного SHA/ZIP и даёт draft.

GitHub на момент подготовки: main protected=false, rulesets=[], stable-review 404.
Нужны обязательный Candidate quality gate, запрет обхода правил/force-push и reviewer
среды stable-review. Настройки не изменялись; YAML сам их не устанавливает.
Прежний независимый review a3366ae не покрывает объединённый diff: отдельный review
обязателен перед stable. Аппаратная приёмка — hall-test-plan §12–13.
Windows run и финальные артефакты пока ожидаются; точные результаты будут в PR/RC.

Публичный старый TASK_STATE удалён; персональные workstation-пути в двух прежних
отчётах обезличены. Проверка секретов очищенного индекса: gitleaks 0.

Локальная проверка интеграции: 1627 Python PASS/3 SKIP/11 subtests; Node PASS.
Последующая правка синтетической identity закреплена RED→GREEN (9 адресных PASS).
Host lifecycle с реальным v3.3.0: upgrade/rollback/interrupted recovery PASS.
Clean/V2 и field-start проверены в Chromium/WebKit; synthetic и финальные
checks точного публичного SHA остаются обязательными в CI. В плотном публичном
редакторе 52px hit-targets соседних приборов перекрываются; drag-тест использует
видимую область исходного прибора, без force и программной подмены событий.

Перед публичным коммитом: все 52 browser checks Chromium/WebKit PASS
(clean 6, real V2 4, synthetic 28, field-start 14); 67 адресных Python PASS; Node PASS.
Точная чистая SHA-проверка и Windows остаются обязательными в Actions.

Первый CI 43437709650 (3ec229b): все 7 Windows diagnostic groups и Linux
pytest/Node PASS; Windows-quality/browser/reproducibility FAIL, ZIP delivery SKIP.
Подтверждены и адресно исправлены: writable-handle fsync резервного ZIP на Windows;
showModal для inline picker; пересчёт доступности inline controls после selection ACK.
Preflight использует встроенный выбор; отрицательная RGB-проверка ждёт успешного
import completion и требует точный отказ по отсутствующему каналу. Два Windows
first-run случая ещё требуют дочернего лога; он теперь сохраняется в артефактах
и ограниченно включается в ошибку. Успех Windows по этому прогону не заявляется.

CI 43440396929 подтвердил исправление Windows fsync: остаются только два
first-run отказа bootstrap. Дочерний лог доказал, что audit hook блокировал
Windows asyncio._make_self_pipe через socket._fallback_socketpair. Исключение
ограничено точным кодом stdlib, его client/listener и собственным ephemeral port;
приложенческий loopback и MA2 по-прежнему блокируются (регрессия RED→GREEN).
Preflight обновлений теперь проверяет существующий update-check напрямую:
публичная страница настроек сохранена без новой структуры вкладок.
