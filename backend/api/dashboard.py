from fastapi import APIRouter

from backend.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def dashboard():
    return dashboard_service.get_dashboard()


@router.get("/categories")
def categories():
    return dashboard_service.get_categories()


@router.get("/activity")
def activity():
    return {"activity": dashboard_service.get_activity()}


@router.get("/recommendations")
def recommendations():
    return {"recommendations": dashboard_service.get_recommendations()}
