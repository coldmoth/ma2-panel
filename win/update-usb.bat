@echo off
setlocal
rem Run from external USB staging; never copy updater modules into the installation.
set "TARGET=%~1"
if not defined TARGET set /p "TARGET=Installation program folder (without quotes): "
if not exist "%TARGET%\python\python.exe" exit /b 1
"%TARGET%\python\python.exe" "%~dp0update.py" --root "%TARGET%" "%~dp0ma2-panel-update.zip"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
