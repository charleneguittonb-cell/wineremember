"""SQLite access (standard library, no ORM)."""
import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tokens (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    producer        TEXT,
    vintage         INTEGER,
    appellation     TEXT,
    region          TEXT,
    country         TEXT,
    color           TEXT,
    grapes          TEXT NOT NULL DEFAULT '[]',   -- JSON list
    classification  TEXT,
    rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
    notes           TEXT,
    tasted_on       TEXT,
    occasion        TEXT,
    match_key       TEXT NOT NULL,               -- normalised producer+name
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Several photos per bottle: front label (position 0), back label, details...
CREATE TABLE IF NOT EXISTS photos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id   INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    file      TEXT NOT NULL,                     -- path relative to uploads/
    position  INTEGER NOT NULL DEFAULT 0
);

-- The user's reference sites (guides, producer sites, vintage charts...)
CREATE TABLE IF NOT EXISTS sources (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url        TEXT NOT NULL,
    label      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, url)
);

-- Links sent for a specific wine (technical sheet, estate page, article...)
CREATE TABLE IF NOT EXISTS wine_links (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id    INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    url        TEXT NOT NULL,
    label      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Research dossier found on the internet for a wine (JSON)
CREATE TABLE IF NOT EXISTS dossiers (
    wine_id    INTEGER PRIMARY KEY REFERENCES wines(id) ON DELETE CASCADE,
    data       TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wines_user ON wines(user_id);
CREATE INDEX IF NOT EXISTS idx_wines_match ON wines(user_id, match_key);
CREATE INDEX IF NOT EXISTS idx_photos_wine ON photos(wine_id, position);
"""


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def wine_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["grapes"] = json.loads(d.get("grapes") or "[]")
    d["photo_count"] = d.get("photo_count") or 0
    d["has_photo"] = d["photo_count"] > 0
    d.pop("match_key", None)
    d.pop("user_id", None)
    return d
