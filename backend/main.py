"""FastAPI application."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
from backend.database.db import init_db
from backend.services.duplicate_service import rebuild_duplicates
from backend.utils.paths import frontend_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    init_db()
    rebuild_duplicates()
    app = FastAPI(title="AI File Manager", version="2.0.0")
    app.include_router(api_router)

    fe = frontend_dir()
    if fe.exists():
        app.mount("/static", StaticFiles(directory=str(fe)), name="static")

    @app.get("/")
    def index():
        index_path = fe / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "AI File Manager API", "docs": "/docs"}

    return app


app = create_app()
