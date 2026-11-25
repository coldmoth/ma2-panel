# LUMA P0.4 — проверка адресации сцен

19.11.2026. Два независимых клиента WebSocket, временный план и Python-мост
с локальной MockMA2. В терминале протокола нет постороннего фонового опроса.

## Исходный `d2a54ac`

Клиент A сохраняет снимок с `s6 → 1.106`. Клиент B удаляет сцену из плана
и пишет Cue на 1.107, после чего `new_id` выдаёт `s6` повторно. Go из
снимка A проходит по новой записи. В этом воспроизведении Fade равен 0.8 с.

```text
A config f362ff79db6844408a96fd466b3adb9d:1 {'id': 's6', 'exec': '1.106', 'label': 'Scene 6'}
request {"a": "scene_delete", "id": "s6", "config_revision": "f362ff79db6844408a96fd466b3adb9d:1", "request_id": "B-delete", "blackout_epoch": 0}
response {"ok": true, "a": "scene_delete", "request_id": "B-delete", "outcome": "completed", "command_evidence": [], "config_revision": "f362ff79db6844408a96fd466b3adb9d:2"}
request {"a": "select_fixtures", "ids": [12], "config_revision": "f362ff79db6844408a96fd466b3adb9d:2", "request_id": "B-select", "blackout_epoch": 0}
response {"ok": true, "a": "select_fixtures", "request_id": "B-select", "outcome": "completed", "command_evidence": []}
request {"a": "scene_create", "label": "Replacement", "page": 1, "exec": "1.107", "confirm": "1.107", "config_revision": "f362ff79db6844408a96fd466b3adb9d:2", "request_id": "B-create", "blackout_epoch": 0}
response {"ok": true, "a": "scene_create", "request_id": "B-create", "outcome": "completed", "command_evidence": ["sent", "sent", "sent", "sent"], "config_revision": "f362ff79db6844408a96fd466b3adb9d:3"}
B config f362ff79db6844408a96fd466b3adb9d:3 {'id': 's6', 'exec': '1.107', 'label': 'Replacement', 'named': True, 'fixtures': [12]}
request {"a": "scene_go", "id": "s6", "config_revision": "f362ff79db6844408a96fd466b3adb9d:1", "request_id": "A-stale", "blackout_epoch": 0}
response {"ok": true, "a": "scene_go", "request_id": "A-stale", "outcome": "completed", "command_evidence": ["sent"]}
mock ["ListVar", "List Executor 1.107", "Lua \"local c=gma.show.getobj.handle('Executor 1.107 Cue 1'); local p=c and gma.show.getobj.parent(c); local n=p and gma.show.getobj.amount(p); local q=c and gma.show.getobj.child(c,0); local cmd; if q then for i=0,gma.show.property.amount(q)-1 do if gma.show.property.name(q,i)=='CMD' then cmd=gma.show.property.get(q,i) end end end; local ok=n and n>=1 and n<=2 and gma.show.property.get(c,'trig')=='Go' and gma.show.getobj.amount(c)==1 and cmd==''; local seen=0; if ok then for i=0,n-1 do local h=gma.show.getobj.child(p,i); local k=h and tonumber(gma.show.getobj.number(h)); if not h then if i~=0 then ok=false end elseif h==c and k==1 then seen=seen+1 elseif k~=0 then ok=false end end end; ok=ok and seen==1; gma.show.setvar('PANELSCENE','e196d7c4a7407aae '..(ok and 'manual' or 'unknown'))\"", "ListVar", "Goto Cue 1 Executor 1.107 Fade 0"]
```

## После исправления

Тот же сценарий с Fade 1.5 с. После записи новой сцены команда со старой
ревизией получает `scene_context_changed`. Подстановка свежей ревизии с
прежним ID и UUID получает `scene_target_changed`. В обоих случаях mock
не получил ни строки. Новая явная цель проходит проверку, запись локальной
группы делает снимок устаревшим, свежий Off сохраняет штатный Fade.

