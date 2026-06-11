"""TimeBank — stub app for s9pk packaging validation.

Replace this file with the real application.
"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

DATA_DIR = os.environ.get("DATA_DIR", "/data")

app = FastAPI(title="TimeBank")


@app.get("/api/kids")
async def list_kids():
    """Health-check endpoint. Returns empty list on fresh install."""
    return []


@app.post("/api/admin/reset-pin")
async def reset_pin():
    """Reset parent PIN to 1031 and clear sessions. Called by StartOS action."""
    import sqlite3

    db_path = os.path.join(DATA_DIR, "timebank.db")
    if not os.path.exists(db_path):
        return {"detail": "Database not initialized yet"}
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE settings SET parent_pin = '1031'")
        conn.execute("DELETE FROM sessions")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "pin": "1031"}


# Serve static PWA files at root (after API routes)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
