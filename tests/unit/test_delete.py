"""Tests for delete post-processing."""

import tempfile
from pathlib import Path
from unittest import mock

from backend.cache.analysis_cache import set_cached, path_hash
from backend.database import db as database
from backend.services.file_ops_service import execute_delete


def test_execute_delete_removes_db_and_cache(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / "remove-me.txt"
        fpath.write_text("hello", encoding="utf-8")
        norm = str(fpath.resolve())

        with database.db() as conn:
            conn.execute(
                """INSERT INTO files (path, filename, size_bytes, extension, content_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (norm, "remove-me.txt", 5, ".txt", "abc123"),
            )
            row = conn.execute("SELECT id FROM files WHERE path = ?", (norm,)).fetchone()
            conn.execute(
                "INSERT INTO analyses (file_id, summary, category, action) VALUES (?, ?, ?, ?)",
                (row["id"], "test", "Other", "Delete"),
            )

        set_cached(norm, "remove-me.txt", 1.0, 5, "abc123", "openai/gpt-oss-20b", {"summary": "x"})

        with mock.patch("backend.filesystem.service.delete_to_trash"):
            result = execute_delete([norm])

        assert result["deleted_count"] == 1
        assert database.fetch_one("SELECT id FROM files WHERE path = ?", (norm,)) is None
        assert database.fetch_one(
            "SELECT path_hash FROM file_cache WHERE path_hash = ?", (path_hash(norm),)
        ) is None


def test_execute_delete_normalizes_paths(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        fpath = Path(tmp) / "file.txt"
        fpath.write_text("data", encoding="utf-8")
        norm = str(fpath.resolve())

        with database.db() as conn:
            conn.execute(
                "INSERT INTO files (path, filename, size_bytes, extension) VALUES (?, ?, ?, ?)",
                (norm, "file.txt", 4, ".txt"),
            )

        with mock.patch("backend.filesystem.service.delete_to_trash") as trash:
            execute_delete([str(fpath)])
            trash.assert_called_once_with(norm)

        assert database.fetch_one("SELECT id FROM files WHERE path = ?", (norm,)) is None
