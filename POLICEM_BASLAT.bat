@echo off
setlocal
cd /d "%~dp0"
title Policem - Yerel Sunucu
where py >nul 2>&1
if not errorlevel 1 (
 set "PY=py -3"
) else (
 where python >nul 2>&1
 if errorlevel 1 (
  echo Python 3 bulunamadi. https://www.python.org/downloads/windows/ adresinden Python 3.11 veya uzerini kurun.
  echo Kurulumda Add Python to PATH secenegini isaretleyin.
  pause
  exit /b 1
 )
 set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
 echo Ilk kurulum yapiliyor...
 %PY% -m venv .venv
 if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
start "" "http://127.0.0.1:8000"
echo Policem aciliyor. Bu pencereyi uygulamayi kullanirken KAPATMAYIN.
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Baslatma basarisiz. Yukaridaki hata mesajini paylasin.
pause
exit /b 1
