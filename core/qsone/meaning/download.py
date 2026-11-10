"""Downloads the search models into `<root>/<model id>/<revision>/`, file by file.

A file arrives as `<file>.part` and resumes over HTTP ranges; it is renamed into place only after
its SHA-256 matches. `verified.json` per model saves rehashing every file at every start. Paths come
only from the manifest, never from a server answer. Logs carry model ids and byte counts only."""

import hashlib
import json
import logging
import os
import shutil
import ssl
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import truststore

from qsone import copy
from qsone.meaning.manifest import ModelFile, ModelSpec

log = logging.getLogger("qsone.meaning.download")

PIECE = 1 << 20  # progress and stop are looked at every MiB
SPARE = 200_000_000  # free space kept beyond the bytes still to come
MOVED_ON = PIECE  # a try that brought this much more starts the count of retries again
VERIFIED = "verified.json"


class DownloadError(Exception):
    def __init__(self, text: dict[str, str]) -> None:
        super().__init__(text["en"])
        self.text = text  # a `copy` pair


class NoSpace(DownloadError):
    """Not enough free space; `need` is the bytes still to come plus `SPARE`."""

    def __init__(self, need: int) -> None:
        super().__init__(copy.fill(copy.MEANING_NO_SPACE, size=f"{round(need / 1e6)} MB"))
        self.need = need


class DownloadStopped(Exception):
    """The stop event was set (the app is quitting); partial files are kept."""


def folder(spec: ModelSpec, root: Path) -> Path:
    return root / spec.id / spec.revision


def _size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _part(path: Path) -> Path:
    return path.with_name(path.name + ".part")


