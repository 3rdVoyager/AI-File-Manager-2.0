"""SQLite connection and schema initialization."""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from backend.utils.paths import db_path
from backend.utils.time import utc_now

_local = threading.local()
SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        _local.conn = conn
    return _local.conn


@contextmanager
def db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    schema = SCHEMA_FILE.read_text(encoding="utf-8")
    with db() as conn:
        conn.executescript(schema)
        _ensure_column(conn, "analyses", "suggested_filename", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "analyses", "rename_reason", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "analyses", "rename_confidence", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "scans", "scan_type", "TEXT NOT NULL DEFAULT 'ai'")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def close_db() -> None:
    if hasattr(_local, "conn") and _local.conn is not None:
        try:
            _local.conn.close()
        except Exception:
            pass
        _local.conn = None


def clear_all_data() -> None:
    """Remove all rows while keeping schema — safe while DB file is open (Windows)."""
    tables = (
        "duplicate_members",
        "file_projects",
        "scan_files",
        "analyses",
        "files",
        "duplicate_groups",
        "projects",
        "recommendations",
        "activity_log",
        "scans",
        "file_cache",
    )
    with db() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in tables:
            conn.execute(f"DELETE FROM {table}")
        conn.execute("PRAGMA foreign_keys = ON")


def log_activity(event_type: str, description: str, metadata: Optional[dict] = None) -> None:
    import json
    with db() as conn:
        conn.execute(
            "INSERT INTO activity_log (event_type, description, metadata_json, created_at) VALUES (?, ?, ?, ?)",
            (event_type, description, json.dumps(metadata or {}), utc_now()),
        )


def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def fetch_one(query: str, params: tuple = ()) -> Optional[dict[str, Any]]:
    with db() as conn:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None


def execute(query: str, params: tuple = ()) -> int:
    with db() as conn:
        cur = conn.execute(query, params)
        return cur.lastrowid or 0
