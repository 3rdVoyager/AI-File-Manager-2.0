import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.database import db as database
from backend.database.db import log_activity
from backend.models.schemas import ReportSaveRequest
from backend.utils.paths import app_data_dir

router = APIRouter(prefix="/reports", tags=["reports"])


def _reports_dir() -> Path:
    d = app_data_dir() / "reports"
    d.mkdir(exist_ok=True)
    return d


@router.get("")
def list_reports():
    reports = []
    for f in sorted(_reports_dir().glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "name": f.stem,
                "filename": f.name,
                "saved_at": data.get("saved_at", ""),
                "file_count": data.get("file_count", 0),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return {"reports": reports}


@router.post("")
def save_report(body: ReportSaveRequest):
    files = database.fetch_all(
        """SELECT f.*, a.summary, a.category, a.action, a.importance, a.tags_json, a.project
           FROM files f LEFT JOIN analyses a ON a.file_id = f.id"""
    )
    data = {
        "name": body.name,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "files": files,
    }
    path = _reports_dir() / f"{body.name}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log_activity("report_saved", f"Report saved: {body.name}.json")
    return {"saved": True, "name": body.name, "file_count": len(files)}