```text
request {"request_id": "p04-1", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:1", "blackout_epoch": 0, "a": "scene_delete", "id": "s6"}
response {"ok": true, "a": "scene_delete", "request_id": "p04-1", "outcome": "completed", "command_evidence": [], "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:2"}
request {"request_id": "p04-2", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:2", "blackout_epoch": 0, "a": "select_fixtures", "ids": [12]}
response {"ok": true, "a": "select_fixtures", "request_id": "p04-2", "outcome": "completed", "command_evidence": []}
request {"request_id": "p04-3", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:2", "blackout_epoch": 0, "a": "scene_create", "exec": "1.107", "confirm": "1.107", "page": 1, "label": "Replacement"}
response {"ok": true, "a": "scene_create", "request_id": "p04-3", "outcome": "completed", "command_evidence": ["sent", "sent", "sent", "sent"], "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3"}
request {"request_id": "p04-1", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:1", "blackout_epoch": 0, "a": "scene_go", "id": "s6", "scene_identity": "6cecbc484a5f4a88b1436f04f9b0935d"}
response {"ok": false, "a": "scene_go", "err": "контекст сцен изменился; проверьте сцену и нажмите снова", "code": "scene_context_changed", "params": {}, "request_id": "p04-1", "outcome": "failed", "command_evidence": []}
mock []
request {"request_id": "p04-2", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3", "blackout_epoch": 0, "a": "scene_go", "id": "s6", "scene_identity": "6cecbc484a5f4a88b1436f04f9b0935d"}
response {"ok": false, "a": "scene_go", "err": "сцена удалена или заменена; выберите сцену заново", "code": "scene_target_changed", "params": {}, "request_id": "p04-2", "outcome": "failed", "command_evidence": []}
mock []
request {"request_id": "p04-3", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:1", "blackout_epoch": 0, "a": "scene_off", "id": "s6", "scene_identity": "6cecbc484a5f4a88b1436f04f9b0935d"}
response {"ok": false, "a": "scene_off", "err": "контекст сцен изменился; проверьте сцену и нажмите снова", "code": "scene_context_changed", "params": {}, "request_id": "p04-3", "outcome": "failed", "command_evidence": []}
mock []
request {"request_id": "p04-4", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3", "blackout_epoch": 0, "a": "scene_off", "id": "s6", "scene_identity": "6cecbc484a5f4a88b1436f04f9b0935d"}
response {"ok": false, "a": "scene_off", "err": "сцена удалена или заменена; выберите сцену заново", "code": "scene_target_changed", "params": {}, "request_id": "p04-4", "outcome": "failed", "command_evidence": []}
mock []
request {"request_id": "p04-5", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3", "blackout_epoch": 0, "a": "scene_go", "id": "s-80d26694cb5743cda538945e1d329324", "scene_identity": "80d26694cb5743cda538945e1d329324"}
response {"ok": true, "a": "scene_go", "request_id": "p04-5", "outcome": "completed", "command_evidence": ["sent"]}
mock ["ListVar", "List Executor 1.107", "Lua \"local c=gma.show.getobj.handle('Executor 1.107 Cue 1'); local p=c and gma.show.getobj.parent(c); local n=p and gma.show.getobj.amount(p); local q=c and gma.show.getobj.child(c,0); local cmd; if q then for i=0,gma.show.property.amount(q)-1 do if gma.show.property.name(q,i)=='CMD' then cmd=gma.show.property.get(q,i) end end end; local ok=n and n>=1 and n<=2 and gma.show.property.get(c,'trig')=='Go' and gma.show.getobj.amount(c)==1 and cmd==''; local seen=0; if ok then for i=0,n-1 do local h=gma.show.getobj.child(p,i); local k=h and tonumber(gma.show.getobj.number(h)); if not h then if i~=0 then ok=false end elseif h==c and k==1 then seen=seen+1 elseif k~=0 then ok=false end end end; ok=ok and seen==1; gma.show.setvar('PANELSCENE','e9728d4c50beaea7 '..(ok and 'manual' or 'unknown'))\"", "ListVar", "Goto Cue 1 Executor 1.107 Fade 1.5"]
request {"request_id": "p04-4", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3", "blackout_epoch": 0, "a": "group_save", "label": "Local", "ids": [12]}
response {"ok": true, "a": "group_save", "request_id": "p04-4", "outcome": "completed", "command_evidence": [], "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:4"}
request {"request_id": "p04-6", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:3", "blackout_epoch": 0, "a": "scene_off", "id": "s-80d26694cb5743cda538945e1d329324", "scene_identity": "80d26694cb5743cda538945e1d329324"}
response {"ok": false, "a": "scene_off", "err": "контекст сцен изменился; проверьте сцену и нажмите снова", "code": "scene_context_changed", "params": {}, "request_id": "p04-6", "outcome": "failed", "command_evidence": []}
mock []
request {"request_id": "p04-7", "config_revision": "645eec72f5a54d7691f545d8c48cbec1:0:4", "blackout_epoch": 0, "a": "scene_off", "id": "s-80d26694cb5743cda538945e1d329324", "scene_identity": "80d26694cb5743cda538945e1d329324"}
response {"ok": true, "a": "scene_off", "request_id": "p04-7", "outcome": "completed", "command_evidence": ["sent", "sent"]}
mock ['ListVar', 'Masterfade 1.5 Executor 1.107', 'Off Executor 1.107']
```

