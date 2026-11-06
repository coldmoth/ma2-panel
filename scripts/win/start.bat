@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo python\python.exe not found. Copy the WHOLE ma2-panel folder, not single files.
  pause
  exit /b 1
)
set "OPEN_PAGE=--open-browser"
:run_bridge
if exist "%~dp0.updates\recovery.py" (
  "%~dp0python\python.exe" "%~dp0.updates\recovery.py" --recover "%~dp0."
  if errorlevel 1 (
    echo Update recovery failed. Do not start the bridge before resolving this error.
    pause
    exit /b 1
  )
)
"%~dp0python\python.exe" "%~dp0bridge.py" %OPEN_PAGE% %*
if %errorlevel%==3 (
  set "OPEN_PAGE="
  echo Restarting the bridge with new settings...
  goto run_bridge
)
echo.
echo Bridge stopped (code %errorlevel%). Log: bridge.log
pause
