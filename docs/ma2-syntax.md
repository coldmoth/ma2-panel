# grandMA2 3.9: проверка синтаксиса для Telnet-моста

Проверено 18 октября 2026 года по официальному англоязычному руководству grandMA2, страницы с пометкой Version 3.9. Команды не выполнялись на onPC. CONFIRMED означает прямое подтверждение руководством; PARTIAL — подтверждена общая конструкция или близкое поведение, но не вся требуемая гарантия; UNKNOWN — подтверждение не найдено. Для UNKNOWN доказательной цитаты нет: приведены прочитанные близкие источники и необходимая живая проверка. Отсутствие команды в найденных страницах не доказывает, что парсер её отвергнет.

Все использованные ниже страницы доступны. Примеры команд с конкретными номерами, полученные подстановкой в документированный синтаксис, отдельно обозначены. Материалы grandMA3 не используются для подтверждения grandMA2. Никаких команд сохранения или загрузки мосту в рамках исследования не отправлялось.

## 1. Export, патч и XML

**CONFIRMED — общий синтаксис:**

```text
Export [Object-list] ["filename"] / [option] = [option value]
Export /?
```

[Export Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_export.html). Короткая цитата: “Exports MA .xml schema definition.” Она подтверждает наличие схемы через опцию ниже; общая форма дана в разделе Syntax этой же страницы.

Все перечисленные руководством опции:

| Опция | Сокращение | Значение и назначение |
|---|---|---|
| `/condition` | `/cnd` | Значения и условия отсылаются к Messages keyword. Универсальное значение для экспорта патча не указано. |
| `/noconfirm` | `/nc` | Без значения; подавляет окно подтверждения. |
| `/overwrite` | `/o` | Без значения; заменяет существующий файл. |
| `/path` | `/p` | Путь; пример руководства: `/path="/data/ma/actual/gma2/ImportExport"`. Это путь из примера, не Windows. |
| `/schema` | Нет | Без значения; экспортирует определение XML-схемы MA. |
| `/style` | Не указано | `html`, `csv`, `default`; последнее — XML со stylesheet для timecode, messages, sequence, fixture, layer, layers. |
| `/transform` | `/t` | Без значения; преобразует файл в заданный стиль. |

Экспорт идёт на выбранный drive. Без имени создаётся отдельный `.xml` для каждого объекта, имя выводится из его свойств. Есть каталоги по типам объектов, например `library` для FixtureType; остальные объекты идут в `importexport`. Поэтому нельзя считать `importexport` единственным каталогом всех экспортов. Для `html`/`csv` роль `/transform` описана, но точные расширения и состав результирующих файлов надо проверить; подтверждённое базовое расширение — `.xml`.

