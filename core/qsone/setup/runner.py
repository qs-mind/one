"""Automatic setup: finds what of the manifest is on this computer and fetches only what is missing.

Nobody presses anything (decisions §17.7). `start()` runs `ensure()` in one background thread when
the app starts; the core answers meanwhile. Each part is, as the contract says:
- `present`: on disk and checked (a bundled part: it answers `--version`);
- `queued`, then `downloading`, through the search models' downloader (`meaning.download`):
  resumable from its `.part` files, checked against each file's SHA-256;
- `waiting_network`: the host could not be reached at all; the thread tries again every
  `AGAIN_SECONDS`, from where it stopped;
- `failed`: three tries reached the host and ended wrong (a damaged file, a refusal, no space);
  `retry()` queues it again;
- `unavailable`: it cannot run on this computer, so it is never fetched; `ready` counts it as done.

`part_path(part_id)` is how other code finds a part that is in place. Logs carry part ids and byte
counts only."""

import importlib.util
import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from qsone import copy, settings
from qsone import phase1_contract as c
from qsone.meaning import download as fetch
from qsone.meaning.manifest import ModelFile
from qsone.records.drawings import find_binary
from qsone.sandbox import runtime
from qsone.setup.manifest import PARTS, Part

log = logging.getLogger("qsone.setup")

TRIES = 3
AGAIN_SECONDS = 30.0  # a part waiting for the network tries again this often
EVENT_SECONDS = 0.5  # bytes are published at most twice a second
JOIN_SECONDS = 10.0
HELPER_SECONDS = 10.0
_MODULE = {"model": "onnxruntime", "sandbox": "wasmtime"}  # what a kind needs to run here


@dataclass(frozen=True)
class _Spec:
    """A part as `meaning.download` takes it."""

    id: str
    revision: str
    files: tuple[ModelFile, ...]
    urls: dict[str, str]

    def url(self, f: ModelFile) -> str:
        return self.urls[f.path]

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


def _spec(part: Part) -> _Spec:
    files = tuple(ModelFile(f.path, f.size, f.sha256) for f in part.files)
    return _Spec(part.folder, part.revision, files, {f.path: f.url for f in part.files})


def can_run(part: Part) -> bool:
    """The model runtime (no wheel for Intel Macs or macOS 13) or the Sandbox's host is here."""
    module = _MODULE.get(part.kind)
    return module is None or importlib.util.find_spec(module) is not None


