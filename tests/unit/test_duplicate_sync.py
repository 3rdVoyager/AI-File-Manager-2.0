"""Tests for duplicate group and analysis synchronization."""

from backend.database import db as database
from backend.services.duplicate_service import rebuild_duplicates


def _insert_file(conn, path, filename, content_hash, modified_at):
    cur = conn.execute(
        """INSERT INTO files (path, filename, size_bytes, extension, modified_at, content_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (path, filename, 10, ".txt", modified_at, content_hash),
    )
    return cur.lastrowid


def test_rebuild_duplicates_marks_keeper_and_delete_copy(isolated_app_data):
    with database.db() as conn:
        _insert_file(conn, "/tmp/old.txt", "old.txt", "samehash", 1)
        _insert_file(conn, "/tmp/new.txt", "new.txt", "samehash", 2)

    rebuild_duplicates()

    old = database.fetch_one(
        """SELECT a.action, a.reasoning
           FROM analyses a JOIN files f ON f.id = a.file_id
           WHERE f.path = ?""",
        ("/tmp/old.txt",),
    )
    new = database.fetch_one(
        """SELECT a.action, a.reasoning, a.confidence
           FROM analyses a JOIN files f ON f.id = a.file_id
           WHERE f.path = ?""",
        ("/tmp/new.txt",),
    )
    groups = database.fetch_all("SELECT content_hash, file_count FROM duplicate_groups")

    assert groups == [{"content_hash": "samehash", "file_count": 2}]
    assert old["action"] == "Keep"
    assert "kept" in old["reasoning"]
    assert new == {"action": "Delete", "reasoning": "Identical content hash.", "confidence": 100}


def test_rebuild_duplicates_clears_stale_hash_delete(isolated_app_data):
    with database.db() as conn:
        file_id = _insert_file(conn, "/tmp/lone.txt", "lone.txt", "lonehash", 1)
        conn.execute(
            """INSERT INTO analyses (file_id, summary, category, action, confidence, reasoning)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (file_id, "Duplicate of deleted file", "Other", "Delete", 100, "Identical content hash."),
        )

    rebuild_duplicates()

    row = database.fetch_one(
        """SELECT action, confidence, reasoning, subcategory
           FROM analyses
           WHERE file_id = ?""",
        (file_id,),
    )

    assert row == {
        "action": "Review",
        "confidence": 50,
        "reasoning": "No longer duplicated.",
        "subcategory": "",
    }
