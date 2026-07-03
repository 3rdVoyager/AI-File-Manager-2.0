# AI File Manager 2.0

An AI-powered desktop app that helps you understand, organize, and maintain your files.

## Quick Start

```bash
pip install -r requirements.txt
python start.py
```

Your browser opens automatically. On first launch, follow the setup wizard to add your free Groq API key.

## Features

- Scan folders and analyze files with AI (or heuristics without a key)
- Dashboard with storage breakdown, categories, and recommendations
- Find duplicates, large files, trash candidates, and projects
- Natural language search over your file index
- Safe delete (Recycle Bin) and rename with preview
- All data stays local — no cloud, no accounts

## For End Users

You never need to edit config files. Set your API key in **Settings** inside the app.

## Packaging

```bash
pip install pyinstaller
pyinstaller aifm.spec
```

## Project Structure

- `start.py` — Launches the local server and opens the browser
- `backend/` — Python FastAPI server, API routes, scan pipeline, services, database helpers, and AI provider code
- `frontend/` — Vanilla HTML/CSS/JavaScript single-page UI
- `config/` — Encrypted settings and user preference handling
- `tests/` — Unit and integration tests
- `docs/` — Developer documentation and architecture notes
- `aifm.spec` — PyInstaller recipe for building the Windows app

## For Developers

Start with [`docs/project-map.md`](docs/project-map.md) if you are trying to understand where everything lives and what to edit.

Use [`docs/architecture.md`](docs/architecture.md) for the deeper layer model, local data paths, and safety rules.
