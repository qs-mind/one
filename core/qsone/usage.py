"""Usage Stats (decision 18): a few allow-listed counts and crash reports, sent to QS Mind's own
Umami, only after the engineer says yes.

- Off until the engineer says yes. `is_on()` is None until asked; nothing is queued or sent
  then, nor after "no". Turning it off empties the queue and sends nothing more, not even the
  "off" itself.
- Each event has fixed keys (`EVENTS`). A value is a number, a boolean, a value from a fixed
  list, or a short code (`^[A-Za-z0-9_.:-]{1,80}$`: a version, a class name, `module:line`).
  Anything else is refused in code and logged by the event's name only. So no project name,
  file name, chat text, number from the work, key, email or Desk name can go out: an AI-built
  Desk name can hold a client's name.
- A crash report is the exception's class and the deepest frame inside `qsone`, as
  module:line. Never its message, never a path.
- The queue is `<data>/usage-queue.jsonl`, at most 200 events (the newest), sent every
  5 minutes. Offline, it waits; a refusal (4xx) drops it.
- The User-Agent names the system and One's version, so Umami counts systems and does not take
  One for a bot.
"""

import json
import logging
import os
import platform
import re
import ssl
import sys
import threading
import traceback
from contextlib import suppress
from pathlib import Path

import httpx
import truststore

import qsone
from qsone import settings
from qsone.journey import setup_state

log = logging.getLogger("qsone.usage")

ENDPOINT = "https://stats.qsmind.app/api/send"  # QSONE_USAGE_ENDPOINT overrides it (tests)
WEBSITE_ID = ""  # Umami's id for One, from O2; QSONE_USAGE_WEBSITE_ID overrides it
HOSTNAME = "one.qsmind.app"
QUEUE_FILE = "usage-queue.jsonl"
QUEUE_MAX = 200
EVERY = 5 * 60  # seconds between sends
SETTING = "usage_stats"

_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_CORE_WHERE = re.compile(r"^qsone(\.\w+)*:\d+$")
_WHERE = {
    "screen": re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*\.(tsx|ts|js):\d+$"),  # Chat.tsx:12
    "shell": re.compile(r"^qs_mind_one(::\w+)*:\d+$"),  # the crate, e.g. qs_mind_one::core:120
    "core": _CORE_WHERE,
}

EVENTS: dict[str, dict[str, type | tuple]] = {
    "app_start": {
        "version": str,
        "os": ("windows", "macos", "linux"),
        "arch": ("x64", "arm64"),
        "language": ("ar", "en"),
    },
    "setup_step": {"step": setup_state.STEPS, "state": ("done", "skipped")},
    "ai_link": {"via": ("api_key", "claude_code", "standard", "none")},
    "project_new": {"files": int, "zips": int, "from_folder": bool},
    "brief_done": {
        "desks": int,
        "specialists": int,
        "off_desk": bool,
        "cost_usd_cents": int,
        "minutes": int,
    },
    "project_archived": {},
    "backup_run": {"projects": int, "ok": bool},
    "update": {"from": str, "to": str, "ok": bool},
    "crash": {"from": ("core", "screen", "shell"), "kind": str, "where": str, "version": str},
    "core_stopped": {"code": int},
}

_lock = threading.RLock()


def _fits(kind: type | tuple, value: object) -> bool:
    if isinstance(kind, tuple):
        return isinstance(value, str) and value in kind
    if kind is int:
        return type(value) is int and -(2**31) <= value < 2**31
    if kind is bool:
        return type(value) is bool
    return isinstance(value, str) and bool(_CODE.fullmatch(value))


def valid(name: str, data: dict) -> bool:
    """True when `data` is exactly what event `name` allows."""
    schema = EVENTS.get(name)
    if schema is None or set(data) != set(schema):
        return False
    if not all(_fits(schema[key], value) for key, value in data.items()):
        return False
    if name == "crash":
        return bool(_WHERE[data["from"]].fullmatch(data["where"]))
    return True


# On or off -------------------------------------------------------------------------------------


def is_on() -> bool | None:
    """True or False as the engineer answered; None before they were asked."""
    saved = settings.load().get(SETTING)
    return saved if isinstance(saved, bool) else None


def set_on(on: bool) -> None:
    """Raises `OSError` when settings.json cannot be written. Off empties the queue."""
    with _lock:
        settings.save(SETTING, on)
        if not on:
            _queue_file().unlink(missing_ok=True)


# The queue -------------------------------------------------------------------------------------


def _queue_file() -> Path:
    return settings.data_dir() / QUEUE_FILE


def _read() -> list[dict]:
    try:
        lines = _queue_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and valid(event.get("name", ""), event.get("data", {})):
            found.append(event)
    return found


def _write(events: list[dict]) -> None:
    path = _queue_file()
    if not events:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    body = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events[-QUEUE_MAX:])
    temporary.write_text(body, encoding="utf-8")
    temporary.replace(path)


def track(name: str, **data) -> None:
    """Queues one event when Usage Stats are on and it is allowed. Never raises; before the
    engineer said yes it does nothing, and says nothing either."""
    try:
        if is_on() is not True:
            return
        if not valid(name, data):
            log.warning("Usage Stats: event %s refused", name if name in EVENTS else "(unknown)")
            return
        with _lock:
            if is_on() is not True:
                return
            event = {"name": name, "data": data, "language": setup_state.language()}
            _write([*_read(), event])
    except Exception:
        log.warning("Usage Stats: event %s not queued", name if name in EVENTS else "(unknown)")


