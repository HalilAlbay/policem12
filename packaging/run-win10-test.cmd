@echo off
setlocal
set "POLICEM_DATA=%LOCALAPPDATA%\PolicemTest\data"
set "POLICEM_BIND_HOST=127.0.0.1"
set "POLICEM_PORT=8000"
if not exist "%POLICEM_DATA%" mkdir "%POLICEM_DATA%"
start "" "http://127.0.0.1:8000/"
"%~dp0PolicemServer.exe"
if errorlevel 1 (
  echo Policem TEST sunucusu baslatilamadi.
  pause
)
