@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo python\python.exe not found. Copy the WHOLE ma2-panel folder, not single files.
  pause
  exit /b 1
)
set "OPEN_PAGE=--open-browser"
set "LAUNCH_MA2=1"
set "BRIDGE_ARGS="
set "SETTINGS_PATH=%~dp0settings.json"
:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--no-ma2" (
  set "LAUNCH_MA2=0"
  shift
  goto parse_args
)
if /i "%~1"=="--settings" (
  if not "%~2"=="" (
    set "SETTINGS_PATH=%~2"
    set "BRIDGE_ARGS=%BRIDGE_ARGS% %1 %2"
    shift
    shift
    goto parse_args
  )
)
set "BRIDGE_ARGS=%BRIDGE_ARGS% %1"
shift
goto parse_args
:args_done
if "%LAUNCH_MA2%"=="1" (
  "%~dp0python\python.exe" -m ma2panel.launcher --settings "%SETTINGS_PATH%"
)
:run_bridge
if exist "%~dp0.updates\recovery.py" (
  "%~dp0python\python.exe" "%~dp0.updates\recovery.py" --recover "%~dp0."
  if errorlevel 1 (
    echo Update recovery failed. Do not start the bridge before resolving this error.
    pause
    exit /b 1
  )
)
"%~dp0python\python.exe" "%~dp0bridge.py" %OPEN_PAGE% %BRIDGE_ARGS%
if %errorlevel%==3 (
  set "OPEN_PAGE="
  echo Restarting the bridge with new settings...
  goto run_bridge
)
echo.
echo Bridge stopped (code %errorlevel%). Log: bridge.log
pause
