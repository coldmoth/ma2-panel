@echo off
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0bridge.py" --stop
pause
