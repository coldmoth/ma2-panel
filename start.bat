@echo off
setlocal
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo python\python.exe not found. Copy the WHOLE ma2-panel folder, not single files.
  pause
  exit /b 1
)
:run_bridge
"%~dp0python\python.exe" "%~dp0bridge.py" %*
if %errorlevel%==3 (
  echo Restarting the bridge with new settings...
  goto run_bridge
)
echo.
echo Bridge stopped (code %errorlevel%). Log: bridge.log
pause
