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
    conn.commit()
    conn.close()
