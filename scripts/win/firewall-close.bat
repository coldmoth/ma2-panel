@echo off
net session >nul 2>&1
if errorlevel 1 (
  echo Right click - Run as administrator.
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="MA2 panel"
netsh advfirewall firewall delete rule name="MA2 simple panel"
pause