def answering_helper() -> Path | None:
    """The bundled DWG helper, when it answers `--version` with its name."""
    binary = find_binary()
    if binary is None:
        return None
    try:
        answer = subprocess.run(
            [str(binary), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=HELPER_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        log.warning("dwg-reader: no answer (%s)", type(error).__name__)
        return None
    if answer.returncode != 0:
        return None
    try:
        reader = json.loads(answer.stdout).get("reader")
    except (ValueError, AttributeError):
        return None
    return binary if reader == "qsone-drawings" else None


def _chain(error: BaseException) -> list[BaseException]:
    found: list[BaseException] = []
    while error is not None and error not in found:
        found.append(error)
        error = error.__cause__ or error.__context__
    return found


def _why(error: Exception) -> dict | None:
    """None when the host could not be reached; else why this try failed."""
    chain = _chain(error)
    if any(isinstance(e, httpx.TransportError) for e in chain):
        return None
    if space := next((e for e in chain if isinstance(e, fetch.NoSpace)), None):
        return copy.fill(copy.SETUP_NO_SPACE, size=f"{round(space.need / 1e6)} MB")
    damaged = (e for e in chain if isinstance(e, fetch.DownloadError))
    if any(e.text == copy.MEANING_FILE_DAMAGED for e in damaged):
        return copy.SETUP_FILE_DAMAGED
    return copy.SETUP_REFUSED


@dataclass
class _Now:
    state: str = "queued"
    done: int = 0
    reason: dict | None = None
    tries: int = 0


class Setup:
    def __init__(
        self,
        models: Path,
        sandbox: Path,
        *,
        parts: Sequence[Part] = PARTS,
        client: Callable[[], httpx.Client] | None = None,
        runs_here: Callable[[Part], bool] = can_run,
        helper: Callable[[], Path | None] = answering_helper,
        sleep: Callable[[float], object] | None = None,
        again: float = AGAIN_SECONDS,
        on_change: Callable[[dict], None] | None = None,
    ) -> None:
        self.models, self.sandbox = Path(models), Path(sandbox)
        self.parts = tuple(parts)
        self.on_change = on_change  # gets the SetupState JSON, from any thread
        self._client = client or (lambda: fetch.default_client())  # looked up at each use
        self._runs_here, self._helper = runs_here, helper
        self._sleep, self._again = sleep, again
        self._lock = threading.Lock()  # guards `_now`
        self._ensuring = threading.Lock()  # one pass at a time
        self._looking = threading.Lock()  # the first look, once
        self._now: dict[str, _Now] | None = None  # None: not looked at yet
        self._stop, self._wake = threading.Event(), threading.Event()
        self._thread: threading.Thread | None = None
        self._published = 0.0

    # What other code reads

    def state(self) -> c.SetupState:
        """The GET /setup/parts body; it looks at the disk only the first time."""
        now = self._looked()
        with self._lock:
            parts = [
                c.SetupPart(
                    id=part.id,
                    title=c.Text(**part.title),
                    state=now[part.id].state,
                    done_bytes=now[part.id].done,
                    total_bytes=part.size,
                    affects=c.Text(**part.affects),
                    reason=c.Text(**now[part.id].reason) if now[part.id].reason else None,
                )
                for part in self.parts
            ]
        return c.SetupState(
            ready=all(p.state in ("present", "unavailable") for p in parts), parts=parts
        )

    def part_path(self, part_id: str) -> Path | None:
        """Where a part that is in place is: a model's folder, the unpacked Sandbox runtime, the
        DWG helper. None when it is not in place, cannot run here, or is not in the manifest."""
        part = next((p for p in self.parts if p.id == part_id), None)
        if part is None or not self._runs_here(part):
            return None
        if part.kind == "bundled":
            return self._helper()
        if part.kind == "sandbox":
            return runtime.find(self.sandbox)
        spec = _spec(part)
        return fetch.folder(spec, self.models) if fetch.installed([spec], self.models) else None

    # Running

    def start(self) -> None:
        """Never blocks: the first look and every download run in the setup thread."""
        self._thread = threading.Thread(target=self._run, name="qsone-setup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Quitting: the download stops within a MiB; what came is kept for the next start."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(JOIN_SECONDS)

    def retry(self) -> c.SetupState:
        """Every failed part is queued again with three new tries; the others stay as they are."""
        now = self._looked()
        with self._lock:
            again = [n for n in now.values() if n.state == "failed"]
            for n in again:
                n.state, n.reason, n.tries = "queued", None, 0
        if again:
            self._wake.set()
            self._changed()
        return self.state()

    def ensure(self) -> None:
        """One pass: fetches every part that is queued or waiting for the network, in manifest
        order. Safe to call again: what is present is never fetched twice, and a download that
        stopped goes on from its `.part` files."""
        with self._ensuring:
            now = self._looked()
            for part in self.parts:
                if self._stop.is_set():
                    return
                if now[part.id].state not in ("queued", "waiting_network"):
                    continue
                self._try(part)
                while now[part.id].state == "queued" and not self._stop.is_set():
                    self._try(part)  # a try that ended wrong, before its third

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                self.ensure()
            except Exception as error:  # the setup thread never stops the core
                log.warning("setup pass failed (%s)", type(error).__name__)
            with self._lock:
                waiting = any(n.state == "waiting_network" for n in (self._now or {}).values())
            self._wake.wait(self._again if waiting else None)

    # Looking and fetching

    def _looked(self) -> dict[str, _Now]:
        if self._now is None:
            with self._looking:
                if self._now is None:
                    looked = {part.id: self._look(part) for part in self.parts}
                    with self._lock:
                        self._now = looked
        return self._now

    def _look(self, part: Part) -> _Now:
        if not self._runs_here(part):
            return _Now("unavailable", 0, part.cannot_run)
        if part.kind == "bundled":
            found = self._helper() is not None
            return _Now("present") if found else _Now("unavailable", 0, part.cannot_run)
        if self.part_path(part.id) is not None:
            return _Now("present", part.size)
        return _Now("queued", self._on_disk(part))

    def _on_disk(self, part: Part) -> int:
        return part.size - fetch.remaining([_spec(part)], self._root(part))

    def _root(self, part: Part) -> Path:
        return self.sandbox if part.kind == "sandbox" else self.models

    def _set(self, part: Part, state: str, done: int, reason: dict | None = None) -> None:
        with self._lock:
            now = self._now[part.id]
            now.state, now.done, now.reason = state, done, reason
        self._changed()

    def _try(self, part: Part) -> None:
        self._set(part, "downloading", self._on_disk(part))

        def progress(done: int, total: int) -> None:
            with self._lock:
                self._now[part.id].done = done
            self._changed(bytes_only=True)

        try:
            with self._client() as client:
                if part.kind == "sandbox":
                    files = tuple(
                        runtime.RuntimeFile(f.path, f.url, f.size, f.sha256) for f in part.files
                    )
                    runtime.install(
                        self.sandbox,
                        client=client,
                        stop=self._stop,
                        on_progress=progress,
                        files=files,
                    )
                else:
                    fetch.download(
                        [_spec(part)],
                        self.models,
                        client=client,
                        stop=self._stop,
                        on_progress=progress,
                        sleep=self._sleep,
                    )
        except fetch.DownloadStopped:
            return self._set(part, "queued", self._on_disk(part))
        except Exception as error:
            reason = _why(error)
            if reason is None:
                log.info("%s: the host cannot be reached; waiting", part.id)
                return self._set(part, "waiting_network", self._on_disk(part))
            with self._lock:
                self._now[part.id].tries += 1
                tries = self._now[part.id].tries
            log.warning("%s: try %d failed (%s)", part.id, tries, type(error).__name__)
            if tries >= TRIES:
                return self._set(part, "failed", self._on_disk(part), reason)
            return self._set(part, "queued", self._on_disk(part))
        log.info("%s: %d bytes in place and checked", part.id, part.size)
        self._set(part, "present", part.size)

    def _changed(self, bytes_only: bool = False) -> None:
        if self.on_change is None:
            return
        moment = time.monotonic()
        if bytes_only and moment - self._published < EVENT_SECONDS:
            return
        self._published = moment
        self.on_change(self.state().model_dump(mode="json"))


def default() -> Setup:
    """The app's own places: `<data>/models` and the Sandbox's folder."""
    return Setup(settings.data_dir() / "models", runtime.root())


def part_path(part_id: str) -> Path | None:
    """Where a part that is in place is, for code outside the app's setup (a reader, a tool)."""
    return default().part_path(part_id)