Воспроизведение защиты и запись трассы:

```sh
uv run pytest -qs -o addopts='' tests/test_scene_identity.py
```

Браузерная регрессия `luma-lab/tests/scene-identity.mjs` проверяет старое
назначение по строковому ID, сохранение валидной привязки после правки
группы, отказ после удаления и ровно один кадр Go после переназначения.

## Восстановление после неопределённой перезаписи

В журнале `scene-write-<executor>.json` записаны шоу, цель и резерв.
Для перезаписи `preparing` означает подготовку резерва. Последний `ListVar`
и проверки допуска транспорта проходят до `committing`. Если транспорт
ещё не допустил Overwrite, мост снимает временную запись и оставляет резерв
на пульте. При перезапуске запись `preparing` перезаписи допускает новую
попытку с повторной проверкой свободного резерва. Запись новой сцены на
пустой Executor использует отдельный прежний сценарий.

`committing` означает, что целевая Cue могла измениться. Мост сохраняет
это состояние в `scene-generation-<ключ шоу>-<executor>.json` до отправки
Overwrite. После подтверждённой штатной записи там остаётся текущее поколение
Cue. При неопределённом результате Go и Off блокируются, даже если убрать
`write_error` или архивировать журнал записи. Мост и CLI проверяют активный
файл, все файлы с префиксом `scene-write-<executor>.json.` и запись поколения.
`preparing` не снимает запрет, заданный другим журналом в `committing` или
`completed`. Ошибка чтения или конфликт шоу, Executor или поколения закрывает
допуск. Успешный `List Executor` подтверждает наличие Executor. Содержимое Cue
для восстановления проверяет ответственный оператор.

1. Остановить мост и исключить изменения целевого Executor на пульте на время
   сверки. Сделать копии рабочего плана, сохранённых планов, журнала и файла
   поколения, если он есть. Сверить точное имя шоу и адрес цели по записи.
2. На MA2 сопоставить Cue 1 цели с подготовленной Cue 1 резерва и с прежней
   Cue 2 резерва. Проверить фактические данные Cue и параметры воспроизведения.
   Если нужную Cue пришлось восстановить на пульте, проверить её повторно.
   При невозможности достоверной сверки оставить мосту блокировку и передать
   ответственному оператору имя шоу, адреса цели и резерва и файлы из шага 1.
