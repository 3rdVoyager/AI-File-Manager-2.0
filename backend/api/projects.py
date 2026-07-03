from fastapi import APIRouter

from backend.services import file_ops_service

router = APIRouter(tags=["projects"])


@router.get("/projects")
def projects():
    return {"projects": file_ops_service.get_projects()}
