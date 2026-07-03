"""Unit tests for filesystem service."""

import os
import tempfile
from pathlib import Path

import pytest

from backend.filesystem import service as fs


def test_human_size():
    assert "KB" in fs.human_size(2048) or "2" in fs.human_size(2048)
    assert fs.human_size(500) == "500 B"


def test_normalize_path():
    with tempfile.TemporaryDirectory() as tmp:
        p = fs.normalize_path(tmp)
        assert Path(p).is_dir()


def test_traverse_and_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        paths = list(fs.traverse_directory(tmp))
        assert len(paths) == 1
        meta = fs.get_metadata(paths[0])
        assert meta.filename == "hello.txt"
        assert meta.size_bytes == 11


def test_compute_hash():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "hashme.txt"
        f.write_text("same content", encoding="utf-8")
        h1 = fs.compute_hash(str(f))
        h2 = fs.compute_hash(str(f))
        assert h1 == h2
        assert len(h1) == 64


def test_open_with_default_app_rejects_missing_file():
    with pytest.raises(FileNotFoundError):
        fs.open_with_default_app(str(Path(tempfile.gettempdir()) / "aifm-missing-file.txt"))


def test_open_with_default_app_rejects_directory():
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(IsADirectoryError):
            fs.open_with_default_app(tmp)


def test_pre_analyze_system_file():
    from backend.scanner.stages.prefilter import pre_analyze_filter
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "desktop.ini"
        f.write_text("[test]", encoding="utf-8")
        result = pre_analyze_filter(str(f))
        assert result is not None
        assert result["category"] == "System"


def test_pre_analyze_installer_is_delete_candidate():
    from backend.scanner.stages.prefilter import pre_analyze_filter
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "setup.msi"
        f.write_bytes(b"installer")
        result = pre_analyze_filter(str(f))
        assert result is not None
        assert result["action"] == "Delete"
        assert result["category"] == "Installers"
        assert result["confidence"] >= 90


def test_pre_analyze_temp_download_is_delete_candidate():
    from backend.scanner.stages.prefilter import pre_analyze_filter
    with tempfile.TemporaryDirectory() as tmp:
        downloads = Path(tmp) / "Downloads"
        downloads.mkdir()
        f = downloads / "video.zip.crdownload"
        f.write_bytes(b"partial")
        result = pre_analyze_filter(str(f))
        assert result is not None
        assert result["action"] == "Delete"
        assert result["category"] == "Downloads"
        assert "type:temp" in result["tags"]


def test_pre_analyze_tmp_file_is_delete_candidate():
    from backend.scanner.stages.prefilter import pre_analyze_filter
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "export.tmp"
        f.write_bytes(b"temporary")
        result = pre_analyze_filter(str(f))
        assert result is not None
        assert result["action"] == "Delete"
        assert result["confidence"] >= 88


def test_pre_analyze_disk_image_is_delete_candidate():
    from backend.scanner.stages.prefilter import pre_analyze_filter
    with tempfile.TemporaryDirectory() as tmp:
        downloads = Path(tmp) / "Downloads"
        downloads.mkdir()
        f = downloads / "tool.iso"
        f.write_bytes(b"disk image")
        result = pre_analyze_filter(str(f))
        assert result is not None
        assert result["action"] == "Delete"
        assert result["subcategory"] == "Disk Image"