def _verified(spec: ModelSpec, root: Path) -> dict:
    try:
        saved = json.loads((folder(spec, root) / VERIFIED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return saved if isinstance(saved, dict) else {}


def _checked(spec: ModelSpec, f: ModelFile, root: Path, verified: dict) -> bool:
    return verified.get(f.path) == f.sha256 and _size(folder(spec, root) / f.path) == f.size


def installed(specs: Sequence[ModelSpec], root: Path) -> bool:
    """Every file is in `verified.json` and has its size. No hashing."""
    for spec in specs:
        verified = _verified(spec, root)
        if not all(_checked(spec, f, root, verified) for f in spec.files):
            return False
    return True


def remaining(specs: Sequence[ModelSpec], root: Path) -> int:
    """Bytes still to come; a file of the right size counts as here, a `.part` as far as it got."""
    left = 0
    for spec in specs:
        for f in spec.files:
            path = folder(spec, root) / f.path
            if _size(path) != f.size:
                part = _size(_part(path)) or 0
                left += f.size - (part if part <= f.size else 0)
    return left


def default_client() -> httpx.Client:
    """The system's trust store, so office networks that inspect TLS work as in the browser."""
    return httpx.Client(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
        headers={"User-Agent": "QS Mind One (qsmind.app)"},
    )


def _hash(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as file:
        while piece := file.read(PIECE):
            h.update(piece)
    return h


class _Fetch:
    """One file into its `.part`; `have` and `hash` always match the bytes on disk."""

    def __init__(self, spec: ModelSpec, f: ModelFile, path: Path) -> None:
        self.spec, self.url, self.f, self.path, self.part = spec, spec.url(f), f, path, _part(path)
        if (_size(self.part) or 0) > f.size:
            self.part.unlink()
        self.have, self.hash = -1, hashlib.sha256()  # -1: not looked at yet

    def _sync(self) -> None:
        """The part as it stands, hashed; only at the start or after a write failed half-way."""
        on_disk = _size(self.part) or 0
        if on_disk != self.have:
            self.have = on_disk
            self.hash = _hash(self.part) if on_disk else hashlib.sha256()

    def once(self, client: httpx.Client, stop: threading.Event, progress: Callable[[int], None]):
        self._sync()
        headers = {"Range": f"bytes={self.have}-"} if self.have else {}
        with client.stream("GET", self.url, headers=headers) as answer:
            if answer.status_code == 416 and self.have == self.f.size:
                return  # the part was already whole
            if answer.status_code == 200:
                self.have, self.hash, mode = 0, hashlib.sha256(), "wb"  # the range was ignored
            elif answer.status_code == 206 and self.have:
                mode = "ab"
            else:
                log.warning("model %s: HTTP %s", self.spec.id, answer.status_code)
                raise DownloadError(copy.MEANING_DOWNLOAD_FAILED)
            self.part.parent.mkdir(parents=True, exist_ok=True)
            with self.part.open(mode, buffering=PIECE) as out:
                mark = self.have
                for piece in answer.iter_bytes():
                    out.write(piece)
                    self.hash.update(piece)
                    self.have += len(piece)
                    if self.have > self.f.size:
                        break  # longer than pinned: the check below deletes it
                    if self.have - mark >= PIECE or self.have == self.f.size:
                        mark = self.have
                        progress(self.have)
                        if stop.is_set():
                            raise DownloadStopped
                out.flush()
                os.fsync(out.fileno())

    def run(self, client, stop, progress, retries: int, sleep) -> None:
        """Network errors are retried, each try resuming from the part; then the checksum. A try
        that moved on by `MOVED_ON` bytes counts the retries from nought again. The wait between
        tries ends at once when `stop` is set."""
        tries = 0
        while True:
            if stop.is_set():
                raise DownloadStopped
            before = max(self.have, 0)
            try:
                self.once(client, stop, progress)
                break
            except (httpx.TransportError, OSError) as error:
                if self.have - before >= MOVED_ON:
                    tries = 0
                if tries >= retries:
                    log.warning(
                        "model %s: gave up at %d bytes (%s)",
                        self.spec.id,
                        self.have,
                        type(error).__name__,
                    )
                    raise DownloadError(copy.MEANING_DOWNLOAD_FAILED) from error
                tries += 1
                (sleep or stop.wait)(2**tries)
        self.finish()

    def finish(self) -> None:
        if self.have != self.f.size or self.hash.hexdigest() != self.f.sha256:
            self.part.unlink(missing_ok=True)
            raise DownloadError(copy.MEANING_FILE_DAMAGED)
        os.replace(self.part, self.path)


def _write_verified(spec: ModelSpec, root: Path) -> None:
    path = folder(spec, root) / VERIFIED
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({f.path: f.sha256 for f in spec.files}), encoding="utf-8")
    os.replace(temporary, path)


_LOCKS: dict[Path, threading.Lock] = {}
_LOCKS_LOCK = threading.Lock()


def _holding(path: Path) -> threading.Lock:
    """One download per folder at a time: automatic setup and search by meaning share one."""
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(path.resolve(), threading.Lock())


def download(
    specs: Sequence[ModelSpec],
    root: Path,
    *,
    client: httpx.Client,
    stop: threading.Event,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    retries: int = 3,
    sleep: Callable[[float], object] | None = None,
) -> None:
    """Fetches what is missing, in manifest order. `on_progress(done, total)` counts all files.
    Between retries it waits on `stop` (or calls `sleep`, for tests).

    Raises `DownloadError` (a `copy` pair in `.text`; `NoSpace` for the disk) or
    `DownloadStopped`."""
    root.mkdir(parents=True, exist_ok=True)
    total = sum(spec.size for spec in specs)
    left = remaining(specs, root)
    if shutil.disk_usage(root).free < left + SPARE:
        raise NoSpace(left + SPARE)
    done = 0  # bytes of the files already finished
    for spec in specs:
        with _holding(folder(spec, root)):  # read again inside: another may have finished
            verified = _verified(spec, root)
            changed = False
            for f in spec.files:
                path = folder(spec, root) / f.path
                if not _checked(spec, f, root, verified):
                    changed = True
                    if _size(path) == f.size and _hash(path).hexdigest() == f.sha256:
                        log.info("model %s: a file put in place by hand is accepted", spec.id)
                    else:
                        path.unlink(missing_ok=True)
                        progress = lambda n, done=done: on_progress(done + n, total)  # noqa: E731
                        _Fetch(spec, f, path).run(client, stop, progress, retries, sleep)
                done += f.size
            if changed:
                _write_verified(spec, root)
                log.info("model %s: %d bytes in place and checked", spec.id, spec.size)
    on_progress(total, total)
