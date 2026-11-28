@echo off
setlocal
rem Run from external USB staging; never copy updater modules into the installation.
set "TARGET=%~1"
if not defined TARGET set /p "TARGET=Installation program folder: "
if defined TARGET set "TARGET=%TARGET:"=%"
if not defined TARGET (
  echo Error: installation folder was not specified.
  pause
  exit /b 1
)
if not exist "%TARGET%\python\python.exe" (
  echo Error: python\python.exe not found in "%TARGET%".
  echo Specify the path to the ma2-panel\program folder.
  pause
  exit /b 1
)
"%TARGET%\python\python.exe" "%~dp0update.py" --root "%TARGET%" "%~dp0ma2-panel-update.zip"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
