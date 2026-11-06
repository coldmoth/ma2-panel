@echo off
rem Prints this PC addresses and settings, tests that the Telnet port answers. Logs in nowhere, sends nothing.
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0bridge.py" --check
pause
