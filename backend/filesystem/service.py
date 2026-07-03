"""Sole gateway for filesystem operations."""

import hashlib
import os
import string
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

MAX_HASH_BYTES = 50 * 1024 * 1024  # 50 MB
CHUNK_SIZE = 65536

WINDOWS_SYSTEM_FILES = {
    "thumbs.db", "desktop.ini", "ehthumbs.db", "ehthumbs_vista.db",
    "folder.jpg", "autorun.inf",
}


@dataclass
class FileMetadata:
    path: str
    filename: str
    size_bytes: int
    size_human: str
    extension: str
    created: str
    modified: str
    modified_at: float
    content_hash: str = ""


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def normalize_path(path: str) -> str:
    return str(Path(path).resolve())


def list_drives() -> list[str]:
    drives = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if os.path.exists(root):
                drives.append(root)
    else:
        drives.append("/")
    return drives


def list_quick_picks() -> list[dict]:
    home = Path.home()
    picks = [
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
        ("Pictures", home / "Pictures"),
    ]
    result = []
    for label, p in picks:
        if p.is_dir():
            result.append({"label": label, "path": str(p.resolve())})
    return result


def list_directory(path: Optional[str] = None) -> dict:
    if not path:
        entries = [{"name": d, "path": d, "is_dir": True} for d in list_drives()]
        return {"current": "", "parent": None, "entries": entries}

    current = normalize_path(path)
    p = Path(current)
    if not p.is_dir():
        raise FileNotFoundError(f"Not a directory: {path}")

    entries = []
    try:
        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if child.name.startswith("."):
                continue
            try:
                entries.append({
                    "name": child.name,
                    "path": str(child.resolve()),
                    "is_dir": child.is_dir(),
                })
            except (OSError, PermissionError):
                continue
    except PermissionError:
        pass

    parent = str(p.parent.resolve()) if p.parent != p else None
    return {"current": current, "parent": parent, "entries": entries}


def traverse_directory(root: str, max_file_size: int = MAX_HASH_BYTES) -> Generator[str, None, None]:
    root_path = Path(normalize_path(root))
    if not root_path.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            full = Path(dirpath) / name
            try:
                if full.is_file() and full.stat().st_size <= max_file_size:
                    yield str(full.resolve())
            except (OSError, PermissionError):
                continue


def get_metadata(path: str) -> FileMetadata:
    p = Path(normalize_path(path))
    stat = p.stat()
    mtime = stat.st_mtime
    return FileMetadata(
        path=str(p),
        filename=p.name,
        size_bytes=stat.st_size,
        size_human=human_size(stat.st_size),
        extension=p.suffix.lower(),
        created=datetime.fromtimestamp(stat.st_ctime).isoformat(),
        modified=datetime.fromtimestamp(mtime).isoformat(),
        modified_at=mtime,
    )


def compute_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def read_text_snippets(path: str, max_per: int = 1000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_per * 3 + 500)
        if len(content) <= max_per * 2:
            return content
        mid = len(content) // 2
        return content[:max_per] + "\n...\n" + content[mid:mid + max_per] + "\n...\n" + content[-max_per:]
    except (OSError, UnicodeError):
        return ""


def delete_to_trash(path: str) -> None:
    import send2trash
    send2trash.send2trash(normalize_path(path))


def open_with_default_app(path: str) -> None:
    target = Path(normalize_path(path))
    if not target.exists():
        raise FileNotFoundError(str(target))
    if not target.is_file():
        raise IsADirectoryError(str(target))

    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def is_system_file(filename: str) -> bool:
    return filename.lower() in WINDOWS_SYSTEM_FILES
