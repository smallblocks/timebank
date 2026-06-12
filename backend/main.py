"""
TimeBank — family tasks + earned screen time.
Kids complete tasks. Parents sign off. Minutes accrue in a bank.
Redemption notifies the parent to grant time in iOS Screen Time.

Single process: FastAPI serves the API and the static PWA.
SQLite at DATA_DIR/timebank.db (StartOS volume-friendly).
"""

import os
import json
import sqlite3
import secrets
import urllib.request
from datetime import datetime, date
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "timebank.db")
STATIC_DIR = os.environ.get(
    "STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static")
)

app = FastAPI(title="TimeBank")

# ---------------------------------------------------------------- db

SCHEMA = """
CREATE TABLE IF NOT EXISTS kids (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT NOT NULL DEFAULT '#2F7D4F',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY,
  kid_id INTEGER NOT NULL REFERENCES kids(id),
  title TEXT NOT NULL,
  minutes INTEGER NOT NULL,
  recurrence TEXT NOT NULL DEFAULT 'daily',   -- daily | weekly | once
  weekday INTEGER,                            -- 0=Mon..6=Sun, for weekly
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS completions (
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL REFERENCES tasks(id),
  kid_id INTEGER NOT NULL REFERENCES kids(id),
  day TEXT NOT NULL,                          -- YYYY-MM-DD
  status TEXT NOT NULL DEFAULT 'pending',     -- pending | approved | rejected
  completed_at TEXT NOT NULL,
  reviewed_at TEXT,
  UNIQUE(task_id, day)
);
CREATE TABLE IF NOT EXISTS redemptions (
  id INTEGER PRIMARY KEY,
  kid_id INTEGER NOT NULL REFERENCES kids(id),
  minutes INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',     -- pending | granted | denied
  requested_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY,
  kid_id INTEGER NOT NULL REFERENCES kids(id),
  delta INTEGER NOT NULL,                     -- minutes, + earn / - spend
  reason TEXT NOT NULL,
  ref_type TEXT,                              -- completion | redemption | manual
  ref_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return date.today().isoformat()


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


@app.on_event("startup")
def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        if get_setting(conn, "parent_pin") is None:
            set_setting(conn, "parent_pin", "1031")


# ---------------------------------------------------------------- helpers

def notify(conn, title: str, body: str):
    """Fire a notification to the parent via a self-hosted (or hosted) ntfy topic URL.
    Configured in Settings as e.g. https://ntfy.yourdomain.com/timebank
    Silently no-ops if unset or unreachable — the in-app queue is the source of truth."""
    url = get_setting(conn, "ntfy_url")
    if not url:
        return
    try:
        req = urllib.request.Request(
            url,
            data=body.encode(),
            headers={"Title": title, "Priority": "default", "Tags": "hourglass"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass


def balance(conn, kid_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta),0) AS b FROM ledger WHERE kid_id=?", (kid_id,)
    ).fetchone()
    return row["b"]


def require_parent(conn, token: str | None):
    if not token:
        raise HTTPException(401, "Parent sign-in required")
    row = conn.execute("SELECT 1 FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        raise HTTPException(401, "Parent sign-in required")


# ---------------------------------------------------------------- models

class KidIn(BaseModel):
    name: str
    color: str = "#2F7D4F"


class TaskIn(BaseModel):
    kid_id: int
    title: str
    minutes: int
    recurrence: str = "daily"
    weekday: int | None = None


class CompletionIn(BaseModel):
    task_id: int


class RedemptionIn(BaseModel):
    kid_id: int
    minutes: int


class ReviewIn(BaseModel):
    action: str  # approve/reject or grant/deny


class AuthIn(BaseModel):
    pin: str


class SettingsIn(BaseModel):
    parent_pin: str | None = None
    ntfy_url: str | None = None


class AdjustIn(BaseModel):
    kid_id: int
    delta: int
    reason: str = "Manual adjustment"


# ---------------------------------------------------------------- auth

@app.post("/api/auth")
def auth(body: AuthIn):
    with db() as conn:
        if body.pin != get_setting(conn, "parent_pin"):
            raise HTTPException(403, "Wrong PIN")
        token = secrets.token_urlsafe(24)
        conn.execute(
            "INSERT INTO sessions(token, created_at) VALUES(?,?)", (token, now())
        )
        return {"token": token}


# ---------------------------------------------------------------- kids

@app.get("/api/kids")
def list_kids():
    with db() as conn:
        kids = [dict(r) for r in conn.execute(
            "SELECT * FROM kids WHERE active=1 ORDER BY id")]
        for k in kids:
            k["balance"] = balance(conn, k["id"])
        return kids


@app.post("/api/kids")
def create_kid(body: KidIn, x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        cur = conn.execute(
            "INSERT INTO kids(name,color,created_at) VALUES(?,?,?)",
            (body.name.strip(), body.color, now()),
        )
        return {"id": cur.lastrowid}


@app.delete("/api/kids/{kid_id}")
def remove_kid(kid_id: int, x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        conn.execute("UPDATE kids SET active=0 WHERE id=?", (kid_id,))
        return {"ok": True}


@app.get("/api/kids/{kid_id}/today")
def kid_today(kid_id: int):
    """Kid home screen: today's tasks with status, plus bank balance."""
    wd = date.today().weekday()
    with db() as conn:
        kid = conn.execute(
            "SELECT * FROM kids WHERE id=? AND active=1", (kid_id,)).fetchone()
        if not kid:
            raise HTTPException(404, "Kid not found")
        tasks = conn.execute(
            """SELECT t.* FROM tasks t WHERE t.kid_id=? AND t.active=1 AND (
                 t.recurrence='daily'
                 OR (t.recurrence='weekly' AND t.weekday=?)
                 OR (t.recurrence='once' AND NOT EXISTS (
                      SELECT 1 FROM completions c
                      WHERE c.task_id=t.id AND c.status='approved'))
               ) ORDER BY t.id""",
            (kid_id, wd),
        ).fetchall()
        out = []
        for t in tasks:
            c = conn.execute(
                "SELECT * FROM completions WHERE task_id=? AND day=?",
                (t["id"], today()),
            ).fetchone()
            d = dict(t)
            d["status"] = c["status"] if c else "open"
            out.append(d)
        pending_red = conn.execute(
            "SELECT * FROM redemptions WHERE kid_id=? AND status='pending'",
            (kid_id,),
        ).fetchall()
        return {
            "kid": dict(kid),
            "balance": balance(conn, kid_id),
            "tasks": out,
            "pending_redemptions": [dict(r) for r in pending_red],
        }


