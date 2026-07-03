"""API route aggregation."""

from fastapi import APIRouter

from backend.api import (
    browse, dashboard, duplicates, files, history,
    projects, query, reports, scan, settings, status, system,
)

api_router = APIRouter(prefix="/api")

api_router.include_router(status.router)
api_router.include_router(settings.router)
api_router.include_router(browse.router)
api_router.include_router(dashboard.router)
api_router.include_router(scan.router)
api_router.include_router(files.router)
api_router.include_router(projects.router)
api_router.include_router(duplicates.router)
api_router.include_router(query.router)
api_router.include_router(reports.router)
api_router.include_router(history.router)
api_router.include_router(system.router)
