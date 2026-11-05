"""Find the engineer's own Claude Code for the first launch (decision 25).

`claude` is looked for on PATH, then in its usual install places: `~/.claude/local/`,
`~/.local/bin/` and the npm global folder. Then `claude --version` runs, for at most 5 seconds.
That only proves it is there: the sign-in is proven by the AI Connector's own check
(`connectors.check("claude-code")`). One never reads Claude Code's credentials.

On Windows only `claude.exe` counts: the Subscription Link cannot run npm's `claude.cmd`.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

VERSION_TIMEOUT = 5  # seconds
WINDOWS = sys.platform == "win32"
NAME = "claude.exe" if WINDOWS else "claude"
SYSTEM_FOLDERS: tuple[Path, ...] = () if WINDOWS else (Path("/usr/local/bin"),)  # npm's default

_VERSION = re.compile(r"[0-9][0-9.]{0,31}")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console pops up


def _usual_places() -> list[Path]:
    home = Path.home()
    found = [home / ".claude" / "local", home / ".local" / "bin"]
    prefix = os.environ.get("NPM_CONFIG_PREFIX")
    if prefix:
        found.append(Path(prefix) if WINDOWS else Path(prefix) / "bin")
    if WINDOWS and os.environ.get("APPDATA"):
        found.append(Path(os.environ["APPDATA"]) / "npm")
    found.append(home / ".npm-global" / "bin")
    return [*found, *SYSTEM_FOLDERS]


def _runnable(path: Path) -> bool:
    return path.is_file() and (WINDOWS or os.access(path, os.X_OK))


def on_path() -> Path | None:
    """`claude` from PATH alone, as the Subscription Link finds it without a saved path."""
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if folder and Path(folder).is_absolute() and _runnable(Path(folder) / NAME):
            return Path(folder) / NAME
    return None


def _version(path: Path) -> str | None:
    try:
        done = subprocess.run(
            [str(path), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=VERSION_TIMEOUT,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    words = done.stdout.decode("utf-8", "replace").split() if done.returncode == 0 else []
    return words[0] if words and _VERSION.fullmatch(words[0]) else None


def find_claude() -> tuple[Path | None, str | None]:
    """(path, version). The version is None when `--version` fails or says something else."""
    path = on_path()
    if path is None:
        path = next((p / NAME for p in _usual_places() if _runnable(p / NAME)), None)
    if path is None:
        return None, None
    return path, _version(path)
