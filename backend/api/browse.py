from fastapi import APIRouter, HTTPException, Query

from backend.filesystem import service as fs

router = APIRouter(tags=["browse"])


@router.get("/browse")
def browse(path: str = Query(default="")):
    try:
        return fs.list_directory(path if path else None)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except PermissionError:
        raise HTTPException(403, "Permission denied accessing this folder.")


@router.get("/browse/quick-picks")
def quick_picks():
    return {"picks": fs.list_quick_picks()}
