"""Pre-analyze deterministic filters."""

from pathlib import Path
from typing import Optional

from backend.filesystem.service import is_system_file
from backend.scanner.token_budget import BINARY_MEDIA_EXTENSIONS, SKIP_AI_DIR_NAMES

TINY_CONFIG_EXTENSIONS = {
    ".gitignore", ".dockerignore", ".editorconfig", ".env", ".env.example",
    ".flake8", ".pylintrc", ".prettierrc", ".eslintrc", ".toml", ".ini", ".cfg", ".conf",
}

ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}
INSTALLER_EXTENSIONS = {
    ".exe", ".msi", ".msix", ".msp", ".cab", ".dmg", ".pkg", ".deb", ".rpm",
    ".appx", ".appxbundle",
}
DISK_IMAGE_EXTENSIONS = {".iso", ".img"}
TEMP_DOWNLOAD_EXTENSIONS = {".tmp", ".temp", ".bak", ".old", ".swp", ".crdownload", ".part", ".download"}
CRASH_DUMP_EXTENSIONS = {".dmp", ".mdmp"}

MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg"}

EXT_CATEGORY = {
    ".py": ("Programming", "Python"), ".js": ("Programming", "JavaScript"),
    ".ts": ("Programming", "TypeScript"), ".tsx": ("Programming", "TypeScript"),
    ".jsx": ("Programming", "JavaScript"), ".java": ("Programming", "Java"),
    ".cpp": ("Programming", "C++"), ".c": ("Programming", "C"), ".h": ("Programming", "Header"),
    ".go": ("Programming", "Go"), ".rs": ("Programming", "Rust"),
    ".html": ("Programming", "Web"), ".css": ("Programming", "Stylesheet"),
    ".json": ("Documents", "JSON"), ".yaml": ("Documents", "YAML"), ".yml": ("Documents", "YAML"),
    ".md": ("Documents", "Markdown"), ".txt": ("Documents", "Text"),
    ".pdf": ("Documents", "PDF"), ".doc": ("Documents", "Word"), ".docx": ("Documents", "Word"),
}


def _in_skip_dir(path: str) -> bool:
    parts = {p.lower() for p in Path(path).parts}
    return bool(parts & SKIP_AI_DIR_NAMES)


def _path_parts(path: Path) -> set[str]:
    return {part.lower() for part in path.parts}


def _in_cleanup_location(path: Path) -> bool:
    parts = _path_parts(path)
    cleanup_parts = {"downloads", "temp", "tmp", "cache", "installer", "installers"}
    return bool(parts & cleanup_parts) or any("temp" in part or "cache" in part for part in parts)


def _in_log_location(path: Path) -> bool:
    parts = _path_parts(path)
    return bool(parts & {"log", "logs", "temp", "tmp"}) or any("log" in part or "temp" in part for part in parts)


