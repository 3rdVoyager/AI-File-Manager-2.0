"""API integration tests."""

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.database import db as database
from backend.providers.groq_limiter import GroqRateLimitError
from backend.services import query_service


def wait_for_scan(client: TestClient, scan_id: int) -> dict:
    for _ in range(20):
        status = client.get(f"/api/scan/{scan_id}").json()
        if status["status"] in {"completed", "failed", "cancelled"}:
            return status
        time.sleep(0.3)
    return client.get(f"/api/scan/{scan_id}").json()


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
        s = wait_for_scan(client, scan_id)
        assert "ai_status" in s
        assert "ai_wait_seconds" in s
        assert s["status"] == "completed"
        files = client.get("/api/files").json()
        assert files["total"] >= 1


def test_rescan_removes_files_deleted_outside_app():
    with tempfile.TemporaryDirectory() as tmp:
        keep_path = Path(tmp, "keep.txt")
        removed_path = Path(tmp, "removed.txt")
        keep_path.write_text("keep", encoding="utf-8")
        removed_path.write_text("remove", encoding="utf-8")
        client = TestClient(create_app())

        first_scan_id = client.post("/api/scan", json={"path": tmp}).json()["scan_id"]
        assert wait_for_scan(client, first_scan_id)["status"] == "completed"

        removed_norm = str(removed_path.resolve())
        keep_norm = str(keep_path.resolve())
        initial_paths = {f["path"] for f in client.get("/api/files").json()["files"]}
        assert removed_norm in initial_paths
        assert keep_norm in initial_paths

        removed_path.unlink()
        second_scan_id = client.post("/api/scan", json={"path": tmp}).json()["scan_id"]
        assert wait_for_scan(client, second_scan_id)["status"] == "completed"

        rescanned_paths = {f["path"] for f in client.get("/api/files").json()["files"]}
        assert removed_norm not in rescanned_paths
        assert keep_norm in rescanned_paths


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

def test_scan_in_background():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "background_sample.txt").write_text("content", encoding="utf-8")
        client = TestClient(create_app())
        scan_id = client.post("/api/scan", json={"path": tmp, "run_in_background": True}).json()["scan_id"]

        # Assert that the scan starts in the background and is running
        initial_status = client.get(f"/api/scan/{scan_id}").json()
        assert initial_status["status"] == "running"

        # Wait for the scan to complete
        s = wait_for_scan(client, scan_id)
        assert s["status"] == "completed"
        
        files = client.get("/api/files").json()
        assert files["total"] >= 1
