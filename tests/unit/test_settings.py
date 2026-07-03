"""Unit tests for settings encryption."""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from config import settings as cfg


def test_settings_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with mock.patch("config.settings.settings_path", return_value=tmp_path / "settings.json"), \
             mock.patch("config.settings.key_path", return_value=tmp_path / ".key"), \
             mock.patch("config.settings.app_data_dir", return_value=tmp_path):
            s = cfg.AppSettings(api_key="gsk_test1234", model="llama-3.1-8b-instant", setup_complete=True)
            cfg.save_settings(s)
            loaded = cfg.load_settings()
            assert loaded.api_key == "gsk_test1234"
            assert loaded.setup_complete is True
            pub = cfg.settings_public_dict(loaded)
            assert pub["api_key_set"] is True
            assert "1234" in pub["api_key_hint"]
            assert "gsk_test" not in pub.get("api_key_hint", "") or pub["api_key_hint"].startswith("****")
