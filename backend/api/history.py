from fastapi import APIRouter

from backend.database import db as database

router = APIRouter(tags=["history"])


@router.get("/history")
def history():
    rows = database.fetch_all(
        "SELECT event_type, description, metadata_json, created_at FROM activity_log ORDER BY created_at DESC LIMIT 100"
    )
    return {"history": rows}