3. После сверки запустить из каталога панели команду восстановления. Указать
   имя Executor и приборы проверенной Cue. Пустой `--fixtures` удаляет
   неизвестный список приборов из метаданных плана.

   ```sh
   uv run python -m ma2panel.scene_recovery \
     --config /path/to/config.json --show "Точное имя шоу" \
     --executor 1.101 --label "Проверенное имя" --fixtures 12 13 --verified-on-ma2
   ```

   С установленным Python также можно вызвать `python -m ma2panel.scene_recovery`.
   Флаг `--verified-on-ma2` фиксирует подтверждение оператора. Команда работает
   с локальными файлами и не подключается к MA2. Она сохраняет ID, место сцены
   и остальные строки рабочего плана, выдаёт новый UUID и открывает поколение
   только после сохранения плана. Подтверждённая запись поколения содержит
   отпечатки содержимого проверенных архивов. Новые операции помечаются
   отдельным идентификатором. Если найден дополнительный или изменённый
   архив, Go и Off снова блокируются до сверки. Подтверждение прежнего формата
   без отпечатков требует повторной сверки, если архив по-прежнему присутствует.
   Если записи указывают разные резервы, восстановление не связывает сцену
   автоматически ни с одним из них.
   Самостоятельно редактировать `identity`, `write_error`, журналы или файл
   поколения для разблокировки не требуется. При прерывании процесса между
   шагами сохраняется блокировка. Повторить команду можно после повторной
   сверки Cue, если восстановление ещё не завершено.

4. Запустить мост и обновить вкладки. Новый процесс выдаст новую ревизию
   плана. Действительные привязки к другим сценам сохраняются. Для восстановленной
   сцены клавишу нужно назначить заново. Хранить файл поколения вместе с
   рабочим каталогом. Сохранённые планы остаются на месте. Их строки со старым
   поколением этой Cue остаются заблокированы при открытии. Чтобы сохранить
   восстановленную строку в актуальной копии плана, пользоваться штатным
   сохранением плана после восстановления.

Если исторический журнал лежит под именем вне префикса
`scene-write-<executor>.json.` или был удалён, вернуть его проверенную копию
в этот каталог под именем с указанным префиксом до запуска моста. По одному
виду Executor или по старому плану определить, была ли перезаписана Cue,
невозможно.

## Обесточивание во время записи

Перед допуском Overwrite мост последовательно сохраняет поколение
`committing`, активный журнал `committing` и рабочий план с `write_error`;
ошибка любого сохранения прерывает отправку Overwrite. Минимальное условие
безопасности после обесточивания — до отправки на диске должна быть
восстанавливаемая запись `committing` с шоу, Executor, прежним UUID и
адресом резерва. При штатном завершении и при восстановлении новая версия
плана должна быть долговечной до публикации `verified`. Блокировка должна
пережить удаление активного журнала, пока новое поколение не зафиксировано.

Сейчас `save_config` закрывает временный файл и вызывает `os.replace` без
синхронизации содержимого и каталога. После потери питания запись
`committing` может исчезнуть или откатиться к `preparing`, а рабочий план
может вернуться к старому UUID, хотя пульт уже выполнил Overwrite. В таком
случае у моста может не остаться свидетельства для блокировки. Для
поддерживаемых файловых систем нужен отдельный протокол синхронизации
содержимого и метаданных, включая публикацию поколения и удаление журнала.
Для Windows нужен отдельный проверенный путь записи с соответствующими
гарантиями Win32. В этом патче порядок записи проверен инъекцией ошибок
сохранения. Физический допуск остаётся заблокирован до реализации
долговечной записи и испытания на реальном отключении питания.
[Документация Win32 по MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw).

## Переход с пропущенным Off

Ответ на Go может содержать
`skipped_off: [{"executor":"1.101","reason":"scene_identity_changed"}]`.
`outcome: completed` сохраняется для совместимости и отражает обработанные
команды. При пропущенном Off LUMA на EN/RU предупреждает, что предыдущая
сцена могла остаться активной, и показывает адрес Executor. Мост не посылает
компенсирующий Off.
