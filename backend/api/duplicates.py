from fastapi import APIRouter

from backend.services import file_ops_service

router = APIRouter(tags=["duplicates"])


@router.get("/duplicates")
def duplicates():
    return {"groups": file_ops_service.get_duplicates()}
