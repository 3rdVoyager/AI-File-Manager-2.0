"""Token budget tiers based on scan size."""

from dataclasses import dataclass

FAST_SCAN_MODEL = "llama-3.1-8b-instant"


@dataclass(frozen=True)
class ScanTier:
    name: str
    snippet_max_per: int
    content_cap: int
    max_tokens: int
    batch_size: int
    skip_ai_extensions: frozenset[str]


_TIERS = {
    "full": ScanTier("full", snippet_max_per=500, content_cap=1500, max_tokens=400, batch_size=5, skip_ai_extensions=frozenset()),
    "standard": ScanTier("standard", snippet_max_per=200, content_cap=500, max_tokens=300, batch_size=10, skip_ai_extensions=frozenset()),
    "light": ScanTier(
        "light", snippet_max_per=0, content_cap=0, max_tokens=250, batch_size=15,
        skip_ai_extensions=frozenset({
            ".pyc", ".pyo", ".class", ".o", ".obj", ".dll", ".so", ".dylib",
            ".woff", ".woff2", ".ttf", ".eot", ".ico", ".cur",
        }),
    ),
    "minimal": ScanTier(
        "minimal", snippet_max_per=0, content_cap=0, max_tokens=200, batch_size=20,
        skip_ai_extensions=frozenset({
            ".pyc", ".pyo", ".class", ".o", ".obj", ".dll", ".so", ".dylib",
            ".woff", ".woff2", ".ttf", ".eot", ".ico", ".cur",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".mp3", ".wav", ".flac",
            ".zip", ".tar", ".gz", ".7z", ".rar", ".pdf", ".db", ".sqlite",
        }),
    ),
}

BINARY_MEDIA_EXTENSIONS = _TIERS["minimal"].skip_ai_extensions

SKIP_AI_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build",
    ".cache", ".npm", ".yarn", "target", ".gradle", ".idea", ".vs",
}


def tier_for_file_count(count: int) -> ScanTier:
    if count <= 200:
        return _TIERS["full"]
    if count <= 2000:
        return _TIERS["standard"]
    if count <= 10000:
        return _TIERS["light"]
    return _TIERS["minimal"]


def model_for_scan(file_count: int, user_model: str) -> str:
    return FAST_SCAN_MODEL


def estimate_ai_calls(file_count: int) -> dict:
    """Rough estimate of Groq API calls after prefilter rules."""
    tier = tier_for_file_count(file_count)
    skip_ratio = {"full": 0.15, "standard": 0.25, "light": 0.55, "minimal": 0.70}.get(tier.name, 0.3)
    ai_calls = max(0, int(file_count * (1 - skip_ratio)))
    return {
        "file_count": file_count,
        "tier": tier.name,
        "estimated_ai_calls": ai_calls,
        "estimated_skipped": file_count - ai_calls,
    }
