@echo off
rem Read-only self-check of the running bridge (start.bat must be running). Changes nothing on MA2. Report: selfcheck-report.txt
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0selfcheck.py"
pause
