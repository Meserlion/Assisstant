import sqlite3
import os
from config import settings


_db_dir_ready = False


def get_db():
    global _db_dir_ready
    if not _db_dir_ready:
        os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
        _db_dir_ready = True
    conn = sqlite3.connect(settings.sqlite_db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    # WAL lets readers and writers run concurrently; busy_timeout makes a blocked
    # writer wait instead of raising "database is locked" immediately.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            summary TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            audio_path TEXT
        )
    """)
    # Migrate existing databases — ignore if columns already exist
    for col, definition in [("pinned", "INTEGER NOT NULL DEFAULT 0"), ("audio_path", "TEXT"), ("archived", "INTEGER NOT NULL DEFAULT 0"), ("color", "TEXT"), ("notebook", "TEXT NOT NULL DEFAULT 'default'")]:
        try:
            conn.execute(f"ALTER TABLE notes ADD COLUMN {col} {definition}")
        except Exception:
            pass
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
            created_at TEXT NOT NULL,
            recurrence TEXT NOT NULL DEFAULT 'none'
        )
    """)
    try:
        conn.execute("ALTER TABLE reminders ADD COLUMN recurrence TEXT NOT NULL DEFAULT 'none'")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_tokens (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            token_json TEXT NOT NULL
        )
    """)
    # Indexes for the common feed query (archived + pinned + created_at)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_list ON notes(archived, pinned DESC, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at)")
    conn.commit()
    conn.close()