def pre_analyze_filter(path: str, tier_skip_extensions: frozenset[str] | None = None) -> Optional[dict]:
    p = Path(path)
    name_lower = p.name.lower()
    ext = p.suffix.lower()

    if _in_skip_dir(path):
        cat, sub = EXT_CATEGORY.get(ext, ("System", "Cache"))
        return _result(f"Cache/dependency path: {p.name}", cat, sub, "Keep", 90,
                       "Inside node_modules, .git, or similar — skipped AI.", ["type:cache"])

    if is_system_file(name_lower):
        return _result("Windows system file", "System", "Config", "Keep", 100,
                        "Recognized system file; no AI needed.", ["lifecycle:transient", "type:temp"])

    try:
        size = p.stat().st_size
    except OSError:
        return None

    if ext in TINY_CONFIG_EXTENSIONS and size < 100:
        return _result(f"Tiny config file ({size} B)", "System", "Config", "Keep", 90,
                        "Small configuration file.", ["type:config"])

    if ext in INSTALLER_EXTENSIONS:
        return _result(f"Installer: {p.name}", "Installers", "Package", "Delete", 90,
                        "Software installer.", ["lifecycle:transient", "type:installer"])

    if name_lower.startswith("setup") and ext == ".exe":
        return _result(f"Installer: {p.name}", "Installers", "Package", "Delete", 92,
                        "Setup executable.", ["lifecycle:transient", "type:installer"])

    if "installer" in name_lower and ext in {".exe", ".msi", ".msix", ".pkg", ".dmg"}:
        return _result(f"Installer: {p.name}", "Installers", "Package", "Delete", 92,
                        "Installer package.", ["lifecycle:transient", "type:installer"])

    if ext in DISK_IMAGE_EXTENSIONS:
        confidence = 90 if _in_cleanup_location(p) else 85
        return _result(f"Disk image: {p.name}", "Installers", "Disk Image", "Delete", confidence,
                        "Mountable installer image.", ["lifecycle:transient", "type:disk-image"])

    if ext in TEMP_DOWNLOAD_EXTENSIONS:
        confidence = 92 if _in_cleanup_location(p) else 88
        return _result(f"Temporary file: {p.name}", "Downloads", "Temporary", "Delete", confidence,
                        "Temporary or partial download.", ["lifecycle:transient", "type:temp"])

    if name_lower.startswith("~$"):
        return _result(f"Office lock file: {p.name}", "Documents", "Temporary", "Delete", 90,
                        "Temporary Office lock file.", ["lifecycle:transient", "type:temp"])

    if ext in CRASH_DUMP_EXTENSIONS:
        return _result(f"Crash dump: {p.name}", "System", "Crash Dump", "Delete", 85,
                        "Debug crash dump.", ["lifecycle:transient", "type:crash-dump"])

    if name_lower.endswith((".log.1", ".log.bak")) or (ext == ".log" and _in_log_location(p)):
        return _result(f"Log file: {p.name}", "System", "Log", "Delete", 80,
                        "Rotated or temporary log.", ["lifecycle:transient", "type:log"])

    if ext in ARCHIVE_EXTENSIONS:
        return _result(f"Archive: {p.name}", "Data", "Archive", "Review", 95,
                        "Archive container.", ["type:archive"])

    screenshot_names = ("screenshot", "screen shot", "snip")
    if any(s in name_lower for s in screenshot_names) and ext in (".png", ".jpg", ".jpeg"):
        return _result(f"Screenshot: {p.name}", "Images", "Screenshot", "Review", 80,
                        "Likely screenshot.", ["type:screenshot"])

    if tier_skip_extensions and ext in tier_skip_extensions:
        cat, sub = _ext_heuristic(ext)
        return _result(f"{sub}: {p.name}", cat, sub, "Review", 75,
                        f"Classified by extension ({ext}) — no AI.", ["type:extension"])

    if ext in MEDIA_EXTENSIONS:
        return _result(f"Image: {p.name}", "Images", "Image", "Keep", 80,
                        "Image file classified by extension.", ["type:image"])

    if ext in VIDEO_EXTENSIONS:
        return _result(f"Video: {p.name}", "Videos", "Video", "Keep", 80,
                        "Video file classified by extension.", ["type:video"])

    if ext in AUDIO_EXTENSIONS:
        return _result(f"Audio: {p.name}", "Downloads", "Audio", "Keep", 75,
                        "Audio file classified by extension.", ["type:audio"])

    if ext in BINARY_MEDIA_EXTENSIONS and ext not in MEDIA_EXTENSIONS:
        cat, sub = _ext_heuristic(ext)
        return _result(f"{sub}: {p.name}", cat, sub, "Review", 70,
                        "Binary/media file — extension heuristic.", ["type:binary"])

    if size > 10 * 1024 * 1024 and ext in {".txt", ".log", ".csv", ".json", ".xml", ".md"}:
        cat, sub = EXT_CATEGORY.get(ext, ("Documents", "Large"))
        return _result(f"Large text file: {p.name}", cat, sub, "Review", 70,
                        "File over 10 MB — metadata-only classification.", ["type:large"])

    return None


def _ext_heuristic(ext: str) -> tuple[str, str]:
    return EXT_CATEGORY.get(ext, ("Other", ext.lstrip(".") or "Unknown"))


def _result(summary, category, subcategory, action, confidence, reasoning, tags) -> dict:
    return {
        "summary": summary,
        "category": category,
        "subcategory": subcategory,
        "project": "",
        "tags": tags,
        "importance": 3,
        "sentimental_value": 1,
        "lifecycle": "Transient" if action == "Delete" else "Active",
        "action": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "requires_review": False,
        "prefiltered": True,
    }
