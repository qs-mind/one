"""Small choices the engineer makes, in settings.json in the app's data folder. Never a key."""

import json
import os
import sys
from pathlib import Path

APP_ID = "app.qsmind.one"  # the desktop's identifier (desktop/tauri.conf.json)


def data_dir() -> Path:
    """The folder Tauri calls the app local data folder; QSONE_DATA_DIR overrides it (tests).

    On Windows it is under Local, never Roaming, so settings, projects and the search models
    never sync with a roaming office profile.
    """
    override = os.environ.get("QSONE_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID


def _file() -> Path:
    return data_dir() / "settings.json"


def load() -> dict:
    """The saved settings; empty when the file is missing or unreadable."""
    try:
        saved = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def save(name: str, value: object) -> None:
    """Raises `OSError` when the file cannot be written."""
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(load() | {name: value}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)  # a crash mid-write never leaves half a file
