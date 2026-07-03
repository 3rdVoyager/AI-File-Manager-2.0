"""File operations service."""

import json
from pathlib import Path
from typing import Any

from backend.cache.analysis_cache import purge_paths
from backend.database import db as database
from backend.database.db import log_activity
from backend.filesystem import service as fs
from backend.services.duplicate_service import rebuild_duplicates
from backend.services.recommendations_service import regenerate_recommendations


def list_files(page: int = 1, per_page: int = 50, sort: str = "filename",
               order: str = "asc", search: str = "", category: str = "",
               action: str = "", min_confidence: int | None = None) -> dict[str, Any]:
    offset = (page - 1) * per_page
    where, params = [], []

    if search:
        where.append("(f.filename LIKE ? OR f.path LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if category:
        where.append("a.category = ?")
        params.append(category)
    if action:
        where.append("a.action = ?")
        params.append(action)
    if min_confidence is not None:
        where.append("a.confidence >= ?")
        params.append(min_confidence)

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    valid_sorts = {"filename", "size_bytes", "modified_at", "importance", "category", "action", "confidence"}
    col = sort if sort in valid_sorts else "filename"
    if col == "importance":
        col = "a.importance"
    elif col == "category":
        col = "a.category"
    elif col == "action":
        col = "a.action"
    elif col == "confidence":
        col = "a.confidence"
    else:
        col = f"f.{col}"
    direction = "DESC" if order.lower() == "desc" else "ASC"

    total = database.fetch_one(
        f"SELECT COUNT(*) as cnt FROM files f LEFT JOIN analyses a ON a.file_id=f.id {clause}",
        tuple(params),
    )["cnt"]

    rows = database.fetch_all(
        f"""SELECT f.id, f.path, f.filename, f.size_bytes, f.extension, f.modified_at, f.content_hash,
                   a.summary, a.category, a.action, a.importance, a.confidence, a.lifecycle, a.project,
                   a.reasoning, a.tags_json
            FROM files f LEFT JOIN analyses a ON a.file_id = f.id
            {clause} ORDER BY {col} {direction} LIMIT ? OFFSET ?""",
        tuple(params) + (per_page, offset),
    )
    for r in rows:
        r["size_human"] = fs.human_size(r["size_bytes"])
        try:
            r["tags"] = json.loads(r.pop("tags_json", "[]"))
        except (json.JSONDecodeError, TypeError):
            r["tags"] = []

    return {"files": rows, "total": total, "page": page, "per_page": per_page}


def get_duplicates() -> list[dict]:
    groups = database.fetch_all(
        """SELECT dg.id, dg.content_hash, dg.file_count, dg.total_bytes
           FROM duplicate_groups dg ORDER BY dg.total_bytes DESC"""
    )
    for g in groups:
        g["size_human"] = fs.human_size(g["total_bytes"])
        g["files"] = database.fetch_all(
            """SELECT f.path, f.filename, f.size_bytes, f.modified_at, f.content_hash
               FROM files f
               JOIN duplicate_members dm ON dm.file_id = f.id
               WHERE dm.group_id = ?
               ORDER BY f.modified_at ASC, f.path ASC""",
            (g["id"],),
        )
        for f in g["files"]:
            f["size_human"] = fs.human_size(f["size_bytes"])
    return groups


def get_projects() -> list[dict]:
    rows = database.fetch_all(
        """SELECT p.name, COUNT(fp.file_id) as file_count, COALESCE(SUM(f.size_bytes), 0) as total_bytes
           FROM projects p
           JOIN file_projects fp ON fp.project_id = p.id
           JOIN files f ON f.id = fp.file_id
           GROUP BY p.name ORDER BY total_bytes DESC"""
    )
    for r in rows:
        r["size_human"] = fs.human_size(r["total_bytes"])
    return rows


def _resolve_open_path(path: str) -> str:
    norm = fs.normalize_path(path)
    if Path(norm).exists():
        return norm

    requested = str(Path(path))
    suffix = requested.replace("/", "\\").lower()
    filename = Path(path).name
    row = database.fetch_one(
        """SELECT path FROM files
           WHERE LOWER(filename) = LOWER(?)
           AND REPLACE(LOWER(path), '/', '\\') LIKE ?
           ORDER BY modified_at DESC LIMIT 1""",
        (filename, f"%{suffix}"),
    )
    if row and Path(row["path"]).exists():
        return row["path"]

    row = database.fetch_one(
        """SELECT path FROM files
           WHERE LOWER(filename) = LOWER(?)
           ORDER BY modified_at DESC LIMIT 1""",
        (filename,),
    )
    if row and Path(row["path"]).exists():
        return row["path"]

    return norm


def open_file(path: str) -> dict[str, Any]:
    norm = _resolve_open_path(path)
    fs.open_with_default_app(norm)
    log_activity("file_opened", f"Opened {Path(norm).name}", {"path": norm})
    return {"success": True, "path": norm, "filename": Path(norm).name}


def delete_preview(paths: list[str]) -> dict:
    files = []
    total = 0
    for path in paths:
        norm = fs.normalize_path(path)
        row = database.fetch_one(
            """SELECT f.path, f.filename, f.size_bytes, a.reasoning, a.action
               FROM files f LEFT JOIN analyses a ON a.file_id = f.id WHERE f.path = ?""",
            (norm,),
        )
        if row:
            total += row["size_bytes"]
            files.append({
                "path": row["path"],
                "filename": row["filename"],
                "size_human": fs.human_size(row["size_bytes"]),
                "reasoning": row["reasoning"] or "User selected for deletion",
            })
    return {"files": files, "total_bytes": total, "total_human": fs.human_size(total)}


def execute_delete(paths: list[str], dry_run: bool = False) -> dict:
    results = []
    deleted_paths: list[str] = []
    freed_bytes = 0

    for path in paths:
        norm = fs.normalize_path(path)
        if dry_run:
            results.append({"path": norm, "success": True, "dry_run": True})
            continue
        row = database.fetch_one("SELECT size_bytes FROM files WHERE path = ?", (norm,))
        try:
            name = Path(norm).name
            fs.delete_to_trash(norm)
            deleted_paths.append(norm)
            if row:
                freed_bytes += row["size_bytes"]
            log_activity("file_deleted", f"Deleted {name} (sent to Recycle Bin)", {"path": norm})
            results.append({"path": norm, "success": True})
        except Exception as e:
            results.append({"path": norm, "success": False, "error": str(e)})

    if deleted_paths and not dry_run:
        placeholders = ",".join("?" * len(deleted_paths))
        database.execute(f"DELETE FROM files WHERE path IN ({placeholders})", tuple(deleted_paths))
        purge_paths(deleted_paths)
        rebuild_duplicates()
        regenerate_recommendations()

    return {
        "results": results,
        "deleted_count": len(deleted_paths),
        "freed_bytes": freed_bytes,
        "freed_human": fs.human_size(freed_bytes),
    }
