"""Path helpers — work in dev and when frozen by PyInstaller."""

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


def app_data_dir() -> Path:
    d = Path.home() / ".aifm"
    d.mkdir(parents=True, exist_ok=True)
    return d


def frontend_dir() -> Path:
    return project_root() / "frontend"


def db_path() -> Path:
    return app_data_dir() / "app.db"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def key_path() -> Path:
    return app_data_dir() / ".key"
