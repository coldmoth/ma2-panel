@echo off
rem Logs in and sends READ-ONLY List commands, writes raw replies to probe.txt. Changes nothing in the show.
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0bridge.py" --probe
pause
