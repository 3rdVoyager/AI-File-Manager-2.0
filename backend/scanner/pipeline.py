"""Scan pipeline orchestration."""

import asyncio
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from config.settings import load_settings
from backend.cache.analysis_cache import get_cached, set_cached
from backend.database import db as database
from backend.database.db import log_activity
from backend.filesystem import service as fs
from backend.models.domain import AnalysisResult
from backend.providers.groq_limiter import get_rate_limit_status
from backend.providers.groq import GroqProvider
from backend.scanner.stages.prefilter import pre_analyze_filter
from backend.scanner.token_budget import tier_for_file_count, model_for_scan, estimate_ai_calls
from backend.services.duplicate_service import rebuild_duplicates
from backend.services.recommendations_service import regenerate_recommendations
from backend.utils.time import utc_now

logger = logging.getLogger(__name__)

AI_BATCH_CONCURRENCY = 1
_active_scans: dict[int, dict] = {}
_scan_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=2)


def _progress_pct(processed: int, total: int, *, cap: float = 99.0) -> float:
    if total <= 0:
        return 100.0
    return min(cap, (processed / total) * 100)


def _analysis_from_dict(d: dict, meta: fs.FileMetadata) -> AnalysisResult:
    return AnalysisResult(
        file=meta.filename, path=meta.path,
        summary=d.get("summary", ""),
        category=d.get("category", "Other"),
        subcategory=d.get("subcategory", ""),
        tags=d.get("tags", []),
        project=d.get("project", ""),
        importance=d.get("importance", 5),
        sentimental_value=d.get("sentimental_value", 1),
        confidence=d.get("confidence", 50),
        lifecycle=d.get("lifecycle", "Unknown"),
        action=d.get("action", "Review"),
        reasoning=d.get("reasoning", ""),
        suggested_filename=d.get("suggested_filename", ""),
        rename_reason=d.get("rename_reason", ""),
        rename_confidence=d.get("rename_confidence", 0),
        requires_review=d.get("requires_review", False),
        prefiltered=d.get("prefiltered", False),
        size_bytes=meta.size_bytes,
        size_human=meta.size_human,
        extension=meta.extension,
        modified=meta.modified,
    )


def _persist_file(scan_id: int, meta: fs.FileMetadata, analysis: AnalysisResult, model_used: str | None = None) -> int:
    model = model_used or load_settings().model
    with database.db() as conn:
        conn.execute(
            """INSERT INTO files (path, filename, size_bytes, extension, created_at, modified_at, content_hash, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                 size_bytes=excluded.size_bytes, modified_at=excluded.modified_at,
                 content_hash=excluded.content_hash, scanned_at=excluded.scanned_at""",
            (meta.path, meta.filename, meta.size_bytes, meta.extension,
             meta.created, meta.modified_at, meta.content_hash, utc_now()),
        )
        row = conn.execute("SELECT id FROM files WHERE path = ?", (meta.path,)).fetchone()
        file_id = row["id"]
        conn.execute(
            """INSERT INTO analyses (file_id, summary, category, subcategory, tags_json, project,
               importance, sentimental_value, confidence, lifecycle, action, reasoning,
               suggested_filename, rename_reason, rename_confidence,
               requires_review, prefiltered, model_used, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(file_id) DO UPDATE SET
                 summary=excluded.summary, category=excluded.category, subcategory=excluded.subcategory,
                 tags_json=excluded.tags_json, project=excluded.project, importance=excluded.importance,
                 sentimental_value=excluded.sentimental_value, confidence=excluded.confidence,
                 lifecycle=excluded.lifecycle, action=excluded.action, reasoning=excluded.reasoning,
                 suggested_filename=excluded.suggested_filename, rename_reason=excluded.rename_reason,
                 rename_confidence=excluded.rename_confidence,
                 requires_review=excluded.requires_review,
                 prefiltered=excluded.prefiltered, model_used=excluded.model_used, analyzed_at=excluded.analyzed_at""",
            (file_id, analysis.summary, analysis.category, analysis.subcategory,
             json.dumps(analysis.tags), analysis.project, analysis.importance,
             analysis.sentimental_value, analysis.confidence, analysis.lifecycle,
             analysis.action, analysis.reasoning, analysis.suggested_filename, analysis.rename_reason,
             analysis.rename_confidence, int(analysis.requires_review), int(analysis.prefiltered),
             model, utc_now()),
        )
        conn.execute(
            "INSERT OR IGNORE INTO scan_files (scan_id, file_id) VALUES (?, ?)",
            (scan_id, file_id),
        )
        if analysis.project:
            conn.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (analysis.project,))
            proj = conn.execute("SELECT id FROM projects WHERE name = ?", (analysis.project,)).fetchone()
            if proj:
                conn.execute(
                    "INSERT OR IGNORE INTO file_projects (file_id, project_id) VALUES (?, ?)",
                    (file_id, proj["id"]),
                )
        return file_id