**PARTIAL — Windows-путь 3.9.** [Export and Import](https://help.malighting.com/grandMA2/en/help/key_export_and_import.html), цитата: “on an onPC solution it might be located”. Руководство приводит `C:\ProgramData\MA Lighting Technologies\grandMA\gma2_V_3.3\importexport`. Это пример с оговоркой и старым номером версии, а не точный путь установки 3.9.x. На целевом Windows нужно проверить каталог установленной версии, выбранный drive и созданный файл. Путь с автоматически подставленным `3.9` официально здесь не подтверждён.

**CONFIRMED — экспорт Fixture и Channel как объектов поддерживается.** На странице [Export and Import](https://help.malighting.com/grandMA2/en/help/key_export_and_import.html) в списке экспортируемых объектов прямо перечислены “Channels” и “Fixtures”. Конкретные формы ниже — подстановка в общий синтаксис, а не отдельные примеры руководства:

```text
Export Fixture 1 Thru 9999 "panel-fixtures"
Export Channel 1 Thru 9999 "panel-channels"
Export FixtureType 1 "panel-type"
```

**CONFIRMED — FixtureType экспортируется:** [Export Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_export.html) прямо указывает “FixtureType (library-folder)”. [FixtureType Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_fixturetype.html) задаёт `FixtureType [ID]` и предупреждает, что большинство действий с типами требуют Edit Setup. Проверить контекст выполнения экспорта через Telnet, не открывая патч на рабочем шоу без необходимости.

**CONFIRMED — слои патча экспортируются следующей дословной командой:**

```text
Export Root LiveSetup.Layers
```

[Root Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_root.html), цитата: “Export all live setup layers”. Пример указывает каталог `fixture_layers` внутри старого `gma2_V_3.1`. Руководство рекомендует имена узлов Root вместо числовых индексов.

**UNKNOWN — `Export Layer ...` как экспорт слоя патча.** [Layer Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_layer.html), цитата: “change the working layer of the attribute encoders”. `Layer [layer ID]` / `Layer [layer name]` здесь относится к Value, Fade, Delay и слоям эффектов. Нельзя подменять этим путь `Root LiveSetup.Layers`. Проверять альтернативную команду только на копии шоу.

**PARTIAL — какой экспорт даст ID, имя и имя типа.** Для инвентаризации патча документированным исходным объектом являются `Root LiveSetup.Layers`; экспорт Fixture также поддерживается. [Adding fixtures to the show](https://help.malighting.com/grandMA2/en/help/key_patch_add_fixtures.html) описывает колонки патча `FixID`, `ChaID`, `Name`, `Fixture Type`; цитата: “This is the Fixture ID number.” Но это описание таблицы GUI, не контракт экспортированного XML. Рекомендация исследовать экспорт слоёв — вывод из этих страниц, а не гарантия наличия конкретных XML-полей. Один FixtureType описывает тип, и его экспорт не подтверждает получение списка экземпляров с ID.

**UNKNOWN — XML-элементы и атрибуты `fixture_id`, `FixtureType`, ссылки между экземпляром и типом.** Публичное описание этих имён в прочитанных страницах не найдено. **CONFIRMED** только механизм `/schema` ([Export Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_export.html), цитата выше). На onPC 3.9.x следует экспортировать слои, несколько fixtures и используемые типы; получить схему через `/schema`, сравнить фактические имена, namespace и связи. Конкретный вызов с `/schema`, имя файла схемы и её полнота для патча отдельно не проиллюстрированы руководством — проверить на месте. Не писать XML-парсер по предположительным именам.

## 2. List, список шоу и SelectDrive

**CONFIRMED — общий List:**

```text
List [Object-list] / [Option]= [Option Value]
List /?
```

[List Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_list.html), цитата: “You can list any object”. Без объекта выводится текущая destination. Опции: `/condition` (`/cnd`) только с Messages; `/filename` (`/f`) с именем создаёт CSV в `reports`.

**PARTIAL — `List Fixture` и `List Fixture 1 Thru 9999`.** Они следуют из общей формы List, объекта Fixture и диапазона Thru, однако отдельного примера и списка колонок именно для fixtures руководство List не даёт. [Fixture Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_fixture.html), цитата: “access fixtures with a fixture ID”. Колонки FixID/Name/Fixture Type в GUI патча не доказывают наличие таких колонок в List. На onPC выполнить обе команды через Telnet, сохранить заголовки, строки, пустые результаты и завершение ответа; проверить имена с пробелами и fixtures без Fixture ID.

**UNKNOWN — `ListFixture`.** В [Function Keywords](https://help.malighting.com/grandMA2/en/help/key_cs_function_keywords.html) и странице List подтверждения слитного keyword не найдено; доказательной цитаты нет. Если этот вариант нужен, проверить распознавание через встроенную справку и CLI. Документированная общая форма — раздельные функция и объект.

**CONFIRMED — список файлов шоу:**

```text
ListShows [Filter]
ListShows
ListShows f*
```

[ListShows Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_listshows.html), цитата: “display the show files on the selected drive”. Сокращение — `ListS`. **UNKNOWN** для `List Shows` и `ListShow`: эти написания не подтверждены страницей. Не считать их синонимами без проверки парсера. Формат колонок и машинный протокол окончания списка в Telnet не описаны.

**CONFIRMED — выбор и перечисление drives:**

```text
SelectDrive [ID]
SelectDrive
SelectDrive 2; LoadShow "demo dimmer and more"
```

[SelectDrive Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_selectdrive.html), цитата: “will be listed along with their ID”. Без ID выводит доступные носители, USB и предыдущие установки; с ID выбирает drive для SaveShow, LoadShow, Import, Export. Если выбран read-only drive, операции записи переключаются на `1` (Internal). Нельзя считать выбор read-only носителя гарантией запрета записи. Номера обнаруживать через `SelectDrive`; пример с `2` относится к demo.

## 3. $SHOWFILE и ListVar

**CONFIRMED — `$SHOWFILE` предопределена и содержит имя шоу.** [Use variables in macros](https://help.malighting.com/grandMA2/en/help/key_macro_create_variables.html), цитата: “This is the name of the show.” Это имя, не подтверждённый абсолютный путь или имя с расширением.

**CONFIRMED — печать переменных:**

```text
ListVar [Filter]
ListVar
ListVar f*
```

[ListVar Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_listvar.html), цитата: “variables and their values”. Фильтр по имени `ListVar SHOWFILE` — подстановка в эту форму, **PARTIAL** до проверки точного сопоставления на onPC; передавать `$SHOWFILE` как фильтр не требуется, поскольку подстановка переменной заменяет её содержимым.

Документированный пример вывода из [Use variables in macros](https://help.malighting.com/grandMA2/en/help/key_macro_create_variables.html):

```text
[time] : Global : $CHORUS_CHASERS = Executor 201 + 204 + 205
```

Это пример другой переменной, **PARTIAL** для точного формата строки `$SHOWFILE` через Telnet. Руководство описывает Command Line Feedback, не байтовый формат TCP-ответа. Проверить метку времени, префикс, кавычки, переносы и окончание ответа. Переменные регистронезависимы; ListVar показывает и глобальные, и пользовательские, ListUserVar — только пользовательские.

## 4. LoadShow, несохранённое шоу, пользователи и файлы

**CONFIRMED — синтаксис:**

```text
LoadShow "Showname" / [Option]
LoadShow /?
```

[LoadShow Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_loadshow.html), цитата: “loads a show from the selected drive”. Если имя не найдено, загружается новое пустое шоу; в сессии шоу передаётся подключённым станциям.

Все документированные опции без дополнительных значений:

| Опция | Сокращение | Смысл |
|---|---|---|
| `/full` | `/f` | Загружает весь набор перечисленных категорий из существующего шоу; очищает их для нового. |
| `/globalsettings` | `/g` | Глобальные настройки. |
| `/localsettings` | `/l` | Локальные настройки. |
| `/network` | `/n` | Конфигурация сети. |
| `/noconfirm` | `/nc` | Убирает предупреждение с предложением сначала сохранить шоу. |
| `/nodata` | Нет | Сохраняет текущие show data в новом шоу. |
| `/nosave` | `/ns` | Не сохраняет текущее шоу. |
| `/protocols` | `/p` | Сетевые протоколы. |
| `/save` | `/s` | Сохраняет текущее шоу. |
| `/timeconfig` | `/t` | Согласно таблице очищает time config. |
| `/user` | `/u` | Согласно таблице очищает user profiles. |

Для категорий настроек таблица описывает очистку при новом и загрузку при существующем шоу; `/full` включает show data, global settings, protocols, user profiles, time config, local settings, network config. **UNKNOWN** — `/keepnetwork`, `/nouser`: в таблице их нет, положительные `/network` и `/user` не доказывают существование обратных форм. Проверить `LoadShow /?` на установленном build. Не выводить из списка опций недокументированные правила их сочетания или приоритетов.

**CONFIRMED — предложение сохранить является pop-up.** [LoadShow Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_loadshow.html), цитата: “asks if you want to save the show file first”. `/nosave` описывает отказ от сохранения, `/noconfirm` — подавление окна; это разные гарантии. **UNKNOWN** — текстовый вопрос и способ ответа по Telnet: руководство их не описывает. На тестовом шоу с несохранёнными изменениями проверить обычный LoadShow и варианты опций, включая их совместное применение; записать GUI и Telnet. Не предполагать, что вопрос можно обработать строкой `yes`.

**CONFIRMED — пользователи и профили находятся в шоу.** [Loading a show](https://help.malighting.com/grandMA2/en/help/key_backup_menu_load_show.html), цитата: “load all the Users and User Profiles from the show file”. Загрузка категории User Profiles заменяет текущих Users и User Profiles. Есть отдельный нюанс: Show Data без User Profiles перезаписывает существующие профили из загружаемого шоу, добавляет дополнительные профили, но не добавляет Users. Global Settings включают разрешение Telnet, поэтому загрузка этих настроек также существенна для моста.

**UNKNOWN — судьба уже вошедшего Telnet-пользователя `panel`.** [Telnet Remote](https://help.malighting.com/grandMA2/en/help/key_remote_control_telnet.html) требует вход пользователем шоу, но не гарантирует сохранение TCP-соединения, логина, programmer или прав после LoadShow. Проверить загрузку шоу с тем же `panel`, с другим паролем/профилем, без `panel`, с выключенным Telnet; проверить необходимость повторного Login. Не переносить описание пользователей в гарантию непрерывной Telnet-сессии.

**CONFIRMED — `.show.gz` и относительный каталог `gma2/shows`.** [Loading a show](https://help.malighting.com/grandMA2/en/help/key_backup_menu_load_show.html), цитата: “my_showfile.show.gz from the gma2/shows folder”. Пример относится к запуску onPC с параметром `-s`. **PARTIAL** — абсолютный Windows-путь: сочетание примера ProgramData из Export and Import и этого относительного пути не подтверждает точный `C:\ProgramData\...\gma2_V_3.9...\shows`. Проверить фактический каталог версии, не конструировать его как установленный факт.

## 5. SaveShow — только документация

**CONFIRMED:**

```text
SaveShow "Showname" /noconfirm
SaveShow "Macbeth"
SaveShow
```

[SaveShow Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_saveshow.html), цитата: “the show will be saved with the current show name”. Сохраняет на выбранный drive; имя можно опустить. При совпадении имени спрашивает о перезаписи или отмене. `/noconfirm` подавляет подтверждение сохранения. Других опций эта страница не перечисляет. Автоматическая отправка SaveShow не предлагается и не выполнялась.

## 6. Programmer: пользователь, профиль, станция и Telnet

**CONFIRMED — programmer принадлежит User, а не уникальному User Profile.** [Create user profiles and users](https://help.malighting.com/grandMA2/en/help/key_single_multi_systems_create.html), цитата: “Each User have their own programmer”. Несколько Users могут использовать один профиль, имея отдельные programmers и выбранные элементы; профиль разделяет views и другие настройки. Поэтому отдельный профиль сам по себе не является определением изоляции programmer. Независимый programmer на каждую станцию при одном User этой цитатой не гарантирован.

**PARTIAL — отдельный programmer Telnet `panel` относительно другого пользователя оператора.** [Telnet Remote](https://help.malighting.com/grandMA2/en/help/key_remote_control_telnet.html), цитата: “a login command for one of the users in the show”. После входа доступны команды CLI; руководство рекомендует специального пользователя для Telnet. Вместе с правилом отдельного programmer у User это обосновывает изоляцию `panel` от другого User оператора, но прямой фразы о выделенном Telnet programmer нет. Проверить одновременно разные атрибуты/selection под `panel` и оператором, включая общий профиль, выход и повторный вход. Раздельные programmers не означают раздельный физический световой выход.

## 7. Off, knockout и Release

**CONFIRMED — `Off Fixture 3` удаляет из programmer все атрибуты этого прибора.** Это подстановка номера в пример `Off Fixture 1 Thru 10` страницы [What is the Programmer](https://help.malighting.com/grandMA2/en/help/key_of_what_is_the_programmer.html). Цитата: “To remove all attributes from fixture 1 to 10 in the programmer”. Это не установка dimmer в ноль и не удаление прибора из патча.

[Off Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_off.html) задаёт:

```text
Off [Object-list]
Off Fixture 1 + 3
```

Цитата: “Knock out parameters of the programmer.” **CONFIRMED** — knockout как операция удаления значений. **UNKNOWN** — самостоятельное слово `Knockout` как keyword grandMA2: в прочитанном справочнике не найдено. Не переносить синтаксис KnockOut из grandMA3; проверить встроенную справку/парсер, если это необходимо.

**CONFIRMED — отдельный атрибут можно убрать у текущей selection:**

```text
Off Attribute 1
```

[Attribute keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_attribute.html), цитата: “Knocks out first attribute (Dim) for current selection.” Там же документировано `Attribute "Name"` и рекомендованы уникальные library names вместо меняющихся номеров. Поэтому `Off Attribute "Dim"` для текущей selection — вывод из документированной грамматики. Для только Fixture 3: сначала установить selection именно из него, затем выполнить Off Attribute. **PARTIAL** для готовой последовательности `Fixture 3`, затем `Off Attribute "Dim"`: проверить, что selection не содержит ранее выбранных приборов и затронут только Dim. Точный однострочный вариант `Off Fixture 3 Attribute "Dim"` — **UNKNOWN**, отдельного подтверждения не найдено; проверить до использования. GUI-удаление одиночного атрибута через Off и касание также описано в What is the Programmer.

**CONFIRMED — Release записывает специальные release-значения, не очищает programmer:**

```text
Release [Object-list]
Release [Effect-list]
Release Selection
Release PresetType "position"
Release Effect 4
```

[Release Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_release.html), цитата: “enters release values in the programmer”. Object-list фильтруется текущей selection. Для обычных объектов действует на value layer, для эффекта — на effect layer работающих атрибутов. При Store Merge release снимает ранее tracked-значения, приборы используют default; в programmer отображается `(R)`. Это сохраняемое содержимое с иной семантикой, чем Off.

**UNKNOWN — `At Release`.** На страницах [Release Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_release.html) и [At keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_at.html) не найдено прямого примера или явного объявления такой формы. Не считать эквивалентом Off. Проверить на одном атрибуте тестового шоу, сравнить с Release Selection и посмотреть `(R)`, активность и итоговый выход. Доказательной цитаты для этой формы нет.

## 8. Highlight / Lowlight

**CONFIRMED — формы без опций:**

```text
Highlight
Highlight On
Highlight Off
```

[Highlight Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_highlight.html), цитата: “apply the defined highlight values on selected fixtures”. Без On/Off переключает режим. Действует на выбранные fixtures; это не обещание dimmer=100 для любого типа. [DMX and Parameter lists](https://help.malighting.com/grandMA2/en/help/key_patch_dmx_parameter_list.html), цитата: “the parameter will not be overwritten by the Highlight function”. Речь о параметрах с highlight `None`.

**PARTIAL — «только выход, programmer не изменяется».** Страница Highlight описывает режим, но явно эту гарантию не формулирует. Для другой команды [FullHighlight keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_fullhighlight.html) прямо сказано: “Takes the highlight values actively into the programmer.” Форма `Fullhighlight` подтверждена, но это не доказательство противоположной гарантии для Highlight. Проверить исходные programmer values и active markers до/во время/после Highlight On/Off, а также сохранение при источнике Prog. Не подменять Highlight командой Fullhighlight.

**PARTIAL — принадлежность режима пользователю/станции.** В [Release Notes — Version 2.1](https://help.malighting.com/grandMA2/en/help/release_notes/key_rn_v2_1.html) сказано: “only highlight and solo are deactivated, programmer values will remain”. Контекст — выход пользователя из сессии. Это подтверждает различие состояния Highlight и programmer, но историческая заметка не определяет полностью область действия режима между Telnet, несколькими станциями и одним User. Проверить две разные учётные записи и две сессии одной учётной записи. Не объявлять режим глобальным или строго станционным без теста.

**UNKNOWN — Lowlight в grandMA2 3.9.** Ни `Lowlight`, ни `Lowlight On/Off`, ни его семантика/принадлежность не найдены в прочитанном справочнике grandMA2: [Function Keywords](https://help.malighting.com/grandMA2/en/help/key_cs_function_keywords.html), [Highlight Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_highlight.html). Доказательной цитаты нет. Найденные поиском статьи Lowlight относятся к grandMA3 и не подтверждают grandMA2. Проверить доступность keyword через справку/CLI на 3.9.x; не отправлять его мостом как известную команду.

Близкая, но отдельная функция — **CONFIRMED** `Solo`, `Solo On`, `Solo Off`: [Solo Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_solo.html), цитата: “forces zero values for intensity output”. Она подавляет intensity невыбранных fixtures/channels, с исключением через React to Master. Называть её Lowlight нельзя.

## 9. Fixture и Dimmer

**CONFIRMED — выбрать прибор по Fixture ID, затем задать dimmer selection:**

```text
Fixture 12
At 100
```

Это подстановка номеров в документированные формы. [Fixture Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_fixture.html), цитата: “entering fixtures without any function specified selects the fixtures”. [At keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_at.html) приводит `At 75`; цитата: “Sets the dimmer attributes of current selection to 75%.” Тот же синтаксис допускает `Fixture 12 At 100`. Значение — проценты dimmer, не всех атрибутов; результат зависит от реальной selection и наличия Dimmer у прибора.

**CONFIRMED — диапазон и список:**

```text
Fixture 1 Thru 30
Fixture 1 + 3 + 5
```

Числа подставлены в общую грамматику. [Thru Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_thru.html) даёт `Fixture 3 Thru 6`; цитата: “a range of objects / values”. [+ [Plus] keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_plus.html), цитата: “combine multiple objects in a list”. Порядок selection имеет значение; [Groups](https://help.malighting.com/grandMA2/en/help/key_groups.html) прямо различает `Fixture 1 + 2` и `Fixture 2 + 1`. Проверка синтаксиса не является гарантией, что указанные ID существуют в конкретном шоу или доступны пользователю в текущем World.

## Сводная таблица

| question | command | confidence | URL |
|---|---|---|---|
| 1. Export, опции, XML | `Export [Object-list] ["filename"] / [option] = [option value]`; `/schema` | CONFIRMED | [Export](https://help.malighting.com/grandMA2/en/help/key_keyword_export.html) |
| 1. Слои патча | `Export Root LiveSetup.Layers` | CONFIRMED | [Root](https://help.malighting.com/grandMA2/en/help/key_keyword_root.html) |
| 1. Точный путь 3.9 и XML-поля | Экспорт и проверка файлов/схемы на onPC | PARTIAL / UNKNOWN | [Export and Import](https://help.malighting.com/grandMA2/en/help/key_export_and_import.html) |
| 2. Fixture-список и колонки | `List Fixture`; `List Fixture 1 Thru 9999` | PARTIAL; колонки UNKNOWN | [List](https://help.malighting.com/grandMA2/en/help/key_keyword_list.html) |
| 2. Список шоу | `ListShows [Filter]` | CONFIRMED | [ListShows](https://help.malighting.com/grandMA2/en/help/key_keyword_listshows.html) |
| 2. Выбор носителя | `SelectDrive [ID]` | CONFIRMED | [SelectDrive](https://help.malighting.com/grandMA2/en/help/key_keyword_selectdrive.html) |
| 3. Имя шоу и переменные | `$SHOWFILE`; `ListVar [Filter]` | CONFIRMED; Telnet-формат PARTIAL | [Variables](https://help.malighting.com/grandMA2/en/help/key_macro_create_variables.html) |
| 4. Загрузка и опции | `LoadShow "Showname" / [Option]` | CONFIRMED; `/keepnetwork`, `/nouser` UNKNOWN | [LoadShow](https://help.malighting.com/grandMA2/en/help/key_keyword_loadshow.html) |
| 4. Пользователи, файлы, повторный вход | `LoadShow`; `.show.gz` | CONFIRMED для Users/расширения; Telnet UNKNOWN | [Loading a show](https://help.malighting.com/grandMA2/en/help/key_backup_menu_load_show.html) |
| 5. Сохранение | `SaveShow "Showname" /noconfirm`; `SaveShow` | CONFIRMED | [SaveShow](https://help.malighting.com/grandMA2/en/help/key_keyword_saveshow.html) |
| 6. Programmer | Отдельный User `panel` | CONFIRMED per User; Telnet PARTIAL | [Users](https://help.malighting.com/grandMA2/en/help/key_single_multi_systems_create.html) |
| 7. Удаление всех атрибутов | `Off Fixture 3` | CONFIRMED | [Programmer](https://help.malighting.com/grandMA2/en/help/key_of_what_is_the_programmer.html) |
| 7. Один атрибут selection | `Off Attribute 1` | CONFIRMED | [Attribute](https://help.malighting.com/grandMA2/en/help/key_keyword_attribute.html) |
| 7. Release | `Release Selection`; `Release [Object-list]` | CONFIRMED; `At Release`, `Knockout` UNKNOWN | [Release](https://help.malighting.com/grandMA2/en/help/key_keyword_release.html) |
| 8. Highlight | `Highlight On`; `Highlight Off` | CONFIRMED; output-only/область PARTIAL | [Highlight](https://help.malighting.com/grandMA2/en/help/key_keyword_highlight.html) |
| 8. Lowlight | `Lowlight` | UNKNOWN | [Function Keywords](https://help.malighting.com/grandMA2/en/help/key_cs_function_keywords.html) |
| 9. Dimmer selection | `Fixture 12`, затем `At 100` | CONFIRMED | [At](https://help.malighting.com/grandMA2/en/help/key_keyword_at.html) |
| 9. Диапазон и список | `Fixture 1 Thru 30`; `Fixture 1 + 3 + 5` | CONFIRMED | [Thru](https://help.malighting.com/grandMA2/en/help/key_keyword_thru.html), [Plus](https://help.malighting.com/grandMA2/en/help/key_keyword_plus.html) |

## Группы и пресеты (v4)

Проверено 18 октября 2026 года по тем же страницам руководства grandMA2 Version 3.9. Команды на пульте не выполнялись.

**CONFIRMED — выбор приборов группы.** [Group Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_group.html): синтаксис `Group [ID]`, пример `Group 3`, цитата: “Selects the fixtures stored in group 3.” Функция по умолчанию — SelFix. Заменяет ли `Group n` текущий выбор или добавляет к нему, страница не говорит: **UNKNOWN**, проверить на месте. Мост перед `Group n` не шлёт `Clear` (запрещён); если выбор добавляется, сначала выбирать приборы панели обычным `Fixture …` не нужно — панель показывает состав из `List Group`, только когда он распознан.

**CONFIRMED — применение пресета к выбору.** [Preset Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_preset.html): синтаксис `Preset [Preset-type].[ID]`; при выбранных приборах функция по умолчанию — At; пример `At Preset 3.2`, цитата: “Sets current selection to the second preset of preset type 3”. Шаблон моста: `At Preset {type}.{n}`.

**PARTIAL — номера типов пресетов.** Страница подтверждает только 3 = gobo. Номера 2 = position и 4 = color — общепринятая раскладка пула, но на прочитанных страницах не подтверждены. Номера типов задаются в `settings.json` (`ma2.preset_types`), по умолчанию `{"position": 2, "color": 4}`.

**CONFIRMED — команды списка, PARTIAL — их вывод.** [List Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_list.html): `List [Object-list]`; примеры `List Group Thru 10` и `List Preset 4."m*"`; вывод идёт в окно обратной связи командной строки, формат вывода не описан. Шаблоны по умолчанию: `List Group 1 Thru 999`, `List Preset 4.1 Thru 4.999`, `List Preset 2.1 Thru 2.999`. Разбор — регулярками из `settings.json`; ничего не распознано → ничего не меняется, сырой ответ в диагностике. Состав группы (ID приборов) в выводе `List Group` не гарантирован: **UNKNOWN**.

**PARTIAL — запись группы.** [Store Keyword](https://help.malighting.com/grandMA2/en/help/key_keyword_store.html): `Store [object-list] "Name" / [option]`; `/noconfirm` описан как “Suppress stores confirmation pop-up”, значит запись в занятый объект может открыть окно подтверждения, на которое Telnet-сессия не ответит. Поэтому мост пишет только в пустой номер: перед `Store Group n "Имя"` шлёт `List Group n` и отказывается, если номер распознан как занятый или ответ не распознан. Без `/overwrite`, `/merge`, `/noconfirm`. Поведение `Store Group` в пустой номер через Telnet проверить на месте.
