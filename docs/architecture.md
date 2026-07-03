# AI File Manager 2.0 — Architecture

## Overview

Local desktop app: Python/FastAPI backend + vanilla HTML/CSS/JS frontend.
User double-clicks `start.py` (or packaged `.exe`); browser opens automatically.

## Layers

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Frontend | `frontend/` | Presentation only — calls REST API |
| API | `backend/api/` | HTTP routes, request validation |
| Services | `backend/services/` | Business logic |
| Scanner | `backend/scanner/` | Scan pipeline |
| Filesystem | `backend/filesystem/` | **Only** module that touches OS files |
| Database | `backend/database/` | SQLite schema and queries |
| Providers | `backend/providers/` | AI backends (Groq first) |
| Config | `config/settings.py` | Encrypted user settings in `~/.aifm/` |

## Data

- SQLite: `~/.aifm/app.db`
- Settings: `~/.aifm/settings.json` (API key encrypted)
- Reports: `~/.aifm/reports/*.json`

## Safety

All delete operations use Windows Recycle Bin (`send2trash`).
Rename/delete require preview endpoints before execution.

## Packaging

```bash
pip install pyinstaller
pyinstaller aifm.spec
```

Output: `dist/AI File Manager.exe`
