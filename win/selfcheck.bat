@echo off
rem Read-only self-check of the running bridge (start.bat must be running). Changes nothing on MA2. Report: selfcheck-report.txt
setlocal
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0selfcheck.py" %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
