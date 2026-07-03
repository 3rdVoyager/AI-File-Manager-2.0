from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.models.schemas import ScanRequest
from backend.scanner import pipeline
from backend.filesystem import service as fs
from backend.services import dashboard_service
from backend.scanner.token_budget import estimate_ai_calls, model_for_scan
from config.settings import load_settings

router = APIRouter(tags=["scan"])


@router.post("/scan")
def start_scan(body: ScanRequest):
    try:
        scan_id = pipeline.start_scan(body.path, body.name)
        return {"scan_id": scan_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/scan/estimate")
def scan_estimate(path: str = Query(...)):
    root = fs.normalize_path(path)
    if not Path(root).is_dir():
        raise HTTPException(400, f"Not a directory: {path}")
    try:
        count = sum(1 for _ in fs.traverse_directory(root))
    except PermissionError:
        raise HTTPException(403, "Permission denied accessing this folder.")
    est = estimate_ai_calls(count)
    settings = load_settings()
    return {
        **est,
        "model": model_for_scan(count, settings.model),
        "user_model": settings.model,
    }


@router.get("/scan/{scan_id}")
def scan_status(scan_id: int):
    result = pipeline.get_scan_status(scan_id)
    if result.get("error") == "Scan not found":
        raise HTTPException(404, "Scan not found")
    return result


@router.post("/scan/{scan_id}/cancel")
def cancel_scan(scan_id: int):
    if pipeline.cancel_scan(scan_id):
        return {"cancelled": True}
    raise HTTPException(404, "Scan not found or already finished")


@router.get("/scans")
def list_scans():
    return {"scans": dashboard_service.get_scans()}
