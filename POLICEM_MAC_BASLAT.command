#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "POLICEM - MacBook baslatiliyor"
if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else
  echo "Python 3 bulunamadi. https://www.python.org/downloads/macos/ adresinden Python 3 kurun."
  read -r -p "Cikmak icin Enter..." _
  exit 1
fi
if [ ! -d ".venv" ]; then "$PYTHON" -m venv .venv; fi
source .venv/bin/activate
python -m pip install -r requirements.txt || { echo "Paket kurulumu basarisiz"; exit 1; }
export POLICEM_DATA="$PWD/data"
if [ -z "${POLICEM_SETUP_KEY:-}" ]; then
  if [ ! -f ".local_setup_key" ]; then
    python -c 'import secrets,pathlib; pathlib.Path(".local_setup_key").write_text(secrets.token_urlsafe(32))'
    chmod 600 .local_setup_key
  fi
  export POLICEM_SETUP_KEY="$(cat .local_setup_key)"
fi
echo ""
echo "Uygulama: http://127.0.0.1:8000"
echo "Musteri: http://127.0.0.1:8000/musteri"
echo "Ilk hesap kurulum anahtari .local_setup_key dosyasinda (gizli tutun)."
(sleep 3; open "http://127.0.0.1:8000") >/dev/null 2>&1 &
python -m uvicorn app:app --host 127.0.0.1 --port 8000
