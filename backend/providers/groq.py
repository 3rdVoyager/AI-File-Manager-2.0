"""Groq AI provider."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from config.settings import load_settings, DEFAULT_MODEL
from backend.filesystem.service import FileMetadata
from backend.models.domain import AnalysisResult, VALID_ACTIONS, VALID_LIFECYCLES
from backend.providers.groq_limiter import GroqRateLimitError, limiter, parse_reset_seconds
from backend.scanner.token_budget import ScanTier, tier_for_file_count

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

CATEGORIES = "Programming|School|Documents|Images|Videos|Downloads|Installers|System|Other"


def _system_prompt(tier: ScanTier, batch: bool = False) -> str:
    keys = [
        "summary", "category", "subcategory", "tags", "project", "importance",
        "sentimental_value", "lifecycle", "action", "confidence", "reasoning",
        "requires_review", "suggested_filename", "rename_reason", "rename_confidence",
    ]
    field_spec = (
        f'keys: {", ".join(keys)}. summary <=12 words; reasoning <=15 words; '
        f"category one of {CATEGORIES}; lifecycle one of Active, Dormant, Archived, Transient, Unknown; "
        "action one of Keep, Delete, Archive, Review. suggested_filename empty unless the filename could be improved for clarity, "
        "organization, or descriptive accuracy; when set, keep the original extension and use a safe Windows filename. "
        "rename_reason <=12 words; rename_confidence 0-100."
    )
    cleanup_guidance = (
        "Be critical about cleanup. Use Delete with confidence 75-95 for files that are usually safe "
        "after use: software installers, temp files, partial downloads, redundant caches, obsolete logs, "
        "crash dumps, and duplicate-looking downloads. Use Keep for source code, active projects, configs, "
        "personal documents, photos, and unique media. Use Review only when the file may be useful but the "
        "metadata is ambiguous. Transient lifecycle should usually mean Delete unless personal value is likely. "
        'Examples: setup.msi in Downloads -> {"category":"Installers","lifecycle":"Transient","action":"Delete","confidence":90}; '
        'notes.py in a project -> {"category":"Programming","lifecycle":"Active","action":"Keep","confidence":85}; '
        'family.jpg -> {"category":"Images","lifecycle":"Active","action":"Keep","confidence":80}.'
    )
    if batch:
        return (
            "Analyze files on the user's computer. Reply with JSON only: "
            f'{{"files":[{{"id":1,"summary":"...","category":"Other"}}]}}. Include one object per input file, '
            f"preserve input order, match each input id, and include these {field_spec} {cleanup_guidance} Be concise."
        )
    return (
        "Analyze a file on the user's computer. Reply with JSON only using these "
        f"{field_spec} {cleanup_guidance} Be concise."
    )


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _coerce(data: dict[str, Any], metadata: FileMetadata) -> AnalysisResult:
    action = data.get("action", "Review")
    if action not in VALID_ACTIONS:
        action = "Review"
    lifecycle = data.get("lifecycle", "Unknown")
    if lifecycle not in VALID_LIFECYCLES:
        lifecycle = "Unknown"
    return AnalysisResult(
        file=metadata.filename,
        path=metadata.path,
        summary=str(data.get("summary", "")),
        category=str(data.get("category", "Other")),
        subcategory=str(data.get("subcategory", "")),
        tags=list(data.get("tags", [])) if isinstance(data.get("tags", []), list) else [],
        project=str(data.get("project", "")),
        importance=_bounded_int(data.get("importance"), 5, 1, 10),
        sentimental_value=_bounded_int(data.get("sentimental_value"), 1, 1, 10),
        confidence=_bounded_int(data.get("confidence"), 50, 0, 100),
        lifecycle=lifecycle,
        action=action,
        reasoning=str(data.get("reasoning", "")),
        suggested_filename=str(data.get("suggested_filename", "")),
        rename_reason=str(data.get("rename_reason", "")),
        rename_confidence=_bounded_int(data.get("rename_confidence"), 0, 0, 100),
        requires_review=bool(data.get("requires_review", False)),
        size_bytes=metadata.size_bytes,
        size_human=metadata.size_human,
        extension=metadata.extension,
        modified=metadata.modified,
    )


def _build_user_msg(metadata: FileMetadata, content: str, tier: ScanTier) -> str:
    return _build_file_block(metadata, content, tier)


def _build_file_block(metadata: FileMetadata, content: str, tier: ScanTier, item_id: int | None = None) -> str:
    parent = Path(metadata.path).parent.name or str(Path(metadata.path).parent)
    modified = metadata.modified.split("T", 1)[0]
    lines = [
        f"File: {metadata.filename}",
        f"Parent: {parent}",
        f"Size: {metadata.size_human}",
        f"Modified: {modified}",
    ]
    if item_id is not None:
        lines.insert(0, f"ID: {item_id}")
    if content and tier.content_cap > 0:
        capped = content[: tier.content_cap]
        lines.append(f"\nContent preview:\n{capped}")
    elif not content:
        lines.append("\n(binary or empty — classify from metadata only)")
    return "\n".join(lines)


def _build_batch_user_msg(items: list[tuple[int, FileMetadata, str]], tier: ScanTier) -> str:
    return "\n\n---\n\n".join(
        _build_file_block(metadata, content, tier, item_id=item_id)
        for item_id, metadata, content in items
    )


def _backoff_seconds(attempt: int, response: Optional[httpx.Response] = None) -> float:
    if response is not None and response.status_code == 429:
        retry_after = (
            _parse_reset_seconds(response.headers.get("Retry-After"))
            or _parse_reset_seconds(response.headers.get("x-ratelimit-reset-requests"))
            or _parse_reset_seconds(response.headers.get("x-ratelimit-reset-tokens"))
            or _parse_reset_seconds(response.headers.get("x-ratelimit-reset"))
        )
        if retry_after is not None:
            return min(retry_after, 60.0)
        return min(2 ** (attempt + 1), 16)
    return 1.0


def _parse_reset_seconds(value: str | None) -> float | None:
    return parse_reset_seconds(value)


def _failed_result(metadata: FileMetadata, summary: str, reasoning: str) -> AnalysisResult:
    return AnalysisResult(
        file=metadata.filename,
        path=metadata.path,
        summary=summary,
        category="Other",
        action="Review",
        reasoning=reasoning,
        requires_review=True,
        size_bytes=metadata.size_bytes,
        size_human=metadata.size_human,
        extension=metadata.extension,
        modified=metadata.modified,
    )


class GroqProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None, tier: ScanTier | None = None):
        settings = load_settings()
        self.api_key = (api_key or settings.api_key).strip()
        self.model = model or settings.model or DEFAULT_MODEL
        self.tier = tier or tier_for_file_count(200)
        self._client: httpx.AsyncClient | None = None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _post(self, payload: dict, max_attempts: int = 4) -> httpx.Response | None:
        for attempt in range(2):
            try:
                client = self._get_client()
                return await limiter.post(
                    client,
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    max_attempts=max_attempts,
                )
            except GroqRateLimitError:
                raise
            except httpx.HTTPError as e:
                logger.warning("Groq HTTP error attempt %s: %s", attempt + 1, e)
                await asyncio.sleep(_backoff_seconds(attempt))
        return None

    async def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            r = await self._post({
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply with OK"}],
                "max_tokens": 5,
            }, max_attempts=1)
            return r is not None and r.status_code == 200
        except GroqRateLimitError:
            return False

    async def analyze(self, metadata: FileMetadata, content: str) -> AnalysisResult:
        if not self.api_key:
            return AnalysisResult(
                file=metadata.filename, path=metadata.path,
                summary="AI not configured", category="Other", action="Review",
                reasoning="Set your Groq API key in Settings.",
                size_bytes=metadata.size_bytes, size_human=metadata.size_human,
                extension=metadata.extension, modified=metadata.modified,
            )

        user_msg = _build_user_msg(metadata, content, self.tier)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system_prompt(self.tier)},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.15,
            "max_tokens": self.tier.max_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            r = await self._post(payload)
        except GroqRateLimitError:
            return _failed_result(
                metadata,
                "AI paused by rate limit",
                "Groq rate limit reached. This file can be retried after the limit resets.",
            )
        if r is None:
            return _failed_result(metadata, "Analysis failed", "Could not reach Groq. Try again later.")
        if r.status_code != 200:
            logger.warning("Groq error %s: %s", r.status_code, r.text[:200])
            return _failed_result(metadata, "Analysis failed", "Groq returned an error. Try again later.")
        try:
            text = r.json()["choices"][0]["message"]["content"]
            data = json.loads(text)
            result = _coerce(data, metadata)
            result.prefiltered = False
            return result
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Groq parse failed: %s", e)
            return _failed_result(metadata, "Analysis failed", "Could not parse AI response. Try again later.")

    async def analyze_batch(self, items: list[tuple[FileMetadata, str]]) -> list[AnalysisResult]:
        if not items:
            return []
        if len(items) == 1:
            return [await self.analyze(items[0][0], items[0][1])]
        if not self.api_key:
            return [
                AnalysisResult(
                    file=metadata.filename, path=metadata.path,
                    summary="AI not configured", category="Other", action="Review",
                    reasoning="Set your Groq API key in Settings.",
                    size_bytes=metadata.size_bytes, size_human=metadata.size_human,
                    extension=metadata.extension, modified=metadata.modified,
                )
                for metadata, _ in items
            ]

        indexed = [(idx, metadata, content) for idx, (metadata, content) in enumerate(items, start=1)]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system_prompt(self.tier, batch=True)},
                {"role": "user", "content": _build_batch_user_msg(indexed, self.tier)},
            ],
            "temperature": 0.1,
            "max_tokens": max(180, 120 * len(items) + 80),
            "response_format": {"type": "json_object"},
        }

        try:
            r = await self._post(payload)
        except GroqRateLimitError:
            logger.warning("Groq batch paused by rate limit; marking %s files for review", len(items))
            return [
                _failed_result(
                    metadata,
                    "AI paused by rate limit",
                    "Groq rate limit reached. Retry the scan after the limit resets.",
                )
                for metadata, _content in items
            ]
        if r is None:
            logger.warning("Groq batch failed before receiving a response")
            return [_failed_result(metadata, "Analysis failed", "Could not reach Groq. Try again later.") for metadata, _ in items]
        if r.status_code != 200:
            logger.warning("Groq batch error %s: %s", r.status_code, r.text[:200])
            return [_failed_result(metadata, "Analysis failed", "Groq returned an error. Try again later.") for metadata, _ in items]
        try:
            text = r.json()["choices"][0]["message"]["content"]
            data = json.loads(text)
            raw_files = data.get("files", []) if isinstance(data, dict) else data
            if not isinstance(raw_files, list):
                raise ValueError("Batch response did not include a files array")

            by_id: dict[int, dict[str, Any]] = {}
            for position, raw in enumerate(raw_files, start=1):
                if not isinstance(raw, dict):
                    continue
                item_id = _bounded_int(raw.get("id"), position, 1, len(items))
                by_id[item_id] = raw

            results: list[AnalysisResult] = []
            for item_id, metadata, _content in indexed:
                raw = by_id.get(item_id)
                if raw is None:
                    raise ValueError(f"Batch response missing item {item_id}")
                result = _coerce(raw, metadata)
                result.prefiltered = False
                results.append(result)
            return results
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Groq batch parse failed: %s", e)
            return [_failed_result(metadata, "Analysis failed", "Could not parse AI response. Try again later.") for metadata, _ in items]

