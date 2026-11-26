"""SQLite audit log: who called what, through the gateway, and how it went."""
import os
import sqlite3
import threading
import time

_LOCK = threading.Lock()
_DB = None


def init_db(path):
    global _DB
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _DB = sqlite3.connect(path, check_same_thread=False)
    _DB.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            client_id TEXT NOT NULL,
            method TEXT NOT NULL,
            tool TEXT,
            status TEXT NOT NULL,
            duration_ms INTEGER NOT NULL
        )"""
    )
    _DB.commit()


def log(client_id, method, tool, status, duration_ms):
    if _DB is None:
        return
    with _LOCK:
        _DB.execute(
            "INSERT INTO audit_log (ts, client_id, method, tool, status, duration_ms)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), client_id, method, tool, status, duration_ms),
        )
        _DB.commit()


def count():
    if _DB is None:
        return 0
    with _LOCK:
        return _DB.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
