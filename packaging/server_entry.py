"""Frozen entrypoint for the existing FastAPI application."""
import os
import sys
from pathlib import Path

def main():
    if getattr(sys, "frozen", False):
        root = Path(os.environ.get("PROGRAMDATA", str(Path.home()))) / "Policem"
        root.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("POLICEM_DATA", str(root / "data"))
    import uvicorn
    from app import app
    host = os.environ.get("POLICEM_BIND_HOST", "127.0.0.1")
    port = int(os.environ.get("POLICEM_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("Invalid POLICEM_PORT")
    uvicorn.run(app, host=host, port=port, proxy_headers=False, log_level="info")

if __name__ == "__main__":
    main()
