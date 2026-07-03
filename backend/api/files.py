from fastapi import APIRouter, HTTPException, Query

from backend.models.schemas import DeletePreviewRequest, DeleteRequest, OpenFileRequest
from backend.services import file_ops_service

router = APIRouter(tags=["files"])


@router.get("/files")
def list_files(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = "filename",
    order: str = "asc",
    search: str = "",
    category: str = "",
    action: str = "",
    min_confidence: int | None = Query(None, ge=0, le=100),
):
    return file_ops_service.list_files(page, per_page, sort, order, search, category, action, min_confidence)


@router.post("/open")
def open_file(body: OpenFileRequest):
    try:
        return file_ops_service.open_file(body.path)
    except FileNotFoundError:
        raise HTTPException(404, "File not found.")
    except IsADirectoryError:
        raise HTTPException(400, "Path is not a file.")
    except OSError as e:
        raise HTTPException(400, str(e))


@router.post("/delete-preview")
def delete_preview(body: DeletePreviewRequest):
    return file_ops_service.delete_preview(body.paths)


@router.post("/delete")
def delete_files(body: DeleteRequest):
    return file_ops_service.execute_delete(body.paths, body.dry_run)