def _where(error: BaseException) -> str:
    """The deepest frame inside `qsone`, as module:line; "qsone:0" when there is none."""
    found = "qsone:0"
    for frame, line in traceback.walk_tb(error.__traceback__):
        module = frame.f_globals.get("__name__", "")
        if isinstance(module, str) and _CORE_WHERE.fullmatch(f"{module}:{line}"):
            found = f"{module}:{line}"
    return found


def crash(error: BaseException, origin: str = "core") -> None:
    """A crash report: the class and where in our code, never the message or a path."""
    kind = type(error).__name__
    track(
        "crash",
        **{
            "from": origin,
            "kind": kind if _CODE.fullmatch(kind) else "Exception",
            "where": _where(error),
            "version": qsone.__version__,
        },
    )


def app_start() -> None:
    machine = platform.machine().lower()
    track(
        "app_start",
        version=qsone.__version__,
        os=_os(),
        arch="arm64" if machine in ("arm64", "aarch64") else "x64",
        language=setup_state.language(),
    )


def core_stopped(data_dir: Path) -> None:
    """The last run's core died while the window was open: the shell left its exit code."""
    path = Path(data_dir) / "last-core-exit.json"
    try:
        code = json.loads(path.read_text(encoding="utf-8")).get("code")
    except (OSError, ValueError, AttributeError):
        return
    finally:
        with suppress(OSError):
            path.unlink(missing_ok=True)
    track("core_stopped", code=code if type(code) is int else -1)  # -1: a signal ended it


VERSION_SETTING = "version"  # the version of One that started last
UPDATE_SETTING = "update_to"  # the version an update was about to install (/app/prepare-update)


def updated() -> None:
    """At the core's start, after an update: the `update` event, from the versions in
    settings.json. A new version means the update installed; the same version with an update
    still pending means it failed and One came back on this one. Never raises."""
    now = qsone.__version__
    saved = settings.load()
    before, pending = saved.get(VERSION_SETTING), saved.get(UPDATE_SETTING)
    if isinstance(before, str) and before != now:
        track("update", **{"from": before, "to": now, "ok": True})
    elif isinstance(pending, str) and pending != now:
        track("update", **{"from": now, "to": pending, "ok": False})
    with suppress(OSError):
        if before != now:
            settings.save(VERSION_SETTING, now)
        if pending is not None:
            settings.remove(UPDATE_SETTING)


def install_hooks() -> None:
    """Crashes outside a request: the main thread's and every other thread's."""
    before_sys, before_thread = sys.excepthook, threading.excepthook

    def on_crash(kind, error, tb):
        crash(error)
        before_sys(kind, error, tb)

    def on_thread_crash(args):
        if args.exc_value is not None:
            crash(args.exc_value)
        before_thread(args)

    sys.excepthook = on_crash
    threading.excepthook = on_thread_crash


# Sending ---------------------------------------------------------------------------------------


def _os() -> str:
    if sys.platform == "win32":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def user_agent() -> str:
    system = {
        "windows": "Windows NT 10.0; Win64; x64",
        "macos": "Macintosh; Intel Mac OS X 10_15_7",
        "linux": "X11; Linux x86_64",
    }[_os()]
    return f"Mozilla/5.0 ({system}) QSMindOne/{qsone.__version__}"


class Sender:
    """Sends the queue every 5 minutes, in its own thread."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="usage-stats", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(EVERY):
            self.flush()

    def flush(self) -> int:
        """Sends what is queued; returns how many Umami took. Never raises. The queue is taken
        out while it is sent, so `track` never waits on the network."""
        website = os.environ.get("QSONE_USAGE_WEBSITE_ID") or WEBSITE_ID
        endpoint = os.environ.get("QSONE_USAGE_ENDPOINT") or ENDPOINT
        with _lock:
            if is_on() is not True or not website:
                return 0
            events = _read()
            _write([])
        sent = 0
        client = self._client or httpx.Client(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), timeout=20.0
        )
        try:
            while events and is_on() is True:
                answer = client.post(
                    endpoint,
                    json=_body(website, events[0]),
                    headers={"User-Agent": user_agent()},
                )
                if 400 <= answer.status_code < 500:
                    log.warning("Usage Stats refused (%s): queue dropped", answer.status_code)
                    events = []
                elif answer.status_code < 300:
                    events.pop(0)
                    sent += 1
                else:
                    break  # Umami is down: the rest waits for the next round
        except Exception:  # offline, or anything else: the rest waits
            log.warning("Usage Stats: not sent now")
        finally:
            if self._client is None:
                client.close()
            with _lock:
                if is_on() is True and events:
                    _write([*events, *_read()])
        return sent


def _body(website: str, event: dict) -> dict:
    """Umami's own shape for an event."""
    return {
        "type": "event",
        "payload": {
            "website": website,
            "hostname": HOSTNAME,
            "url": "/app",
            "name": event["name"],
            "data": event["data"],
            "language": event["language"],
        },
    }