def _canonical_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _path_is_within_root(path: str, root_path: str) -> bool:
    try:
        root = _canonical_path(root_path)
        return os.path.commonpath([_canonical_path(path), root]) == root
    except (OSError, ValueError):
        return False


def _prune_stale_files(root_path: str, current_paths: list[str]) -> int:
    current = {_canonical_path(path) for path in current_paths}
    stale_ids: list[int] = []

    with database.db() as conn:
        rows = conn.execute("SELECT id, path FROM files").fetchall()
        for row in rows:
            if _path_is_within_root(row["path"], root_path) and _canonical_path(row["path"]) not in current:
                stale_ids.append(row["id"])

        if stale_ids:
            placeholders = ",".join("?" * len(stale_ids))
            conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", tuple(stale_ids))
            conn.execute(
                """DELETE FROM projects
                   WHERE NOT EXISTS (
                     SELECT 1 FROM file_projects WHERE file_projects.project_id = projects.id
                   )"""
            )

    return len(stale_ids)


def _is_cancel_requested(scan_id: int) -> bool:
    with _scan_lock:
        return bool(_active_scans.get(scan_id, {}).get("cancel_requested"))


def _mark_cancelled(scan_id: int) -> None:
    with database.db() as conn:
        conn.execute(
            "UPDATE scans SET status='cancelled', completed_at=? WHERE id=?",
            (utc_now(), scan_id),
        )
    with _scan_lock:
        if scan_id in _active_scans:
            _active_scans[scan_id]["status"] = "cancelled"


