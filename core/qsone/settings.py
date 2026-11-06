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
    _write(load() | {name: value})


def remove(name: str) -> None:
    """Raises `OSError` when the file cannot be written."""
    saved = load()
    if name in saved:
        del saved[name]
        _write(saved)


def _write(values: dict) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)  # a crash mid-write never leaves half a file


def ai() -> dict:
    """The "ai" part: Standard Link entries, the model for each role, and entered prices."""
    saved = load().get("ai")
    return saved if isinstance(saved, dict) else {}


def save_ai(part: str, value: object) -> None:
    """Raises `OSError` when the file cannot be written."""
    save("ai", ai() | {part: value})


def map_auto_usd():
    """Per-drop automatic Project Map allowance, in exact USD."""
    from decimal import Decimal, InvalidOperation

    try:
        value = Decimal(str(load().get("map_auto_usd", "0.50")))
        return value if value.is_finite() and value >= 0 else Decimal("0.50")
    except InvalidOperation:
        return Decimal("0.50")


def save_map_auto_usd(value: str):
    """Persist an exact, nonnegative per-drop allowance; never accept a JSON float."""
    import re

    if not isinstance(value, str) or not re.fullmatch(r"\d{1,12}(?:\.\d{1,6})?", value):
        raise ValueError("map_auto_usd")
    save("map_auto_usd", value)
