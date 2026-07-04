"""Duplicate group maintenance."""

import json
from typing import Any

from backend.database import db as database
from backend.utils.time import utc_now


def rebuild_duplicates() -> None:
    with database.db() as conn:
        conn.execute("DELETE FROM duplicate_members")
        conn.execute("DELETE FROM duplicate_groups")
        rows = conn.execute(
            """SELECT f.content_hash, COUNT(*) as cnt, SUM(f.size_bytes) as total
               FROM files f
               JOIN scan_files sf ON sf.file_id = f.id
               JOIN scans s ON s.id = sf.scan_id
               WHERE f.content_hash != '' AND s.scan_type = 'script'
               GROUP BY f.content_hash HAVING cnt > 1"""
        ).fetchall()
        for row in rows:
            cur = conn.execute(
                "INSERT INTO duplicate_groups (content_hash, file_count, total_bytes) VALUES (?, ?, ?)",
                (row["content_hash"], row["cnt"], row["total"]),
            )
            gid = cur.lastrowid
            members = conn.execute(
                """SELECT f.id FROM files f
                   JOIN scan_files sf ON sf.file_id = f.id
                   JOIN scans s ON s.id = sf.scan_id
                   WHERE f.content_hash = ? AND s.scan_type = 'script'""",
                (row["content_hash"],)
            ).fetchall()
            for m in members:
                conn.execute(
                    "INSERT INTO duplicate_members (group_id, file_id) VALUES (?, ?)",
                    (gid, m["id"]),
                )
        sync_duplicate_analyses(conn)


def sync_duplicate_analyses(conn: Any | None = None) -> None:
    if conn is None:
        with database.db() as owned_conn:
            _sync_duplicate_analyses(owned_conn)
        return
    _sync_duplicate_analyses(conn)


def _sync_duplicate_analyses(conn: Any) -> None:
    now = utc_now()
    duplicate_hashes = conn.execute(
        """SELECT f.content_hash
           FROM files f
           JOIN scan_files sf ON sf.file_id = f.id
           JOIN scans s ON s.id = sf.scan_id
           WHERE f.content_hash != '' AND s.scan_type = 'script'
           GROUP BY f.content_hash
           HAVING COUNT(*) > 1"""
    ).fetchall()

    conn.execute(
        """UPDATE analyses
           SET action = 'Review',
               confidence = 50,
               reasoning = 'No longer duplicated.',
               subcategory = '',
               prefiltered = 0,
               analyzed_at = ?
           WHERE reasoning = 'Identical content hash.'
             AND file_id IN (
               SELECT f.id
               FROM files f
               JOIN scan_files sf ON sf.file_id = f.id
               JOIN scans s ON s.id = sf.scan_id
               WHERE f.content_hash != '' AND s.scan_type = 'script'
                 AND f.content_hash NOT IN (
                   SELECT f.content_hash
                   FROM files f
                   JOIN scan_files sf ON sf.file_id = f.id
                   JOIN scans s ON s.id = sf.scan_id
                   WHERE f.content_hash != '' AND s.scan_type = 'script'
                   GROUP BY f.content_hash
                   HAVING COUNT(*) > 1
                 )
             )""",
        (now,),
    )

    for row in duplicate_hashes:
        members = conn.execute(
            """SELECT f.id, f.filename
               FROM files f
               JOIN scan_files sf ON sf.file_id = f.id
               JOIN scans s ON s.id = sf.scan_id
               WHERE f.content_hash = ? AND s.scan_type = 'script'
               ORDER BY f.modified_at ASC, f.path ASC""",
            (row["content_hash"],),
        ).fetchall()
        if len(members) < 2:
            continue

        keeper = members[0]
        conn.execute(
            """INSERT INTO analyses (file_id, summary, category, action, confidence, reasoning, analyzed_at)
               VALUES (?, ?, 'Other', 'Keep', 90, 'Original copy kept for duplicate group.', ?)
               ON CONFLICT(file_id) DO UPDATE SET
                 action = 'Keep',
                 confidence = CASE WHEN reasoning = 'Identical content hash.' THEN 90 ELSE confidence END,
                 reasoning = CASE
                   WHEN reasoning = 'Identical content hash.' THEN 'Original copy kept for duplicate group.'
                   ELSE reasoning
                 END,
                 subcategory = CASE WHEN reasoning = 'Identical content hash.' THEN '' ELSE subcategory END,
                 prefiltered = CASE WHEN reasoning = 'Identical content hash.' THEN 0 ELSE prefiltered END,
                 analyzed_at = ?""",
            (keeper["id"], f"Original copy: {keeper['filename']}", now, now),
        )

        for member in members[1:]:
            conn.execute(
                """INSERT INTO analyses (
                     file_id, summary, category, subcategory, tags_json, confidence,
                     lifecycle, action, reasoning, prefiltered, analyzed_at
                   )
                   VALUES (?, ?, 'Other', 'Duplicate', ?, 100, 'Unknown', 'Delete',
                           'Identical content hash.', 1, ?)
                   ON CONFLICT(file_id) DO UPDATE SET
                     summary = ?,
                     category = 'Other',
                     subcategory = 'Duplicate',
                     tags_json = ?,
                     confidence = 100,
                     action = 'Delete',
                     reasoning = 'Identical content hash.',
                     prefiltered = 1,
                     analyzed_at = ?""",
                (
                    member["id"],
                    f"Duplicate of {keeper['filename']}",
                    json.dumps(["type:duplicate"]),
                    now,
                    f"Duplicate of {keeper['filename']}",
                    json.dumps(["type:duplicate"]),
                    now,
                ),
            )
