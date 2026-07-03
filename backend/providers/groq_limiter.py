"""Shared Groq request pacing and rate-limit status."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RATE_LIMIT_PAUSE_SECONDS = 60.0
LOW_REQUEST_THRESHOLD = 3
LOW_TOKEN_THRESHOLD = 1000


class GroqRateLimitError(RuntimeError):
    """Raised when Groq remains rate limited after retrying."""

    def __init__(self, wait_seconds: float, message: str = "Groq rate limit reached") -> None:
        super().__init__(message)
        self.wait_seconds = wait_seconds


@dataclass
class RateLimitStatus:
    paused: bool
    reason: str = ""
    resume_at: str = ""
    wait_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "paused": self.paused,
            "reason": self.reason,
            "resume_at": self.resume_at,
            "wait_seconds": self.wait_seconds,
        }


def parse_reset_seconds(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip().lower()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    for suffix, multiplier in multipliers.items():
        if value.endswith(suffix):
            try:
                return max(0.0, float(value[: -len(suffix)]) * multiplier)
            except ValueError:
                return None
    return None


def _header_wait_seconds(response: httpx.Response, fallback: float) -> float:
    candidates = [
        parse_reset_seconds(response.headers.get("Retry-After")),
        parse_reset_seconds(response.headers.get("x-ratelimit-reset-requests")),
        parse_reset_seconds(response.headers.get("x-ratelimit-reset-tokens")),
        parse_reset_seconds(response.headers.get("x-ratelimit-reset")),
        fallback,
    ]
    wait = max(value for value in candidates if value is not None)
    return min(max(0.0, wait), MAX_RATE_LIMIT_PAUSE_SECONDS)


def _remaining_int(response: httpx.Response, header: str) -> int | None:
    try:
        value = response.headers.get(header)
        return int(value) if value is not None else None
    except ValueError:
        return None


class GroqRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._paused_until = 0.0
        self._resume_at: datetime | None = None
        self._reason = ""

    def status(self) -> RateLimitStatus:
        now = time.monotonic()
        wait = max(0.0, self._paused_until - now)
        if wait <= 0:
            return RateLimitStatus(paused=False)
        return RateLimitStatus(
            paused=True,
            reason=self._reason,
            resume_at=self._resume_at.isoformat() if self._resume_at else "",
            wait_seconds=max(1, int(wait + 0.999)),
        )

    def clear(self) -> None:
        self._paused_until = 0.0
        self._resume_at = None
        self._reason = ""

    def _set_pause(self, wait_seconds: float, reason: str) -> None:
        wait = min(max(0.0, wait_seconds), MAX_RATE_LIMIT_PAUSE_SECONDS)
        if wait <= 0:
            return
        self._paused_until = max(self._paused_until, time.monotonic() + wait)
        self._resume_at = datetime.now(timezone.utc) + timedelta(seconds=wait)
        self._reason = reason

    async def _wait_if_paused(self) -> None:
        status = self.status()
        if status.paused:
            logger.info("Groq requests paused for %ss (%s)", status.wait_seconds, status.reason)
            await asyncio.sleep(status.wait_seconds)
            self.clear()

    def _pace_after_success(self, response: httpx.Response) -> None:
        remaining = _remaining_int(response, "x-ratelimit-remaining-requests")
        tokens = _remaining_int(response, "x-ratelimit-remaining-tokens")
        requests_ok = remaining is None or remaining >= LOW_REQUEST_THRESHOLD
        tokens_ok = tokens is None or tokens >= LOW_TOKEN_THRESHOLD
        if requests_ok and tokens_ok:
            return

        wait = _header_wait_seconds(response, fallback=0.0)
        if wait > 0:
            logger.info(
                "Groq budget low (%s requests, %s tokens remaining); pausing %.1fs",
                remaining,
                tokens,
                wait,
            )
            self._set_pause(wait, "low_budget")

    async def post(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        max_attempts: int = 3,
    ) -> httpx.Response:
        last_wait = 0.0
        async with self._lock:
            for attempt in range(max_attempts):
                await self._wait_if_paused()
                response = await client.post(url, headers=headers, json=json)
                if response.status_code != 429:
                    self._pace_after_success(response)
                    return response

                last_wait = _header_wait_seconds(response, fallback=2 ** (attempt + 1))
                logger.warning("Groq rate limited; pausing %.1fs", last_wait)
                self._set_pause(last_wait, "rate_limit")

            raise GroqRateLimitError(last_wait or MAX_RATE_LIMIT_PAUSE_SECONDS)


limiter = GroqRateLimiter()


def get_rate_limit_status() -> dict[str, Any]:
    return limiter.status().to_dict()
