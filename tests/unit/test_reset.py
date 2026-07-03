"""Tests for factory reset and system endpoints."""

from config.settings import load_settings, save_settings, AppSettings
from backend.database import db as database
from backend.main import create_app
from backend.services.reset_service import factory_reset
from fastapi.testclient import TestClient


def test_reset_requires_confirm(isolated_app_data):
    client = TestClient(create_app())
    r = client.post("/api/reset", json={"confirm": "wrong"})
    assert r.status_code == 400


def test_factory_reset_wipes_data(isolated_app_data, tmp_path):
    save_settings(AppSettings(api_key="gsk_test1234", setup_complete=True))
    with database.db() as conn:
        conn.execute(
            "INSERT INTO files (path, filename, size_bytes, extension) VALUES (?, ?, ?, ?)",
            ("/tmp/x.txt", "x.txt", 10, ".txt"),
        )

    factory_reset()

    assert database.fetch_one("SELECT COUNT(*) as cnt FROM files")["cnt"] == 0
    s = load_settings()
    assert s.setup_complete is False
    assert s.api_key == ""


def test_reset_api(isolated_app_data):
    save_settings(AppSettings(api_key="gsk_test", setup_complete=True))
    client = TestClient(create_app())
    r = client.post("/api/reset", json={"confirm": "RESET"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert load_settings().setup_complete is False
