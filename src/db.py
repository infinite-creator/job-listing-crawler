import os
import sqlite3
from typing import Iterable

def connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT,
            salary TEXT,
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

def is_seen(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone()
    return row is not None

def upsert_job(conn: sqlite3.Connection, url: str, title: str, company: str | None, salary: str | None) -> None:
    conn.execute("""
        INSERT INTO jobs (url, title, company, salary)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
          title = excluded.title,
          company = COALESCE(excluded.company, jobs.company),
          salary = COALESCE(excluded.salary, jobs.salary),
          last_seen_at = datetime('now')
    """, (url, title, company, salary))
    conn.commit()

def touch_seen(conn: sqlite3.Connection, urls: Iterable[str]) -> None:
    conn.executemany(
        "UPDATE jobs SET last_seen_at = datetime('now') WHERE url = ?",
        [(u,) for u in urls],
    )
    conn.commit()
