"""Dedicated disposable API for browser tests. No bot or external messages."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
(root / "tmp").mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + str(root / "tmp" / "browser-audit.db")
os.environ["FRONTEND_ORIGINS"] = "http://127.0.0.1:3130,http://localhost:3130"

from app import max_bot

def disabled_transport(*args, **kwargs):
    raise RuntimeError("External MAX calls are disabled in the audit environment")

max_bot.max_api_request = disabled_transport

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8011)
