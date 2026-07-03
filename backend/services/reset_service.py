"""Factory reset — wipe all user data and return to first-run state."""

import shutil

from config.settings import AppSettings, save_settings
from backend.database.db import clear_all_data
from backend.utils.paths import app_data_dir, settings_path, key_path


def factory_reset() -> None:
    clear_all_data()
    data_dir = app_data_dir()

    for path in (settings_path(), key_path()):
        if path.exists():
            path.unlink()

    reports_dir = data_dir / "reports"
    if reports_dir.exists():
        shutil.rmtree(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    save_settings(AppSettings(setup_complete=False))
