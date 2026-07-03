import getpass
from fastapi import APIRouter

from backend.database import db as database

router = APIRouter(tags=["status"])


@router.get("/status")
def get_status():
    settings_data = __import__("config.settings", fromlist=["load_settings", "settings_public_dict"])
    s = settings_data.load_settings()
    file_count = database.fetch_one("SELECT COUNT(*) as cnt FROM files")
    cache_count = database.fetch_one("SELECT COUNT(*) as cnt FROM file_cache")
    return {
        "status": "ok",
        "username": getpass.getuser(),
        "files_indexed": file_count["cnt"] if file_count else 0,
        "cache_entries": cache_count["cnt"] if cache_count else 0,
        **settings_data.settings_public_dict(s),
    }
