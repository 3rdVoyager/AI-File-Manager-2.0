"""Generate cleanup recommendations after scan."""

from backend.database import db as database
from backend.filesystem.service import human_size


def regenerate_recommendations() -> None:
    with database.db() as conn:
        conn.execute("DELETE FROM recommendations")

        # Duplicate screenshots
        row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(f.size_bytes), 0) as bytes
               FROM files f JOIN analyses a ON a.file_id = f.id
               WHERE a.tags_json LIKE '%screenshot%'
               AND f.content_hash IN (
                   SELECT content_hash FROM files GROUP BY content_hash HAVING COUNT(*) > 1
               )"""
        ).fetchone()
        if row and row["cnt"] > 0:
            conn.execute(
                """INSERT INTO recommendations (rec_type, title, description, savings_bytes, file_count, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                ("duplicates", f"{row['cnt']} duplicate screenshots",
                 f"You can save {human_size(row['bytes'])}", row["bytes"], row["cnt"]),
            )

        # Inactive projects
        row = conn.execute(
            """SELECT COUNT(DISTINCT a.project) as cnt FROM analyses a
               WHERE a.project != '' AND a.lifecycle = 'Dormant'"""
        ).fetchone()
        if row and row["cnt"] > 0:
            conn.execute(
                """INSERT INTO recommendations (rec_type, title, description, savings_bytes, file_count, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                ("projects", f"{row['cnt']} inactive coding projects",
                 "Not accessed in 6+ months", 0, row["cnt"]),
            )

        # Temp downloads
        row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(f.size_bytes), 0) as bytes
               FROM files f JOIN analyses a ON a.file_id = f.id
               WHERE a.category = 'Downloads' OR a.lifecycle = 'Transient'"""
        ).fetchone()
        if row and row["cnt"] > 0:
            conn.execute(
                """INSERT INTO recommendations (rec_type, title, description, savings_bytes, file_count, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                ("downloads", f"{row['cnt']} temporary downloads",
                 f"You can save {human_size(row['bytes'])}", row["bytes"], row["cnt"]),
            )

        # Large videos
        row = conn.execute(
            """SELECT COUNT(*) as cnt, COALESCE(SUM(f.size_bytes), 0) as bytes
               FROM files f JOIN analyses a ON a.file_id = f.id
               WHERE f.extension IN ('.mp4', '.mkv', '.avi', '.mov')
               AND f.size_bytes > 500000000"""
        ).fetchone()
        if row and row["cnt"] > 0:
            conn.execute(
                """INSERT INTO recommendations (rec_type, title, description, savings_bytes, file_count, created_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                ("videos", f"{row['cnt']} large video files",
                 f"You can save {human_size(row['bytes'])}", row["bytes"], row["cnt"]),
            )
