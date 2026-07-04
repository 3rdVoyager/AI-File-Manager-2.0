"""Tests for delete post-processing."""

import tempfile
from pathlib import Path
from unittest import mock

from backend.cache.analysis_cache import set_cached, path_hash
from backend.database import db as database
from backend.services.file_ops_service import (
    apply_rename_suggestions, delete_empty_directories, execute_delete,
    list_empty_directories, list_rename_suggestions,
)


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


def test_empty_directory_cleanup_lists_and_removes_scanned_empty_dirs(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        empty_dir = root / "empty"
        non_empty_dir = root / "non-empty"
        empty_dir.mkdir()
        non_empty_dir.mkdir()
        (non_empty_dir / "file.txt").write_text("data", encoding="utf-8")
        database.execute(
            "INSERT INTO scans (name, root_path, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
            ("tmp", str(root.resolve()), "completed", "2026-01-01T00:00:00", "2026-01-01T00:00:01"),
        )

        listed = list_empty_directories()
        paths = {d["path"] for d in listed["directories"]}
        assert str(empty_dir.resolve()) in paths
        assert str(non_empty_dir.resolve()) not in paths

        result = delete_empty_directories([str(empty_dir)])
        assert result["removed_count"] == 1
        assert not empty_dir.exists()


def test_empty_directory_cleanup_refuses_non_empty_dirs(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        directory = root / "not-empty"
        directory.mkdir()
        (directory / "file.txt").write_text("data", encoding="utf-8")
        database.execute(
            "INSERT INTO scans (name, root_path, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
            ("tmp", str(root.resolve()), "completed", "2026-01-01T00:00:00", "2026-01-01T00:00:01"),
        )

        result = delete_empty_directories([str(directory)])
        assert result["removed_count"] == 0
        assert result["results"][0]["success"] is False
        assert directory.exists()


def test_rename_suggestions_list_and_apply_document_renames(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "scan001.pdf"
        file_path.write_bytes(b"%PDF test")
        norm = str(file_path.resolve())

        with database.db() as conn:
            conn.execute(
                """INSERT INTO files (path, filename, size_bytes, extension, content_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (norm, "scan001.pdf", 9, ".pdf", "renamehash"),
            )
            row = conn.execute("SELECT id FROM files WHERE path = ?", (norm,)).fetchone()
            conn.execute(
                """INSERT INTO analyses (
                     file_id, summary, category, action, suggested_filename, rename_reason, rename_confidence
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"], "Receipt from July", "Documents", "Keep",
                    "July_Receipt.pdf", "Generic scan name", 88,
                ),
            )

        suggestions = list_rename_suggestions()["suggestions"]
        assert suggestions[0]["suggested_filename"] == "July_Receipt.pdf"

        result = apply_rename_suggestions([norm])
        assert result["renamed_count"] == 1
        renamed_path = Path(tmp) / "July_Receipt.pdf"
        assert renamed_path.exists()
        assert not file_path.exists()
        assert database.fetch_one("SELECT id FROM files WHERE path = ?", (str(renamed_path.resolve()),)) is not None


def test_rename_suggestions_refuse_target_overwrite(isolated_app_data):
    with tempfile.TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "scan001.pdf"
        target_path = Path(tmp) / "July_Receipt.pdf"
        file_path.write_bytes(b"%PDF test")
        target_path.write_bytes(b"existing")
        norm = str(file_path.resolve())

        with database.db() as conn:
            conn.execute(
                """INSERT INTO files (path, filename, size_bytes, extension, content_hash)
                   VALUES (?, ?, ?, ?, ?)""",
                (norm, "scan001.pdf", 9, ".pdf", "renamehash"),
            )
            row = conn.execute("SELECT id FROM files WHERE path = ?", (norm,)).fetchone()
            conn.execute(
                """INSERT INTO analyses (
                     file_id, summary, category, action, suggested_filename, rename_reason, rename_confidence
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"], "Receipt from July", "Documents", "Keep",
                    "July_Receipt.pdf", "Generic scan name", 88,
                ),
            )

        result = apply_rename_suggestions([norm])
        assert result["renamed_count"] == 0
        assert result["results"][0]["success"] is False
        assert file_path.exists()
        assert target_path.exists()
