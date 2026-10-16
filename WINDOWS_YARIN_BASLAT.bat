@echo off
cd /d "%~dp0"
python --version || (echo Python bulunamadi. & pause & exit /b 1)
python -m pip install -r requirements.txt || (pause & exit /b 1)
set POLICEM_DATA=%~dp0data
set POLICEM_SETUP_KEY=local-only-setup-key-change-before-public-deployment
start "" "http://127.0.0.1:8000/musteri"
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
