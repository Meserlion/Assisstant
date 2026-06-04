import sqlite3
import os
from config import settings


def get_db():
    os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            summary TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id TEXT PRIMARY KEY,
            subscription_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            google_event_id TEXT,
            sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            token_json TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
