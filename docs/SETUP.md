# Install on Windows

**[Download for Windows](https://github.com/coldmoth/ma2-panel/releases/download/v3.2.0/ma2-panel-win.zip)** · [Release notes](RELEASE-3.2.md)

Version **3.2.0 is a pre-release for supervised testing**. Validation with real grandMA2 hardware is not yet complete.

## Before you start

You need Windows 10/11 x64, grandMA2 onPC 3.9 and a modern browser such as Chrome or Edge. The ZIP includes Python 3.12.10 x64 and all application dependencies. You do not need Git, Python, uv or a terminal.

For an existing installation, [back up your data first](ADVANCED.md#back-up-and-move-an-existing-installation). Install 3.2.0 in a separate folder; no update ZIP is published for this release.

## Install and launch

1. Download **ma2-panel-win.zip** using the link above. The GitHub **Source code** archives are for developers and do not include the Windows runtime.
2. In File Explorer, right-click the ZIP and choose **Extract All**. Extract the entire `ma2-panel` folder to a writable location, for example `C:\ma2-panel-3.2`. Keep it outside Program Files, OneDrive and any older installation.
3. Open the extracted `ma2-panel` folder. It contains **`start.bat`** and **`program`**. Keep them together.
4. Open grandMA2 onPC yourself, then double-click the outer **`start.bat`**. Keep the launcher window open while using the panel.
5. The setup wizard opens in your browser. If it does not, open [http://localhost:8080/setup.html](http://localhost:8080/setup.html).

There is no separate **MA2 Panel.exe** in this release.

## Complete setup

При переходе с 3.0 на 3.1 установите полный комплект в отдельную папку, сохранив старую. ZIP обновления не подходит для старого runtime. После остановки
старого моста перенесите в новую папку `program` собственные config.json, settings.json, secret.env, highlight.json,
shows/, diag/, diagnostic-upload.json, field-data/, rdm-search.json, blackout.json,
scene-write-*.json и update_url.txt при наличии. Не заменяйте
их публичными шаблонами. `rdm-search.json` — состояние незавершённого RDM, включая
исходный target: переносите файл целиком, даже если он повреждён или target неизвестен.
Журналы blackout.json и scene-write-*.json также переносите побайтово: они нужны
для разбора незавершённого Blackout или записи Cue. Не удаляйте и не исправляйте
журналы для снятия предупреждения. Перед переносом сохраните
старую папку целиком; старые backups/ и логи можно сохранить отдельно. При ручном
восстановлении из backups/before-update-* сначала остановите мост и сохраните текущую
папку целиком. Не заменяйте более новое неизвестное RDM-состояние старой копией:
сохраните обе версии для отдельной проверки оператором. Копирование не подтверждает RDM Off.
runtime.json/runtime-files.json, Python и lib должны оставаться
из одного полного комплекта. После смены пути или портов повторите `program/firewall-open.bat`
от имени администратора.

Follow [First connection](FIRST-CONNECTION.md). You must create or select a dedicated grandMA2 user with a separate User Profile and enable Telnet Remote **inside grandMA2**. The panel wizard saves connection settings; it does not create the MA2 account or enable Telnet for you.

After saving and restarting the bridge, open the full panel at [http://127.0.0.1:8080](http://127.0.0.1:8080). The simple scene view is at [http://127.0.0.1:8090](http://127.0.0.1:8090). These are the default ports.

A new installation has an empty venue plan and restricted permissions. This is expected. Complete a [supervised first test](ONPC-HALL-TEST-3.2.md) before using real lighting.

## Stop the application

Press **Ctrl+C** in the launcher window, or open **`program/stop.bat`**. Stopping the bridge does not turn off lights or stop scenes already running in MA2. Check the lighting state in onPC.

## Next steps

- [Connect a tablet](TABLET.md)
- [Read the user guide](USAGE.md)
- [Resolve a startup or connection problem](TROUBLESHOOTING.md)
- [Install from source or use mock mode](ADVANCED.md)

[All documentation](README.md)
