"""Portable Windows entrypoint: browser and localhost server."""
import os
import threading
import time
import webbrowser
import uvicorn
from app import app

def open_browser():
    time.sleep(2)
    webbrowser.open('http://127.0.0.1:8000')

if __name__ == '__main__':
    threading.Thread(target=open_browser, daemon=True).start()
    print('Policem calisiyor: http://127.0.0.1:8000')
    print('Kapatmak icin bu pencereyi kapatin.')
    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')
