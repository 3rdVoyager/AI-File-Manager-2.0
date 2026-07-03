import asyncio

import httpx

from backend.filesystem.service import FileMetadata
from backend.providers.groq import GroqProvider, _backoff_seconds, _parse_reset_seconds
from backend.providers.groq_limiter import GroqRateLimitError, limiter


def _response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers=headers or {},
        request=httpx.Request("POST", "https://example.test"),
        json={"choices": [{"message": {"content": "{}"}}]},
    )


def _metadata(name: str = "sample.txt") -> FileMetadata:
    return FileMetadata(
        path=f"C:/tmp/{name}",
        filename=name,
        size_bytes=12,
        size_human="12 B",
        extension=".txt",
        created="2026-01-01T00:00:00Z",
        modified="2026-01-01T00:00:00Z",
        modified_at=1.0,
        content_hash="hash",
    )


def test_parse_reset_seconds_units():
    assert _parse_reset_seconds("30s") == 30
    assert _parse_reset_seconds("500ms") == 0.5
    assert _parse_reset_seconds("2m") == 120
    assert _parse_reset_seconds("bad") is None


def test_backoff_uses_retry_after_and_reset_headers():
    assert _backoff_seconds(0, _response(429, {"Retry-After": "45"})) == 45
    assert _backoff_seconds(0, _response(429, {"x-ratelimit-reset-requests": "20s"})) == 20


def test_limiter_sets_shared_pause_on_429(monkeypatch):
    limiter.clear()

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("backend.providers.groq_limiter.asyncio.sleep", no_sleep)

    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def post(self, *_args, **_kwargs):
            self.calls += 1
            return _response(429, {"Retry-After": "10"})

    client = FakeClient()

    async def run():
        try:
            await limiter.post(client, "https://example.test", headers={}, json={}, max_attempts=1)
        except GroqRateLimitError:
            return
        raise AssertionError("Expected GroqRateLimitError")

    asyncio.run(run())
    status = limiter.status()
    assert client.calls == 1
    assert status.paused is True
    assert status.reason == "rate_limit"
    assert status.wait_seconds > 0
    limiter.clear()


def test_batch_failure_does_not_fall_back_to_single_file_calls(monkeypatch):
    provider = GroqProvider(api_key="gsk_test")
    calls = {"single": 0}

    async def fake_post(_payload, max_attempts=4):
        return _response(500)

    async def fake_analyze(_metadata, _content):
        calls["single"] += 1
        raise AssertionError("single-file fallback should not run")

    monkeypatch.setattr(provider, "_post", fake_post)
    monkeypatch.setattr(provider, "analyze", fake_analyze)

    async def run():
        return await provider.analyze_batch([(_metadata("a.txt"), ""), (_metadata("b.txt"), "")])

    results = asyncio.run(run())
    assert calls["single"] == 0
    assert len(results) == 2
    assert all(r.requires_review for r in results)
