# MA2 3.9: доказательства команд и границы приёмки

Проверено по официальному руководству MA Lighting 2026-11-10.
Разделы этапов 1–2 ниже — историческое документальное обоснование.
Фактическая проверка onPC этапа 4 приведена отдельно в конце документа.
Общие правила синтаксиса применяются к составным адресам объектов; строки,
которых нет в руководстве буквально, ниже явно отделены от прямых примеров.

| Команда/механизм | Официальный источник и подтверждённое поведение |
|---|---|
| `Goto Cue 1 Executor P.E Fade T` | [Playing back Cues](https://help.malighting.com/grandMA2/en/help/key_cs_playback.html): дан прямой пример Goto с Cue, Executor и Fade. Время команды заменяет Cue и индивидуальные времена. Используется также при T=0. |
| `Go Executor` | [Go](https://help.malighting.com/grandMA2/en/help/key_keyword_go.html): выполняет следующий шаг. Поэтому для запуска конкретной сцены исключён. |
| `Fade` | [Fade](https://help.malighting.com/grandMA2/en/help/key_keyword_fade.html): задаёт время функции playback либо время сохраняемого объекта. Сам по себе не устанавливает время снятия другого Executor. |
| `OutFade` | [OutFade](https://help.malighting.com/grandMA2/en/help/key_keyword_outfade.html): время уменьшения dimmer внутри Cue. Это не замена Off Time другого playback. |
| `Masterfade T Executor P.E` | [MasterFade](https://help.malighting.com/grandMA2/en/help/key_keyword_masterfade.html): для Sequence Executor задаёт Off fade; руководство содержит прямой пример. |
| `Off Executor P.E` | [Off](https://help.malighting.com/grandMA2/en/help/key_keyword_off.html), [Executors](https://help.malighting.com/grandMA2/en/help/key_exec_what_are.html): Off останавливает Executor; Off Time плавно снимает dimmer, удерживая остальные атрибуты до конца. В коде отправляется сразу после Goto, без sleep. |
| Executor и приоритеты | [Playback](https://help.malighting.com/grandMA2/en/help/key_cs_playback.html), [Executor options](https://help.malighting.com/grandMA2/en/help/key_adv_exec_options.html): HTP выбирает максимальный dimmer, остальные атрибуты LTP; normal LTP отдаёт приоритет новому значению. Soft LTP нужен для плавной передачи интенсивности. Super выше Programmer; панель его не включает. |
| Ручная Cue | [Playback / Trigger](https://help.malighting.com/grandMA2/en/help/key_cs_playback.html): Go — ручной триггер; Time/Follow/Sound/BPM/Timecode имеют другую семантику. Панель допускает только одиночную Cue 1 с Go; неизвестная топология блокирует запуск. |
| `Blackout On/Off` | [Blackout](https://help.malighting.com/grandMA2/en/help/key_keyword_blackout.html): подавляет dimmer; React to Master=Off исключается. Голый Blackout переключает состояние. Не применён: снять чужую исходную B.O.-маску без достоверного чтения нельзя. |
| `Master` и `SpecialMaster 2.1` | [Master](https://help.malighting.com/grandMA2/en/help/key_keyword_master.html) описывает функцию интенсивности Executor. [Grand Masters](https://help.malighting.com/grandMA2/en/help/key_adv_exec_spec_master_grand.html) определяет SpecialMaster 2.1 как Grand. [Example macros](https://help.malighting.com/grandMA2/en/help/key_macro_examples.html) содержит установку Grand через At. Для нового затемнения используется `SpecialMaster 2.1 At V`, с сохранением V. Старый настраиваемый `master.cmd` не является основанием для этого выбора. |
| `Fixture N + M` | [Fixture](https://help.malighting.com/grandMA2/en/help/key_keyword_fixture.html): явный выбор приборов. Запись ограничена выбранными в панели приборами; Programmer не очищается. |
| `Store Executor P.E Cue 1 /Source=Output /Use=Allforselected` | [Store](https://help.malighting.com/grandMA2/en/help/key_keyword_store.html), [Store options](https://help.malighting.com/grandMA2/en/help/key_cs_store_options_default.html), [Storing cues](https://help.malighting.com/grandMA2/en/help/key_cs_store.html): адрес Cue/Executor, источник Output и Allforselected документированы отдельно. Составная строка следует этой грамматике. Сохраняются все атрибуты выбранных приборов, включая неактивные в Programmer; выход может зависеть от мастеров/профилей. |
| `StoreLook` (исключён из нового пути) | [StoreLook](https://help.malighting.com/grandMA2/en/help/key_keyword_storelook.html): сохраняет dimmer всех приборов и остальные параметры светящихся. Поэтому захватывал посторонний свет. Legacy `store_scene` остаётся отключённым. |
| `Assign Cue 1 Executor P.E /Trig=Go` | [Assign](https://help.malighting.com/grandMA2/en/help/key_keyword_assign.html) документирует `/property=value`; [Playback](https://help.malighting.com/grandMA2/en/help/key_cs_playback.html) — поле Trig и Go. Составная форма выведена из этих правил; после команды мост отдельно читает триггер, неизвестное значение не считается успехом. |
| `Copy Cue 1 Executor A At Cue 2 Executor B`; обратное копирование Cue 1 с `/Overwrite` | [Copy](https://help.malighting.com/grandMA2/en/help/key_keyword_copy.html) подтверждает копирование объектов и явный Overwrite; [Cue](https://help.malighting.com/grandMA2/en/help/key_keyword_cue.html) — объект Cue. Составные адреса следуют объектной грамматике; реальное копирование Cue между Executor требует приёмки. Guard разрешает только ограниченные формы Copy Cue, не произвольный Overwrite. |
| `Label Executor`, `List Executor`, `ListVar` | [Label](https://help.malighting.com/grandMA2/en/help/key_keyword_label.html), [List](https://help.malighting.com/grandMA2/en/help/key_keyword_list.html), [ListVar](https://help.malighting.com/grandMA2/en/help/key_keyword_listvar.html). Формат SHOWFILE ранее записан с 3.9.60; List подтверждает наличие объекта, но не совпадение содержимого Cue. |
| `Lua` и чтение свойств | [Lua](https://help.malighting.com/grandMA2/en/help/key_keyword_lua.html), [ListPluginLibrary](https://help.malighting.com/grandMA2/en/help/key_keyword_listpluginlibrary.html), [Plugins](https://help.malighting.com/grandMA2/en/help/key_plugins.html). Lua как команда документирована, полный контракт адресов/свойств встроенной библиотеки здесь не подтверждён. `getobj.handle/parent/amount/child/number`, `property.get(...,'trig'/'priority'/'softltp'/'cmd'/'value')` — **runtime-предпосылки**: nil, неожиданный тип, нечисловой уровень, отсутствие явного знака %, либо неверный nonce запрещают действие. Mock не доказывает эти свойства на MA2. |

## Условия и ограничения

- Модель перехода — отдельные одиночные Sequence Executor панели, normal LTP
  и Soft LTP. Настройки приоритета существующего шоу автоматически не меняются; не подтверждённые LTP/Soft LTP и непустой Cmd блокируют запуск.
  HTP/High/Super, Snap, effects, чужой Programmer, shared Sequence/Executor и
  внешние триггеры могут менять результат; это не обещание одинакового fade
  любого атрибута при любых настройках шоу.
- Programmer выше обычного playback: ручные значения сохраняются и могут
  перекрыть сцену. Нужен отдельный пользователь/Programmer панели либо явное
  ручное снятие нужных значений. Глобальный ClearAll не используется.
- Grand Master не гарантирует гашение React to Master=Off, Park, DMX tester,
  merge/внешнего DMX и устройств без управляемого dimmer. Это не питание.
  B.O.-маска не меняется. Во время затемнения playback продолжает жить;
  возвращается уровень механизма подавления, а не старый кадр выхода.
- Чужое изменение Grand до ненулевого уровня запрещает восстановление.
  Повторную запись чужого 0 отличить от прежнего 0 нельзя. Операторы должны
  согласовать владение Grand. После reconnect/смены шоу/рестарта/unknown
  автоматического восстановления нет; исходный уровень остаётся в blackout.json.
- При ошибке подготовки/резервирования исходный Cue 1 не трогается. При
  unknown commit нельзя утверждать, какой Cue теперь в target: резерв остаётся
  в spare Cue 2, новый кадр — spare Cue 1, журнал блокирует повторную запись.
  Восстановление оператором: проверить шоу и адреса, затем вручную скопировать
  резерв Cue 2 в целевой Cue 1. Резервный Executor автоматически не удаляется.
- Между List и записью другой оператор может занять место: у MA2 нет
  доказанного compare-and-swap. Нужен выделенный диапазон записи и запрет
  параллельной правки этих объектов. Мост удерживает только собственный lock.

## Что проверять на onPC/в зале

1. Вывести реальные свойства Cue/Grand; подтвердить
   структуру CueZero/Cue 1, Trig и формат value с явным знаком %. Голое число не доказывает процентную шкалу и отклоняется. Если чтение не поддержано,
   панель должна отказаться, а не угадывать исходный уровень/ручной триггер.
2. A→B с частичным пересечением, dimmer вниз/вверх, цвет/позиция, Snap,
   повторное A→B→A, ручной Programmer и посторонний playback.
3. Masterfade+Off: dimmer A-only плавно уходит, non-dimmer удерживаются до
   release; MA2 сама заканчивает уже отправленный fade при обрыве Telnet.
4. Store/Assign/Copy между Executor: новый Cue, старый резерв, известный отказ,
   неизвестный commit, label failure, восстановление только вручную.
5. Grand 37.5→0→37.5, исходный B.O.=On, чужой Grand, React to Master=Off,
   Park/DMX overrides, потеря соединения и перезапуск с журналом.

Windows 11 в Parallels обнаружена в suspended. `prlctl clone` отказал, поскольку
клонирование такого состояния не поддерживается. Исходная VM не запускалась:
в ней может быть рабочее шоу/сетевое подключение. Изолированный onPC не получен,
официальный дистрибутив не устанавливался. Реального испытания MA2 не было.

## Этап 2 — чтение состояния, Patch, группы и движение (2026-11-10)

Проверены официальные страницы **Version 3.9**. Ниже отдельно обозначены
документированные команды и runtime-предпосылки форматов. Нового испытания
на onPC или физическом DMX в этом этапе нет.

| Применение | Официальный источник и границы подтверждения |
|---|---|
| `Fixture 1 + 2`, Fixture ID | [Fixture](https://help.malighting.com/grandMA2/en/help/key_keyword_fixture.html), [Adding fixtures](https://help.malighting.com/grandMA2/en/help/key_patch_add_fixtures.html): Fixture ID и Channel ID различаются, адрес DMX задаётся отдельно. Индекс XML не подменяет Fixture ID. |
| `Export Fixture 1 Thru 9999 "name"`, `Export FixtureType n "name"`, `Export Group 1 Thru 999 "name"` | [Export](https://help.malighting.com/grandMA2/en/help/key_keyword_export.html): Object-list, filename, экспорт XML; типовые объекты имеют отдельные папки, прочие — importexport; выбранный drive влияет на путь. [FixtureType](https://help.malighting.com/grandMA2/en/help/key_keyword_fixturetype.html) — объект типа. Форма конкретного XML и полнота диапазона не гарантируются этой страницей. `/Overwrite` не добавляется. |
| `List FixtureType`, `List Group`, `List Preset` | [List](https://help.malighting.com/grandMA2/en/help/key_keyword_list.html), [Group](https://help.malighting.com/grandMA2/en/help/key_keyword_group.html): чтение объектов/выбор группы. Текстовые столбцы, LongName/DMXFootprint и XML состава — runtime-форматы; часть образцов 3.9.60 уже хранится в tests. Дубли/неразобранные строки отвергаются. Явный No objects found отличается от пустого транспорта. |
| FixtureType Modules/Instances | [Instance Manager](https://help.malighting.com/grandMA2/en/help/key_adv_fixture_anatomy_instance.html): instance ссылается на модуль и задаёт DMX offset. Поддержка одного module_index=0/patch=1 основана также на имеющихся XML-регрессиях. Множество instances, смещения и неизвестная структура — unknown, не догадка о каналах. |
| `Lua … pcall(gma.show.getdmx, address)` → `SetVar` → `ListVar` | [Lua](https://help.malighting.com/grandMA2/en/help/key_keyword_lua.html), [Edit Plugins](https://help.malighting.com/grandMA2/en/help/key_plugins_edit.html), [ListPluginLibrary](https://help.malighting.com/grandMA2/en/help/key_keyword_listpluginlibrary.html): Lua-команда и встроенная библиотека существуют; руководство направляет за API к установленному plugin_1.lua. Публичная страница **не подтверждает точную сигнатуру getdmx**. Сохранён прежний одноадресный вызов из readback-исправлений; runtime требует 0..255, nonce, длину и адрес. Старый трёхаргументный вызов не восстанавливался. Нужна проверка локального API в изолированном onPC 3.9. |
| `Attribute "Pan" At + 5`, `… Tilt At - 2` | [Attribute](https://help.malighting.com/grandMA2/en/help/key_keyword_attribute.html), [Plus](https://help.malighting.com/grandMA2/en/help/key_keyword_plus.html), [Minus](https://help.malighting.com/grandMA2/en/help/key_keyword_minus.html): именованный атрибут и относительное изменение; MA2 применяет шаг к каждому выбранному прибору. Ограничение физическим диапазоном и единицы конкретного профиля требуют onPC/площадки. Никакого вычисленного абсолютного старта при unknown нет. |
| Dimmer/RGB/Shutter | [Attributes](https://help.malighting.com/grandMA2/en/help/key_patch_attributes.html): один атрибут может использовать несколько DMX-байтов/функций. Имена COLORRGB1–3, coarse, from_dmx/to_dmx — предпосылки поддерживаемого XML, не универсальный декодер всех приборов. Только явные непересекающиеся 8-bit Open/Closed интервалы доказывают затвор; strobe/неизвестная единица/неполный byte → unknown. |
| Programmer, Executor и текущий выход | [Playing back Cues](https://help.malighting.com/grandMA2/en/help/key_cs_playback.html): HTP/LTP и разные приоритеты меняют итог. Programmer может перекрыть обычный playback, Super — Programmer. Значения отправленных команд не равны выходу. Readback DMX — байты внутри MA2, не подтверждение физической линии/света/положения механики. |

Не получены: локальный plugin_1.lua, свежие реальные group XML/профили Shutter,
физическая шкала Pan/Tilt каждого типа. Установленного onPC на этом macOS-хосте
не найдено; рабочая VM не запускалась. Пустой или синтаксически корректный,
но семантически укороченный экспорт без списка ожидаемых IDs нельзя объявлять
доказанно полным: неоднозначность/неизвестный формат требует оператора.


## Этап 4 — повторная сверка и onPC 3.9.63.11 (2026-11-10)

Повторно прочитаны официальные страницы Version 3.9: Fade, OutFade,
MasterFade, Go, Goto, Executor, Off, Blackout/SpecialMaster, Store/Assign,
Copy/Delete/Update, Fixture/Group/Attribute, DMX/Lua/Export, Login/NewShow/SaveShow.
Источники — ссылки в таблицах выше; дополнительно:
[NewShow](https://help.malighting.com/grandMA2/en/help/key_keyword_newshow.html),
[SaveShow](https://help.malighting.com/grandMA2/en/help/key_keyword_saveshow.html),
[Login](https://help.malighting.com/grandMA2/en/help/key_keyword_login.html),
[Update](https://help.malighting.com/grandMA2/en/help/key_keyword_update.html),
[Delete](https://help.malighting.com/grandMA2/en/help/key_keyword_delete.html).
`Update` не заменяет транзакцию подготовки/резерва; `Delete` удаляет данные и
не используется перед перезаписью сцены. `Go` может выбрать следующий шаг,
поэтому используется явный Goto Cue 1. OutFade внутри Cue не заменяет Off Time.
Ошибки/потеря prompt останавливают последовательность, неизвестная запись не
повторяется; ACK и занятый Executor не доказывают содержимое или свет.

Исправление прежнего утверждения: **ListPluginLibrary выводит XML-файлы
plugins, а не полный контракт Lua API**. Сигнатуры библиотеки и свойства
нельзя вывести из одного этого ключевого слова. Lua 5.3 и сама команда Lua
документированы; доступность конкретного метода дополнительно проверена ниже.

Среда: APFS-копия существующей VM, новый UUID; исходная VM не запускалась.
Windows 11 ARM64 10.0.26300.9711, onPC **3.9.63.11**, standalone/127.0.0.1;
сеть и USB отключены. Создано новое `PANEL_STAGE4_LAB_20261110` через NewShow
с nosave/noconfirm/protocols. Рабочее шоу из исходной VM не изменялось.
Это **другая сборка**, не целевая 3.9.60. Новый дистрибутив не устанавливался.

Факты из свежих ответов (локальные необезличенные логи `/tmp/ma2-stage4-*.log`):

| Наблюдение | Результат и вывод |
|---|---|
| Grand `List SpecialMaster 2.1` | 100.00%; команда 37.5 → 37.50%, 0 → 0.00%, возврат 37.5 → 37.50%, затем 100. Значение читается в процентах. Это не проверка физических исключений гашения. |
| Lua `getobj.handle('SpecialMaster 2.1')`, `property.get(...,'value')`, `show.setvar` | Свежий nonce и `100.00%` доступны в ListVar этой сборки. Старые сообщения об отсутствии setvar на 3.9.60 этим не опровергнуты. |
| Текущий `dmx_lua(1,3,nonce=...)` | Свежий `$PANELDMX1` содержит `T<nonce> 1 0,0,0`; однобайтовый getdmx работает на пустом шоу. Значения живых приборов и многовселенная физическая линия этим не доказаны. |
| `Store Executor 1.101 Cue 1 /Source=Output /Use=Allforselected` | Принят, созданы Executor/Sequence и пустая Cue 1. Проверено на пустом тестовом шоу, не с фотометрическим содержимым выбранных приборов. |
| Прежний probe этапа 1 | Возвращал `unknown` на действительной ручной Cue: Executor handle имеет только No./Name; priority/softltp там отсутствуют; CMD находится в части Cue. Это был воспроизведённый дефект, не отсутствие прав. |
| Структура Cue | Sequence amount=2, child 0 отсутствует, child 1=Cue 1/number 1; Cue содержит одну CMD_CUE_PART с точным полем CMD (пустая строка). Имена остальных свойств не используются как доказательство отсутствия команды. |
| Исправленный probe | Тот же Executor даёт свежий nonce `manual`; nil child 0 допустим только как начальный пустой слот при подтверждённой единственной Cue 1. Другие отсутствующие/дополнительные объекты не превращаются в ручную сцену. |
| Playback-профиль | Реальный List: `Priority=Normal SoftLTP=on Chaser=off`. Проверяются однозначно три поля; Normal соответствует normal LTP руководства. Неизвестное/повторное поле, HTP, SoftLTP off или Chaser on дают отказ до запуска. |

В одном первом запуске read-only PS probe ошибочно указан разовый ExecutionPolicy
Bypass. Постоянные политики не менялись; последующие проверки выполнены обычным
PowerShell stdin/EncodedCommand без этого флага. Запуск .ps1 при штатной Restricted
закономерно отклонён; политика не ослаблялась для продолжения.

Ключевое ограничение: перечисленные пробы и пустые Cue не доказывают fade/Soft LTP
с частичным пересечением настоящих приборов, захват Output и сохранность значений,
Pan/Tilt разных профилей, физический DMX или совместимость целевой 3.9.60.
План проверки и восстановления — [hardware-acceptance.md](hardware-acceptance.md).


Продолжение испытания этапа 4:

- Реальные Goto Cue 1 / Fade 2, Masterfade 2 и Off приняты без ошибок на
  пустых Cue; List Executor показывает OffTime=2.00. Это проверка синтаксиса
  и настройки времени, а не доказательство формы светового перехода.
- Проба с Trig=Follow вернула unknown; после Trig=Go — manual. Дополнительная
  Cue 2 также дала unknown; отдельный Executor с единственной Cue 1 — manual.
- **Подтверждён новый дефект Copy**: строка без метода открывает интерактивный
  `Choose copy method`. Следующие строки не являются командами, пока открыт
  диалог; реальный MA2Link должен остановиться по unknown/prompt timeout.
  Простое OK mock этого дефекта не показывало.
- Исправление: backup `Copy Cue 1 Executor A At Cue 2 Executor B /CueOnly`,
  commit `Copy Cue 1 Executor B At Cue 1 Executor A /CueOnly /Overwrite`.
  Оба точных варианта приняты onPC 3.9.63.11 без диалога; List подтвердил Cue 1
  target и Cue 2 spare. `/CueOnly` документирован в Copy, предотвращает tracking
  далее; `/NoConfirm` не добавлялся. Guard запрещает Copy Cue без явного метода,
  сохраняет область store_execs и разрешает Overwrite только Cue 1→Cue 1.
- Модель mock дополнена реальным выбором метода без prompt; существующий
  регрессионный сценарий перезаписи сначала упал по timeout, затем прошёл с
  явным CueOnly. Ошибки/unknown commit по-прежнему не приводят к повтору/rollback.
- Первый экспериментальный CLI harness после открытия Copy-диалога отправлял
  дальнейшие строки; они получили Invalid Key и не учитываются как проверки.
  Harness остановлен/исправлен; успешная последовательность — отдельный новый
  сеанс `/tmp/ma2-stage4-native-final.log`. В приложении такого replay нет:
  отсутствие prompt останавливает MA2Link.

### Проверка через настоящий MA2Link и код транзакций

Повторный запуск использовал `link.MA2Link`, `confirm_manual_scene`,
`GrandMasterBlackout` и `safety.make_guard` текущего кода, а не ускоренную
имитацию ответов. У DMX включён allow_fixture_read и временно разрешена только
точная сгенерированная строка, как в координаторе чтения. Произвольная Lua не
разрешалась. `SaveShow` применён только к новому тестовому шоу.

Выявлены и исправлены дополнительные предпосылки:

1. После гостевого prompt onPC присылает отдельный `Please login !`/prompt.
   Он может прийти уже после отправки login. Теперь он дочитывается в пределах
   первоначального login timeout, без повторного login. Свежий ListVar всё ещё
   обязан подтвердить пользователя; отказ/тайм-аут не дают ready.
2. Prompt Lua приходит раньше публикации нового nonce в ListVar. Разрешены
   максимум три завершённых чтения ListVar с паузами 50 мс, чтобы дождаться
   собственного nonce. Сама Lua не пересылается заново. Свежий unknown или
   неоднозначные данные не превращаются в manual/проценты.
3. Даже свежий замер Grand сразу после At может показывать прежний уровень.
   После единственной записи выполняются максимум три новых nonce-замера с
   паузами 50 мс. Успех — только при наблюдении точного target. Если он не
   появился, остаётся unknown/журнал, без повтора записи или компенсации.
   Каждый замер — новая read-only Lua с новым nonce; это не replay старой записи.
4. Ошибка транспорта/отсутствие prompt немедленно прерывает эти процедуры;
   ограниченное дочитывание относится только к завершённым ответам со старым
   маркером/уровнем. Контекст шоу/соединения проверяет вызывающий мост.

**Фактически прошло:** MA2Link login; разрешённая ручная Cue 1; Grand 37.5→0→37.5
через настоящий класс со snapshot/journal/readback; nonce-чтение трёх DMX-адресов;
SaveShow. Свидетельство: `/tmp/ma2-stage4-onpc-source-acceptance-final.log`.
Физических приборов в шоу нет; подтверждены внутренние значения и команды.

Windows CLI: фактически найдено, что selfcheck с cp1252 падал до создания
UTF-8 отчёта. Исправление — настройка stdout/stderr на входе CLI, как у bridge
и updater; регрессия использует настоящий subprocess с принудительным cp1252.
Windows delivery тест не задаёт PYTHONUTF8 для BAT. Только его вложенный тест
API update/rollback настраивает свой поток, поскольку обходит обычный CLI main.


## Уточнение ручного Off по review — 2026-11-10

Повторно сверено с официальной документацией версии 3.9:
[MasterFade](https://help.malighting.com/grandMA2/en/help/key_keyword_masterfade.html)
задаёт Off fade для sequence executors; [Executors](https://help.malighting.com/grandMA2/en/help/key_exec_what_are.html)
объясняет Off Time как снятие интенсивности с удержанием других атрибутов до конца.
Поэтому перед каждым ручным Off выполняются `Masterfade T Executor P.E` и
`Off Executor P.E`, где T берётся из серверного общего Fade. Пример синтаксиса
Masterfade в руководстве прямой; составной адрес P.E уже используется проектом.
Не добавлены предположительные Off Fade или Assign OffTime.

Документальный вывод: прежнее Masterfade не должно оставаться временем следующего
ручного Off. Проверка очередности/значений/guards выполнена тестами; физическая
кривая dimmer, освобождение non-dimmer, повторные Off и прерывание fade на целевой
MA2 3.9.60 требуют новой приёмки. Исторический onPC-прогон ниже/выше её не заменяет.

## Ограничение области crossfade — 2026-11-11

Повторно прочитаны официальные MasterFade, Off, Executors/Off Time и Playing
back Cues версии 3.9. Синтаксис не меняется: Masterfade задаётся прежним запускам
панели, затем Goto целевой сцены и адресный Off прежних. Каталог не является
доказательством активности или владения. Ограниченная серверная стратегия и
границы stale/unknown readback описаны в spec и RELEASE-3.3.md. Модель частичных
пересечений/прерываний проходит; физическая кривая fade остаётся зал-проверкой.