# ---------------------------------------------------------------- tasks

@app.get("/api/tasks")
def list_tasks(x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        return [dict(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE active=1 ORDER BY kid_id, id")]


@app.post("/api/tasks")
def create_task(body: TaskIn, x_parent_token: str | None = Header(None)):
    if body.recurrence not in ("daily", "weekly", "once"):
        raise HTTPException(400, "recurrence must be daily, weekly, or once")
    if body.recurrence == "weekly" and body.weekday is None:
        raise HTTPException(400, "weekly tasks need a weekday")
    with db() as conn:
        require_parent(conn, x_parent_token)
        cur = conn.execute(
            "INSERT INTO tasks(kid_id,title,minutes,recurrence,weekday,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (body.kid_id, body.title.strip(), body.minutes,
             body.recurrence, body.weekday, now()),
        )
        return {"id": cur.lastrowid}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int, x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        conn.execute("UPDATE tasks SET active=0 WHERE id=?", (task_id,))
        return {"ok": True}


# ---------------------------------------------------------------- completions

@app.post("/api/completions")
def mark_done(body: CompletionIn):
    with db() as conn:
        t = conn.execute(
            "SELECT * FROM tasks WHERE id=? AND active=1", (body.task_id,)).fetchone()
        if not t:
            raise HTTPException(404, "Task not found")
        existing = conn.execute(
            "SELECT * FROM completions WHERE task_id=? AND day=?",
            (body.task_id, today()),
        ).fetchone()
        if existing:
            raise HTTPException(409, "Already marked for today")
        conn.execute(
            "INSERT INTO completions(task_id,kid_id,day,completed_at) VALUES(?,?,?,?)",
            (t["id"], t["kid_id"], today(), now()),
        )
        kid = conn.execute(
            "SELECT name FROM kids WHERE id=?", (t["kid_id"],)).fetchone()
        notify(conn, "TimeBank: sign-off needed",
               f"{kid['name']} finished “{t['title']}” (+{t['minutes']} min)")
        return {"ok": True}


@app.get("/api/approvals")
def approvals(x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        comps = conn.execute(
            """SELECT c.id, c.day, c.completed_at, t.title, t.minutes,
                      k.name AS kid_name, k.id AS kid_id, k.color
               FROM completions c
               JOIN tasks t ON t.id=c.task_id
               JOIN kids k ON k.id=c.kid_id
               WHERE c.status='pending' ORDER BY c.completed_at"""
        ).fetchall()
        reds = conn.execute(
            """SELECT r.id, r.minutes, r.requested_at,
                      k.name AS kid_name, k.id AS kid_id, k.color
               FROM redemptions r JOIN kids k ON k.id=r.kid_id
               WHERE r.status='pending' ORDER BY r.requested_at"""
        ).fetchall()
        out_reds = []
        for r in reds:
            d = dict(r)
            d["balance"] = balance(conn, r["kid_id"])
            out_reds.append(d)
        return {"completions": [dict(c) for c in comps], "redemptions": out_reds}


@app.post("/api/completions/{comp_id}/review")
def review_completion(comp_id: int, body: ReviewIn,
                      x_parent_token: str | None = Header(None)):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be approve or reject")
    with db() as conn:
        require_parent(conn, x_parent_token)
        c = conn.execute(
            "SELECT * FROM completions WHERE id=? AND status='pending'",
            (comp_id,)).fetchone()
        if not c:
            raise HTTPException(404, "Not pending")
        status = "approved" if body.action == "approve" else "rejected"
        conn.execute(
            "UPDATE completions SET status=?, reviewed_at=? WHERE id=?",
            (status, now(), comp_id),
        )
        if status == "approved":
            t = conn.execute(
                "SELECT * FROM tasks WHERE id=?", (c["task_id"],)).fetchone()
            conn.execute(
                "INSERT INTO ledger(kid_id,delta,reason,ref_type,ref_id,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (c["kid_id"], t["minutes"], f"Earned: {t['title']}",
                 "completion", comp_id, now()),
            )
        return {"ok": True}


# ---------------------------------------------------------------- redemptions

@app.post("/api/redemptions")
def request_time(body: RedemptionIn):
    with db() as conn:
        if body.minutes <= 0:
            raise HTTPException(400, "Minutes must be positive")
        if body.minutes > balance(conn, body.kid_id):
            raise HTTPException(400, "Not enough minutes in the bank")
        conn.execute(
            "INSERT INTO redemptions(kid_id,minutes,requested_at) VALUES(?,?,?)",
            (body.kid_id, body.minutes, now()),
        )
        kid = conn.execute(
            "SELECT name FROM kids WHERE id=?", (body.kid_id,)).fetchone()
        notify(conn, "TimeBank: time requested",
               f"{kid['name']} wants to spend {body.minutes} min of screen time")
        return {"ok": True}


@app.post("/api/redemptions/{red_id}/review")
def review_redemption(red_id: int, body: ReviewIn,
                      x_parent_token: str | None = Header(None)):
    if body.action not in ("grant", "deny"):
        raise HTTPException(400, "action must be grant or deny")
    with db() as conn:
        require_parent(conn, x_parent_token)
        r = conn.execute(
            "SELECT * FROM redemptions WHERE id=? AND status='pending'",
            (red_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Not pending")
        status = "granted" if body.action == "grant" else "denied"
        conn.execute(
            "UPDATE redemptions SET status=?, resolved_at=? WHERE id=?",
            (status, now(), red_id),
        )
        kid = conn.execute(
            "SELECT name FROM kids WHERE id=?", (r["kid_id"],)).fetchone()
        if status == "granted":
            conn.execute(
                "INSERT INTO ledger(kid_id,delta,reason,ref_type,ref_id,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (r["kid_id"], -r["minutes"], "Spent: screen time",
                 "redemption", red_id, now()),
            )
            notify(conn, "TimeBank: grant time now",
                   f"Open Screen Time and give {kid['name']} "
                   f"{r['minutes']} minutes")
        return {"ok": True, "status": status, "kid": kid["name"],
                "minutes": r["minutes"]}


# ---------------------------------------------------------------- ledger / settings

@app.get("/api/kids/{kid_id}/ledger")
def kid_ledger(kid_id: int):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM ledger WHERE kid_id=? ORDER BY id DESC LIMIT 100",
            (kid_id,)).fetchall()
        return {"balance": balance(conn, kid_id),
                "entries": [dict(r) for r in rows]}


@app.post("/api/adjust")
def adjust(body: AdjustIn, x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        conn.execute(
            "INSERT INTO ledger(kid_id,delta,reason,ref_type,created_at) "
            "VALUES(?,?,?,?,?)",
            (body.kid_id, body.delta, body.reason, "manual", now()),
        )
        return {"ok": True, "balance": balance(conn, body.kid_id)}


@app.post("/api/admin/reset-pin")
def reset_pin(request: Request):
    """Reset parent PIN to 1031 and clear all sessions.

    Called by the StartOS 'Reset Parent PIN' action, which fetches
    http://127.0.0.1/api/admin/reset-pin from inside the host. Loopback
    only: this endpoint is unauthenticated by design (it IS the recovery
    path for a lost PIN), so it must never be reachable through the
    public web interface — otherwise a kid on the iPad could reset the
    PIN and approve their own screen time.
    """
    client = request.client.host if request.client else ""
    if client not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Loopback only")
    with db() as conn:
        set_setting(conn, "parent_pin", "1031")
        conn.execute("DELETE FROM sessions")
    return {"ok": True, "pin": "1031"}


@app.get("/api/settings")
def get_settings(x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        return {"ntfy_url": get_setting(conn, "ntfy_url", "")}


@app.put("/api/settings")
def put_settings(body: SettingsIn, x_parent_token: str | None = Header(None)):
    with db() as conn:
        require_parent(conn, x_parent_token)
        if body.parent_pin:
            set_setting(conn, "parent_pin", body.parent_pin)
        if body.ntfy_url is not None:
            set_setting(conn, "ntfy_url", body.ntfy_url.strip())
        return {"ok": True}


# ---------------------------------------------------------------- static / PWA

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.webmanifest"),
                        media_type="application/manifest+json")


@app.get("/sw.js")
def sw():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"),
                        media_type="application/javascript")


@app.get("/{full_path:path}")
def spa(full_path: str, request: Request):
    fp = os.path.join(STATIC_DIR, full_path)
    if full_path and os.path.isfile(fp):
        return FileResponse(fp)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
