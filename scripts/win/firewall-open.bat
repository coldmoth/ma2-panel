@echo off
rem Run as Administrator. Opens ONLY: this python.exe, the ports in settings.json, from the local subnet, private/domain networks.
net session >nul 2>&1
if errorlevel 1 (
  echo Right click - Run as administrator.
  pause
  exit /b 1
)
"%~dp0python\python.exe" "%~dp0firewall.py"
if errorlevel 1 (
  echo Firewall update failed. Check settings.json and run as Administrator.
  pause
  exit /b 1
)
echo.
echo Done. Remove it later with firewall-close.bat
pause
