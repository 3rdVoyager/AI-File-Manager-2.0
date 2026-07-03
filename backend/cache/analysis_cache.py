"""Analysis cache with mtime/size/model invalidation."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from backend.database import db as database


def path_hash(path: str) -> str:
    return hashlib.sha256(path.lower().encode()).hexdigest()


def get_cached(path: str, modified_time: float, size_bytes: int, content_hash: str, model: str) -> Optional[dict]:
    ph = path_hash(path)
    row = database.fetch_one(
        "SELECT * FROM file_cache WHERE path_hash = ?", (ph,)
    )
    if not row:
        return None
    if (row["modified_time"] != modified_time or row["size_bytes"] != size_bytes
            or row["content_hash"] != content_hash or row["model_used"] != model):
        return None
    try:
        return json.loads(row["analysis_json"])
    except json.JSONDecodeError:
        return None


def set_cached(path: str, filename: str, modified_time: float, size_bytes: int,
               content_hash: str, model: str, analysis: dict) -> None:
    ph = path_hash(path)
    now = datetime.now(timezone.utc).isoformat()
    with database.db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO file_cache
               (path_hash, file_path, filename, modified_time, size_bytes, content_hash, model_used, analysis_json, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ph, path, filename, modified_time, size_bytes, content_hash, model, json.dumps(analysis), now),
        )


def purge_paths(paths: list[str]) -> None:
    if not paths:
        return
    hashes = [path_hash(p) for p in paths]
    placeholders = ",".join("?" * len(hashes))
    with database.db() as conn:
        conn.execute(f"DELETE FROM file_cache WHERE path_hash IN ({placeholders})", tuple(hashes))
