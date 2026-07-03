"""Shared pytest fixtures for isolated app data."""

import pytest

from backend.database import db as database


@pytest.fixture(autouse=True)
def isolated_app_data(tmp_path, monkeypatch):
    """Keep tests from writing to real ~/.aifm/."""
    monkeypatch.setattr("backend.utils.paths.app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("backend.utils.paths.db_path", lambda: tmp_path / "app.db")
    monkeypatch.setattr("backend.utils.paths.settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("backend.utils.paths.key_path", lambda: tmp_path / ".key")
    monkeypatch.setattr("config.settings.settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr("config.settings.key_path", lambda: tmp_path / ".key")
    monkeypatch.setattr("config.settings.app_data_dir", lambda: tmp_path)
    if hasattr(database._local, "conn") and database._local.conn is not None:
        database._local.conn.close()
        database._local.conn = None
    database.init_db()
    yield tmp_path
    if hasattr(database._local, "conn") and database._local.conn is not None:
        database._local.conn.close()
        database._local.conn = None
