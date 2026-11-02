@echo off
rem Run as Administrator. Opens ONLY: this python.exe, TCP 8080 and 8090, from the local subnet, private/domain networks.
net session >nul 2>&1
if errorlevel 1 (
  echo Right click - Run as administrator.
  pause
  exit /b 1
)
netsh advfirewall firewall delete rule name="MA2 panel" >nul 2>&1
netsh advfirewall firewall add rule name="MA2 panel" dir=in action=allow program="%~dp0python\python.exe" protocol=TCP localport=8080 remoteip=LocalSubnet profile=private,domain enable=yes
netsh advfirewall firewall delete rule name="MA2 simple panel" >nul 2>&1
netsh advfirewall firewall add rule name="MA2 simple panel" dir=in action=allow program="%~dp0python\python.exe" protocol=TCP localport=8090 remoteip=LocalSubnet profile=private enable=yes
echo.
echo Done. Remove it later with firewall-close.bat
pause
