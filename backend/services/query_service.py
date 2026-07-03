"""Natural language and deterministic query service."""

import json
import re
from typing import Any

import httpx

from config.settings import load_settings
from backend.database import db as database
from backend.database.db import log_activity
from backend.filesystem.service import human_size
from backend.providers.groq import GROQ_URL
from backend.providers.groq_limiter import GroqRateLimitError, limiter


def filter_files(params: dict) -> list[dict]:
    where, args = [], []
    if params.get("category"):
        where.append("a.category = ?")
        args.append(params["category"])
    if params.get("action"):
        where.append("a.action = ?")
        args.append(params["action"])
    if params.get("lifecycle"):
        where.append("a.lifecycle = ?")
        args.append(params["lifecycle"])
    if params.get("project"):
        where.append("a.project LIKE ?")
        args.append(f"%{params['project']}%")
    if params.get("extension"):
        where.append("f.extension = ?")
        args.append(params["extension"] if params["extension"].startswith(".") else f".{params['extension']}")
    if params.get("min_importance"):
        where.append("a.importance >= ?")
        args.append(params["min_importance"])
    if params.get("max_importance"):
        where.append("a.importance <= ?")
        args.append(params["max_importance"])
    if params.get("search"):
        where.append("(f.filename LIKE ? OR f.path LIKE ? OR a.summary LIKE ?)")
        s = f"%{params['search']}%"
        args.extend([s, s, s])

    # Heuristic NL patterns without AI
    if params.get("query"):
        q = params["query"].lower()
        if "inactive" in q and "python" in q:
            where.append("a.lifecycle = 'Dormant'")
            where.append("f.extension IN ('.py', '.ipynb')")
        elif "duplicate" in q:
            where.append("f.content_hash IN (SELECT content_hash FROM files GROUP BY content_hash HAVING COUNT(*) > 1)")
        elif "screenshot" in q:
            where.append("a.tags_json LIKE '%screenshot%'")
        elif "large" in q:
            where.append("f.size_bytes > 100000000")

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = database.fetch_all(
        f"""SELECT f.path, f.filename, f.size_bytes, a.summary, a.category, a.action,
                   a.importance, a.lifecycle, a.project
            FROM files f LEFT JOIN analyses a ON a.file_id = f.id {clause}
            ORDER BY f.size_bytes DESC LIMIT 200""",
        tuple(args),
    )
    for r in rows:
        r["size_human"] = human_size(r["size_bytes"])
    return rows


def _record_query(query: str, result_count: int) -> None:
    log_activity("query_executed", f"Query: {query[:60]}", {"count": result_count})


async def natural_language_query(query: str) -> dict[str, Any]:
    settings = load_settings()
    if not settings.api_key_set():
        # Fall back to keyword heuristics
        results = filter_files({"query": query, "search": query})
        _record_query(query, len(results))
        return {"query": query, "results": results, "method": "keyword", "count": len(results)}

    # Build corpus summary for AI
    sample = database.fetch_all(
        """SELECT f.filename, a.category, a.project, a.lifecycle, a.action, a.summary
           FROM files f JOIN analyses a ON a.file_id = f.id LIMIT 500"""
    )
    if not sample:
        return {"query": query, "results": [], "method": "ai", "count": 0}

    corpus = json.dumps(sample[:200])
    prompt = f"""Given this file index (JSON array) and user query, return JSON:
{{"filters": {{"category": "", "lifecycle": "", "action": "", "search": "", "extension": ""}},
  "explanation": "brief explanation"}}
Only include non-empty filters. User query: {query}
File index: {corpus[:8000]}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await limiter.post(
                client,
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                },
                max_attempts=2,
            )
            if r.status_code == 200:
                data = json.loads(r.json()["choices"][0]["message"]["content"])
                filters = data.get("filters", {})
                filters["search"] = filters.get("search") or query
                results = filter_files(filters)
                _record_query(query, len(results))
                return {
                    "query": query, "results": results, "method": "ai",
                    "explanation": data.get("explanation", ""), "count": len(results),
                }
    except GroqRateLimitError as e:
        results = filter_files({"query": query, "search": query})
        _record_query(query, len(results))
        return {
            "query": query,
            "results": results,
            "method": "keyword",
            "count": len(results),
            "rate_limited": True,
            "message": f"Groq rate limit reached. Using keyword search for now; AI search will resume in about {max(1, int(e.wait_seconds))}s.",
        }
    except Exception:
        pass

    results = filter_files({"query": query, "search": query})
    _record_query(query, len(results))
    return {"query": query, "results": results, "method": "keyword", "count": len(results)}
