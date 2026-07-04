"""File operations service."""

import json
import os
import re
from pathlib import Path
from typing import Any

from backend.cache.analysis_cache import purge_paths
from backend.database import db as database
from backend.database.db import log_activity
from backend.filesystem import service as fs
from backend.services.duplicate_service import rebuild_duplicates
from backend.services.recommendations_service import regenerate_recommendations

DOCUMENT_RENAME_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".odt", ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv", ".pages", ".numbers", ".key",
    ".py", ".js", ".ts", ".html", ".css", ".c", ".cpp", ".h", ".java", ".go",
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


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


def _valid_suggested_filename(current: str, suggested: str, extension: str) -> str:
    name = suggested.strip().strip(". ")
    if not name or INVALID_FILENAME_CHARS.search(name):
        return ""
    if name in {".", ".."} or Path(name).name != name:
        return ""
    suffix = extension.lower()
    if suffix and Path(name).suffix.lower() != suffix:
        name = f"{Path(name).stem}{suffix}"
    if name.lower() == current.lower():
        return ""
    return name


def list_rename_suggestions() -> dict[str, Any]:
    rows = database.fetch_all(
        """SELECT f.path, f.filename, f.extension, f.size_bytes, a.summary,
                  a.suggested_filename, a.rename_reason, a.rename_confidence
           FROM files f
           JOIN analyses a ON a.file_id = f.id
           WHERE a.suggested_filename != ''
             AND a.rename_confidence >= 30
           ORDER BY a.rename_confidence DESC, f.filename ASC"""
    )
    suggestions = []
    for row in rows:
        if row["extension"].lower() not in DOCUMENT_RENAME_EXTENSIONS:
            continue
        suggested = _valid_suggested_filename(row["filename"], row["suggested_filename"], row["extension"])
        if not suggested:
            continue
        target_path = str((Path(row["path"]).parent / suggested).resolve())
        suggestions.append({
            "path": row["path"],
            "filename": row["filename"],
            "suggested_filename": suggested,
            "target_path": target_path,
            "summary": row["summary"],
            "rename_reason": row["rename_reason"],
            "rename_confidence": row["rename_confidence"],
            "size_human": fs.human_size(row["size_bytes"]),
        })
    return {"suggestions": suggestions, "count": len(suggestions)}


def apply_rename_suggestions(paths: list[str]) -> dict[str, Any]:
    results = []
    renamed: list[tuple[str, str]] = []

    for raw_path in paths:
        try:
            norm = fs.normalize_path(raw_path)
            row = database.fetch_one(
                """SELECT f.id, f.path, f.filename, f.extension, a.suggested_filename
                   FROM files f JOIN analyses a ON a.file_id = f.id
                   WHERE f.path = ?""",
                (norm,),
            )
            if not row:
                raise FileNotFoundError("File is not in the scan index.")
            if row["extension"].lower() not in DOCUMENT_RENAME_EXTENSIONS:
                raise ValueError("Only document files can be renamed by this tool.")
            suggested = _valid_suggested_filename(row["filename"], row["suggested_filename"], row["extension"])
            if not suggested:
                raise ValueError("No valid rename suggestion is available.")

            source = Path(row["path"])
            target = source.with_name(suggested)
            if target.exists():
                raise FileExistsError(f"Target already exists: {target.name}")
            source.rename(target)

            target_norm = str(target.resolve())
            with database.db() as conn:
                conn.execute(
                    """UPDATE files
                       SET path = ?, filename = ?, extension = ?
                       WHERE id = ?""",
                    (target_norm, target.name, target.suffix.lower(), row["id"]),
                )
                conn.execute(
                    """UPDATE analyses
                       SET suggested_filename = '', rename_reason = '', rename_confidence = 0
                       WHERE file_id = ?""",
                    (row["id"],),
                )
            purge_paths([norm])
            log_activity("file_renamed", f"Renamed {row['filename']} to {target.name}", {
                "from": norm,
                "to": target_norm,
            })
            renamed.append((norm, target_norm))
            results.append({"path": norm, "new_path": target_norm, "success": True})
        except Exception as e:
            results.append({"path": raw_path, "success": False, "error": str(e)})

    return {"results": results, "renamed_count": len(renamed)}


def get_duplicates() -> list[dict]:
    rebuild_duplicates()
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


def _completed_scan_roots() -> list[str]:
    rows = database.fetch_all(
        "SELECT DISTINCT root_path FROM scans WHERE status = 'completed' ORDER BY root_path"
    )
    roots = []
    for row in rows:
        try:
            root = fs.normalize_path(row["root_path"])
        except OSError:
            continue
        if Path(root).is_dir():
            roots.append(root)
    return roots


def _is_inside_scan_root(path: str, roots: list[str]) -> bool:
    candidate = Path(path)
    for root in roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return candidate != Path(root)
    return False


def list_empty_directories(path: Optional[str] = None) -> dict[str, Any]:
    if path:
        try:
            roots = [fs.normalize_path(path)]
        except OSError:
            roots = []
    else:
        roots = _completed_scan_roots()
    
    empty_dirs: dict[str, dict[str, Any]] = {}

    for root in roots:
        if not Path(root).is_dir():
            continue
        for dirpath, _, _ in os.walk(root):
            path_obj = Path(dirpath)
            if path_obj == Path(root) or path_obj.is_symlink():
                continue
            try:
                next(path_obj.iterdir())
            except StopIteration:
                norm = str(path_obj.resolve())
                empty_dirs[norm] = {
                    "path": norm,
                    "name": path_obj.name,
                    "root_path": root,
                }
            except (OSError, PermissionError):
                continue

    directories = sorted(empty_dirs.values(), key=lambda d: d["path"].lower())
    return {"directories": directories, "count": len(directories)}


def delete_empty_directories(paths: list[str]) -> dict[str, Any]:
    results = []
    removed = []

    normalized = []
    for path in paths:
        try:
            normalized.append(fs.normalize_path(path))
        except OSError as e:
            results.append({"path": path, "success": False, "error": str(e)})

    for norm in sorted(set(normalized), key=lambda p: len(Path(p).parts), reverse=True):
        path = Path(norm)
        try:
            if path.is_symlink():
                raise ValueError("Refusing to remove symbolic links.")
            if not path.is_dir():
                raise FileNotFoundError("Directory not found.")
            
            # Attempt to remove - os.rmdir only works if empty
            path.rmdir()
            removed.append(norm)
            log_activity("empty_directory_removed", f"Removed empty folder {path.name}", {"path": norm})
            results.append({"path": norm, "success": True})
        except OSError as e:
            # Usually means not empty or permission denied
            results.append({"path": norm, "success": False, "error": "Folder is not empty or permission denied."})
        except Exception as e:
            results.append({"path": norm, "success": False, "error": str(e)})

    return {"results": results, "removed_count": len(removed)}
