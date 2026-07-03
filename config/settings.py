"""Load/save user settings with encrypted API key."""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.utils.paths import settings_path, key_path, app_data_dir

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-20b"
GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]

MODEL_LABELS = {
    "openai/gpt-oss-20b": "GPT-OSS 20B (fast, recommended)",
    "openai/gpt-oss-120b": "GPT-OSS 120B (capable)",
    "llama-3.3-70b-versatile": "Llama 3.3 70B (best quality)",
    "llama-3.1-8b-instant": "Llama 3.1 8B (fastest)",
    "mixtral-8x7b-32768": "Mixtral 8x7B",
    "gemma2-9b-it": "Gemma 2 9B",
}


@dataclass
class AppSettings:
    api_key: str = ""
    model: str = DEFAULT_MODEL
    theme: str = "dark"
    setup_complete: bool = False

    def api_key_set(self) -> bool:
        return bool(self.api_key.strip())

    def api_key_hint(self) -> str:
        key = self.api_key.strip()
        if len(key) < 4:
            return ""
        return f"****{key[-4:]}"


def _fernet() -> Fernet:
    kp = key_path()
    app_data_dir()
    if not kp.exists():
        key = Fernet.generate_key()
        kp.write_bytes(key)
    return Fernet(kp.read_bytes())


def load_settings() -> AppSettings:
    path = settings_path()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppSettings()

    settings = AppSettings(
        model=raw.get("model", DEFAULT_MODEL),
        theme=raw.get("theme", "dark"),
        setup_complete=bool(raw.get("setup_complete", False)),
    )
    if settings.model not in GROQ_MODELS:
        settings.model = DEFAULT_MODEL
    enc = raw.get("api_key_enc", "")
    if enc:
        try:
            settings.api_key = _fernet().decrypt(enc.encode()).decode()
        except (InvalidToken, Exception):
            logger.warning("Could not decrypt API key")
    return settings


def save_settings(settings: AppSettings) -> None:
    app_data_dir()
    raw: dict[str, Any] = {
        "model": settings.model,
        "theme": settings.theme,
        "setup_complete": settings.setup_complete,
        "api_key_enc": "",
    }
    if settings.api_key.strip():
        raw["api_key_enc"] = _fernet().encrypt(settings.api_key.strip().encode()).decode()
    settings_path().write_text(json.dumps(raw, indent=2), encoding="utf-8")


def settings_public_dict(settings: AppSettings) -> dict:
    return {
        "model": settings.model,
        "theme": settings.theme,
        "setup_complete": settings.setup_complete,
        "api_key_set": settings.api_key_set(),
        "api_key_hint": settings.api_key_hint(),
        "models": GROQ_MODELS,
        "model_labels": {m: MODEL_LABELS.get(m, m) for m in GROQ_MODELS},
        "data_dir": str(app_data_dir()),
    }
