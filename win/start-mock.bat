@echo off
rem Fake console inside the program: NOTHING is sent to the real grandMA2.
cd /d "%~dp0"
:run_bridge
"%~dp0python\python.exe" "%~dp0bridge.py" --mock
if %errorlevel%==3 (
  echo Restarting the bridge with new settings...
  goto run_bridge
)
echo.
echo Bridge stopped (code %errorlevel%). Log: bridge.log
pause
