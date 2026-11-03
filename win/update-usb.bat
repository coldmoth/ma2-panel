@echo off
rem Copy update.py, release.py, ma2-panel-update.zip and this file into the ma2-panel folder, then double-click this file.
rem config.json, settings.json, secret.env and shows\ are not in the update: they stay as they are (and are copied to backups\ first).
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0update.py" "%~dp0ma2-panel-update.zip"
pause