def _chunks[T](items: list[T], size: int) -> list[list[T]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _process_ai_batches(
    scan_id: int,
    provider: GroqProvider,
    pending: list[tuple[fs.FileMetadata, str]],
    scan_model: str,
    total_files: int,
    completed_count: int,
) -> int:
    if not pending:
        return completed_count

    semaphore = asyncio.Semaphore(AI_BATCH_CONCURRENCY)
    batch_size = max(1, provider.tier.batch_size)
    batches = _chunks(pending, batch_size)
    completed_ai = 0

    with _scan_lock:
        if scan_id in _active_scans:
            _active_scans[scan_id]["ai_status"] = "active"
            _active_scans[scan_id]["ai_pause_reason"] = ""
            _active_scans[scan_id]["ai_resume_at"] = ""
            _active_scans[scan_id]["ai_wait_seconds"] = 0

    async def analyze_batch(batch: list[tuple[fs.FileMetadata, str]]):
        async with semaphore:
            if _is_cancel_requested(scan_id):
                raise asyncio.CancelledError()
            return batch, await provider.analyze_batch(batch)

    tasks = [asyncio.create_task(analyze_batch(batch)) for batch in batches]
    try:
        for future in asyncio.as_completed(tasks):
            if _is_cancel_requested(scan_id):
                for task in tasks:
                    task.cancel()
                raise asyncio.CancelledError()

            batch, results = await future
            for (meta, _content), analysis in zip(batch, results):
                set_cached(path=meta.path, filename=meta.filename, modified_time=meta.modified_at,
                           size_bytes=meta.size_bytes, content_hash=meta.content_hash,
                           model=scan_model, analysis=analysis.to_dict())
                _persist_file(scan_id, meta, analysis, scan_model)

            completed_ai += len(batch)
            processed = completed_count + completed_ai
            rate_status = get_rate_limit_status()
            with _scan_lock:
                if scan_id in _active_scans:
                    _active_scans[scan_id]["files_processed"] = processed
                    _active_scans[scan_id]["current_file"] = batch[-1][0].path
                    _active_scans[scan_id]["progress"] = _progress_pct(processed, total_files)
                    _active_scans[scan_id]["ai_status"] = "paused" if rate_status["paused"] else "active"
                    _active_scans[scan_id]["ai_pause_reason"] = rate_status["reason"]
                    _active_scans[scan_id]["ai_resume_at"] = rate_status["resume_at"]
                    _active_scans[scan_id]["ai_wait_seconds"] = rate_status["wait_seconds"]
    except asyncio.CancelledError:
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    with _scan_lock:
        if scan_id in _active_scans:
            _active_scans[scan_id]["ai_status"] = "idle"
            _active_scans[scan_id]["ai_pause_reason"] = ""
            _active_scans[scan_id]["ai_resume_at"] = ""
            _active_scans[scan_id]["ai_wait_seconds"] = 0

    return completed_count + completed_ai


def _run_scan(scan_id: int, root_path: str, scan_type: str = "ai") -> None:
    database.close_db()
    settings = load_settings()
    hash_seen: dict[str, str] = {}
    loop = asyncio.new_event_loop()
    provider: GroqProvider | None = None
    use_ai = scan_type == "ai"

    try:
        paths = list(fs.traverse_directory(root_path))
        total = len(paths)
        scan_tier = tier_for_file_count(total)
        scan_model = model_for_scan(total, settings.model)
        if use_ai:
            provider = GroqProvider(model=scan_model, tier=scan_tier)
        total_bytes = 0
        processed_count = 0
        pending_ai: list[tuple[fs.FileMetadata, str]] = []

        with database.db() as conn:
            conn.execute(
                "UPDATE scans SET status='running', files_found=?, started_at=COALESCE(started_at, ?), scan_type=? WHERE id=?",
                (total, utc_now(), scan_type, scan_id),
            )

        with _scan_lock:
            _active_scans[scan_id]["files_found"] = total
            _active_scans[scan_id]["status"] = "running"

        for i, path in enumerate(paths):
            cancel_requested = False
            with _scan_lock:
                state = _active_scans.get(scan_id, {})
                if state.get("cancel_requested"):
                    cancel_requested = True
                else:
                    _active_scans[scan_id]["files_processed"] = processed_count
                    _active_scans[scan_id]["current_file"] = path
                    _active_scans[scan_id]["progress"] = _progress_pct(processed_count, total)
            if cancel_requested:
                _mark_cancelled(scan_id)
                return

            try:
                meta = fs.get_metadata(path)
                if not meta.content_hash:
                    meta.content_hash = fs.compute_hash(path)
                total_bytes += meta.size_bytes

                cached = get_cached(path, meta.modified_at, meta.size_bytes, meta.content_hash, scan_model)
                if cached:
                    analysis = _analysis_from_dict(cached, meta)
                elif meta.content_hash in hash_seen:
                    analysis = AnalysisResult(
                        file=meta.filename, path=meta.path,
                        summary=f"Duplicate of {hash_seen[meta.content_hash]}",
                        category="Other", subcategory="Duplicate", action="Delete",
                        confidence=100, reasoning="Identical content hash.",
                        tags=["type:duplicate"], prefiltered=True,
                        size_bytes=meta.size_bytes, size_human=meta.size_human,
                        extension=meta.extension, modified=meta.modified,
                    )
                else:
                    hash_seen[meta.content_hash] = meta.filename
                    pre = pre_analyze_filter(path, scan_tier.skip_ai_extensions)
                    if pre:
                        analysis = _analysis_from_dict(pre, meta)
                    elif use_ai and provider and provider.is_configured():
                        content = fs.read_text_snippets(path, max_per=scan_tier.snippet_max_per) if scan_tier.snippet_max_per else ""
                        pending_ai.append((meta, content))
                        continue
                    else:
                        analysis = AnalysisResult(
                            file=meta.filename, path=meta.path,
                            summary=f"File: {meta.filename}",
                            category=_guess_category(meta.extension),
                            action="Review", confidence=50,
                            reasoning="Script scan — basic classification only." if not use_ai else "AI not configured — basic classification only.",
                            prefiltered=True,
                            size_bytes=meta.size_bytes, size_human=meta.size_human,
                            extension=meta.extension, modified=meta.modified,
                        )

                _persist_file(scan_id, meta, analysis, scan_model)
                processed_count += 1
                with _scan_lock:
                    if scan_id in _active_scans:
                        _active_scans[scan_id]["files_processed"] = processed_count
                        _active_scans[scan_id]["progress"] = _progress_pct(processed_count, total)
            except Exception as e:
                logger.warning("Error processing %s: %s", path, e)

        if pending_ai and provider and provider.is_configured() and use_ai:
            try:
                processed_count = loop.run_until_complete(
                    _process_ai_batches(scan_id, provider, pending_ai, scan_model, total, processed_count)
                )
            except asyncio.CancelledError:
                _mark_cancelled(scan_id)
                return

        stale_count = _prune_stale_files(root_path, paths)
        if stale_count:
            logger.info("Pruned %s stale file rows under %s", stale_count, root_path)

        rebuild_duplicates()
        if use_ai:
            regenerate_recommendations()

        with database.db() as conn:
            conn.execute(
                """UPDATE scans SET status='completed', progress=100, files_processed=?,
                   total_bytes=?, completed_at=? WHERE id=?""",
                (total, total_bytes, utc_now(), scan_id),
            )

        scan_name = Path(root_path).name
        log_activity("scan_completed", f"Scan completed: {scan_name} • {total:,} files",
                     {"scan_id": scan_id, "path": root_path, "files": total})

        with _scan_lock:
            _active_scans[scan_id]["status"] = "completed"
            _active_scans[scan_id]["progress"] = 100

    except Exception as e:
        logger.exception("Scan failed: %s", e)
        with database.db() as conn:
            conn.execute(
                "UPDATE scans SET status='failed', error_message=?, completed_at=? WHERE id=?",
                (str(e), utc_now(), scan_id),
            )
        with _scan_lock:
            if scan_id in _active_scans:
                _active_scans[scan_id]["status"] = "failed"
                _active_scans[scan_id]["error"] = str(e)
    finally:
        if provider is not None:
            loop.run_until_complete(provider.close())
        loop.close()


def _guess_category(ext: str) -> str:
    mapping = {
        ".py": "Programming", ".js": "Programming", ".ts": "Programming",
        ".java": "Programming", ".cpp": "Programming", ".go": "Programming",
        ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
        ".png": "Images", ".jpg": "Images", ".jpeg": "Images", ".gif": "Images",
        ".mp4": "Videos", ".mkv": "Videos", ".avi": "Videos",
        ".zip": "Downloads", ".exe": "Installers",
    }
    return mapping.get(ext.lower(), "Other")


def start_scan(root_path: str, name: Optional[str] = None, run_in_background: bool = False, scan_type: str = "ai") -> int:
    root = fs.normalize_path(root_path)
    if not Path(root).is_dir():
        raise ValueError(f"Not a directory: {root_path}")

    scan_name = name or Path(root).name
    initial_status_in_db = 'running' if run_in_background else 'pending'
    scan_id = database.execute(
        """INSERT INTO scans (name, root_path, status, started_at) VALUES (?, ?, ?, ?)""",
        (scan_name, root, initial_status_in_db, utc_now()),
    )

    with _scan_lock:
        _active_scans[scan_id] = {
            "status": "running", "progress": 0, "files_found": 0,
            "files_processed": 0, "current_file": "", "cancel_requested": False, "error": "",
            "ai_status": "idle", "ai_pause_reason": "", "ai_resume_at": "", "ai_wait_seconds": 0,
            "scan_type": scan_type,
        }

    _executor.submit(_run_scan, scan_id, root, scan_type)
    return scan_id


def get_scan_status(scan_id: int) -> dict:
    row = database.fetch_one("SELECT * FROM scans WHERE id = ?", (scan_id,))
    if not row:
        return {"error": "Scan not found"}

    with _scan_lock:
        live = _active_scans.get(scan_id, {})

    ai_status = live.get("ai_status", "idle")
    rate_status = get_rate_limit_status()
    if live.get("status", row["status"]) == "running" and ai_status in {"active", "paused"} and rate_status["paused"]:
        ai_status = "paused"
        ai_pause_reason = rate_status["reason"]
        ai_resume_at = rate_status["resume_at"]
        ai_wait_seconds = rate_status["wait_seconds"]
    else:
        ai_pause_reason = live.get("ai_pause_reason", "")
        ai_resume_at = live.get("ai_resume_at", "")
        ai_wait_seconds = live.get("ai_wait_seconds", 0)

    return {
        "scan_id": scan_id,
        "status": live.get("status", row["status"]),
        "progress": live.get("progress", row["progress"] or 0),
        "files_found": live.get("files_found", row["files_found"] or 0),
        "files_processed": live.get("files_processed", row["files_processed"] or 0),
        "current_file": live.get("current_file", ""),
        "error": live.get("error", row["error_message"] or ""),
        "name": row["name"],
        "root_path": row["root_path"],
        "ai_status": ai_status,
        "ai_pause_reason": ai_pause_reason,
        "ai_resume_at": ai_resume_at,
        "ai_wait_seconds": ai_wait_seconds,
    }


def cancel_scan(scan_id: int) -> bool:
    with _scan_lock:
        if scan_id in _active_scans:
            _active_scans[scan_id]["cancel_requested"] = True
            return True
    return False


async def analyze_single_file(path: str) -> dict:
    meta = fs.get_metadata(path)
    meta.content_hash = fs.compute_hash(path)
    settings = load_settings()
    tier = tier_for_file_count(200)
    provider = GroqProvider(tier=tier)

    cached = get_cached(path, meta.modified_at, meta.size_bytes, meta.content_hash, settings.model)
    if cached:
        return cached

    pre = pre_analyze_filter(path, tier.skip_ai_extensions)
    if pre:
        return pre

    if provider.is_configured():
        content = fs.read_text_snippets(path, max_per=tier.snippet_max_per) if tier.snippet_max_per else ""
        result = await provider.analyze(meta, content)
        d = result.to_dict()
        set_cached(path, meta.filename, meta.modified_at, meta.size_bytes, meta.content_hash, settings.model, d)
        return d

    return {
        "summary": f"File: {meta.filename}",
        "category": _guess_category(meta.extension),
        "action": "Review",
        "reasoning": "Configure API key in Settings for AI analysis.",
        "prefiltered": True,
    }
