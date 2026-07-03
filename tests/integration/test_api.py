"""API integration tests."""

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.database import db as database
from backend.providers.groq_limiter import GroqRateLimitError
from backend.services import query_service


def test_status_and_dashboard():
    client = TestClient(create_app())
    assert client.get("/api/status").status_code == 200
    dash = client.get("/api/dashboard").json()
    assert "files_analyzed" in dash


def test_browse_drives():
    client = TestClient(create_app())
    r = client.get("/api/browse")
    assert r.status_code == 200
    assert "entries" in r.json()


def test_scan_small_folder():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "sample.txt").write_text("content", encoding="utf-8")
        client = TestClient(create_app())
        scan_id = client.post("/api/scan", json={"path": tmp}).json()["scan_id"]
        for _ in range(20):
            s = client.get(f"/api/scan/{scan_id}").json()
            assert "ai_status" in s
            assert "ai_wait_seconds" in s
            if s["status"] == "completed":
                break
            time.sleep(0.3)
        files = client.get("/api/files").json()
        assert files["total"] >= 1


def test_settings_save():
    client = TestClient(create_app())
    r = client.post("/api/settings", json={"theme": "dark", "setup_complete": True})
    assert r.status_code == 200
    assert r.json()["setup_complete"] is True


def test_frontend_module_assets():
    client = TestClient(create_app())
    assert client.get("/static/scripts/components/ui.js").status_code == 200
    assert client.get("/static/scripts/views/dashboard.js").status_code == 200
    r = client.get("/")
    assert r.status_code == 200
    assert "AI File Manager" in r.text


def test_query_reports_rate_limited_keyword_fallback(monkeypatch):
    client = TestClient(create_app())
    client.post("/api/settings", json={"api_key": "gsk_test", "setup_complete": True})

    file_id = database.execute(
        """INSERT INTO files (path, filename, size_bytes, extension, content_hash)
           VALUES (?, ?, ?, ?, ?)""",
        ("C:/tmp/report.txt", "report.txt", 10, ".txt", "hash"),
    )
    database.execute(
        """INSERT INTO analyses (file_id, summary, category, lifecycle, action)
           VALUES (?, ?, ?, ?, ?)""",
        (file_id, "Quarterly report", "Documents", "Active", "Keep"),
    )

    async def rate_limited(*_args, **_kwargs):
        raise GroqRateLimitError(30)

    monkeypatch.setattr(query_service.limiter, "post", rate_limited)
    response = client.post("/api/query", json={"query": "report"})

    assert response.status_code == 200
    body = response.json()
    assert body["method"] == "keyword"
    assert body["rate_limited"] is True
    assert "Groq rate limit" in body["message"]
