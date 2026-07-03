"""Dashboard aggregation service."""

import json
from typing import Any

from backend.database import db as database
from backend.filesystem.service import human_size
from backend.models.domain import TRASH_CONFIDENCE_TIERS


def _empty_dashboard() -> dict[str, Any]:
    return {
        "empty": True,
        "files_analyzed": 0,
        "files_delta": 0,
        "projects_detected": 0,
        "projects_delta": 0,
        "duplicate_files": 0,
        "duplicate_bytes": 0,
        "trash_candidates": 0,
        "trash_bytes": 0,
        "avg_importance": 0,
        "importance_label": "N/A",
        "storage": {
            "total_bytes": 0,
            "total_human": "0 B",
            "used_bytes": 0,
            "used_human": "0 B",
            "recommended_delete_bytes": 0,
            "recommended_delete_human": "0 B",
            "duplicate_bytes": 0,
            "duplicate_human": "0 B",
            "other_bytes": 0,
            "other_human": "0 B",
        },
    }


def get_dashboard() -> dict[str, Any]:
    high_confidence = TRASH_CONFIDENCE_TIERS["high"]
    stats = database.fetch_one(
        """SELECT
            COUNT(DISTINCT f.id) as files_analyzed,
            COALESCE(SUM(f.size_bytes), 0) as total_bytes,
            COUNT(DISTINCT CASE WHEN a.action = 'Delete' AND a.confidence >= ? THEN f.id END) as trash_candidates,
            COALESCE(SUM(CASE WHEN a.action = 'Delete' AND a.confidence >= ? THEN f.size_bytes ELSE 0 END), 0) as trash_bytes,
            COALESCE(AVG(a.importance), 0) as avg_importance
        FROM files f
        LEFT JOIN analyses a ON a.file_id = f.id""",
        (high_confidence, high_confidence),
    )
    if not stats or stats["files_analyzed"] == 0:
        return _empty_dashboard()

    dup = database.fetch_one(
        """SELECT COALESCE(SUM(file_count), 0) as cnt, COALESCE(SUM(total_bytes), 0) as bytes
           FROM duplicate_groups"""
    )
    projects = database.fetch_one("SELECT COUNT(DISTINCT name) as cnt FROM projects")

    prev = database.fetch_one(
        """SELECT files_found FROM scans WHERE status = 'completed'
           ORDER BY completed_at DESC LIMIT 1 OFFSET 1"""
    )
    current_scan = database.fetch_one(
        "SELECT files_found FROM scans WHERE status = 'completed' ORDER BY completed_at DESC LIMIT 1"
    )
    files_delta = 0
    if prev and current_scan:
        files_delta = current_scan["files_found"] - prev["files_found"]

    total = stats["total_bytes"] or 0
    trash_bytes = stats["trash_bytes"] or 0
    dup_bytes = dup["bytes"] if dup else 0
    used = total
    other = max(0, total - trash_bytes - dup_bytes)

    avg = round(stats["avg_importance"] or 0, 1)
    if avg >= 7:
        label = "Good"
    elif avg >= 5:
        label = "Fair"
    else:
        label = "Low"

    return {
        "empty": False,
        "files_analyzed": stats["files_analyzed"],
        "files_delta": files_delta,
        "projects_detected": projects["cnt"] if projects else 0,
        "projects_delta": 0,
        "duplicate_files": dup["cnt"] if dup else 0,
        "duplicate_bytes": dup_bytes,
        "duplicate_human": human_size(dup_bytes),
        "trash_candidates": stats["trash_candidates"] or 0,
        "trash_bytes": trash_bytes,
        "trash_human": human_size(trash_bytes),
        "avg_importance": avg,
        "importance_label": label,
        "storage": {
            "total_bytes": total,
            "total_human": human_size(total),
            "used_bytes": used,
            "used_human": human_size(used),
            "recommended_delete_bytes": trash_bytes,
            "recommended_delete_human": human_size(trash_bytes),
            "duplicate_bytes": dup_bytes,
            "duplicate_human": human_size(dup_bytes),
            "other_bytes": other,
            "other_human": human_size(other),
        },
    }


def get_categories() -> dict[str, Any]:
    rows = database.fetch_all(
        """SELECT a.category, COUNT(*) as file_count,
                  COALESCE(SUM(f.size_bytes), 0) as total_bytes
           FROM analyses a
           JOIN files f ON f.id = a.file_id
           WHERE a.category != ''
           GROUP BY a.category
           ORDER BY total_bytes DESC"""
    )
    total_bytes = sum(r["total_bytes"] for r in rows) or 1
    total_files = sum(r["file_count"] for r in rows) or 1
    categories = []
    for r in rows:
        categories.append({
            "category": r["category"],
            "files": r["file_count"],
            "size_bytes": r["total_bytes"],
            "size_human": human_size(r["total_bytes"]),
            "percent_size": round(100 * r["total_bytes"] / total_bytes, 1),
            "percent_files": round(100 * r["file_count"] / total_files, 1),
        })
    return {"categories": categories, "total_bytes": total_bytes, "total_files": total_files}


def get_activity(limit: int = 10) -> list[dict]:
    return database.fetch_all(
        "SELECT event_type, description, created_at FROM activity_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )


def get_recommendations() -> list[dict]:
    rows = database.fetch_all(
        "SELECT rec_type, title, description, savings_bytes, file_count FROM recommendations ORDER BY savings_bytes DESC LIMIT 10"
    )
    for r in rows:
        r["savings_human"] = human_size(r["savings_bytes"])
    return rows


def get_scans(limit: int = 20) -> list[dict]:
    rows = database.fetch_all(
        """SELECT id, name, root_path, files_found, total_bytes, status, started_at, completed_at
           FROM scans ORDER BY started_at DESC LIMIT ?""",
        (limit,),
    )
    for r in rows:
        r["size_human"] = human_size(r["total_bytes"] or 0)
    return rows
