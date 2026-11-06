"""Search by meaning as one service: the state the screen shows, the download thread and the one
background worker that embeds the chunks of open projects.

Nobody is asked (founder's decision, 5 Nov 2026): the model downloads quietly the first time an
open project has text, and from then on at every start until it is in place. A failure waits for
the next start. `status()` reads memory only, as the screen polls it every second. Logs carry
model ids, project ids, counts and timings only: never a query, a chunk text, a project name or a
file name."""

import importlib.util
import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from qsone import copy, settings
from qsone.meaning import download as fetch
from qsone.meaning.host import HostedEmbedder, ModelHost
from qsone.meaning.manifest import EMBEDDER, RETIRED, ModelSpec
from qsone.records import search
from qsone.records.project import RecordsError

log = logging.getLogger("qsone.meaning")

SETTING = "meaning_search"  # "on" once a project had text: the download goes on at every start
WAKE_SECONDS = 5.0
JOIN_SECONDS = 10.0


class ModelFailed(Exception):
    """The search model would not load; the service's state says why."""


def _onnx_loader(spec: ModelSpec, folder: Path) -> object:
    from qsone.meaning import onnx  # the model runtime loads only here, on first use

    return onnx.OnnxEmbedder.load(spec, folder)


def _has_runtime() -> bool:
    return importlib.util.find_spec("onnxruntime") is not None


def _job(state: str, done: int = 0, total: int = 0, reason: dict | None = None) -> dict:
    return {"state": state, "done": done, "total": total, "reason": reason}


class Meaning:
    def __init__(
        self,
        projects,
        root: Path,
        *,
        spec: ModelSpec = EMBEDDER,
        client: Callable[[], httpx.Client] | None = None,
        loader: Callable[[ModelSpec, Path], object] | None = None,
        available: Callable[[], bool] | None = None,
        ram: int | None = None,
        sleep: Callable[[float], object] | None = None,
    ):
        self.root = Path(root)
        self._projects, self._specs = projects, (spec,)
        self._client = client or fetch.default_client
        self._sleep = sleep  # None: the wait between retries ends when quitting
        self._loader = loader or _onnx_loader
        self._available = available or _has_runtime
        self._host = ModelHost(
            {"embedder": lambda: self._load(spec)}, {"embedder": spec.ram_bytes}, ram=ram
        )
        self._embedder = HostedEmbedder(self._host, spec)

        self._lock = threading.Lock()
        self._state, self._reason = "off", None
        self._done, self._total = 0, spec.size
        self._jobs: dict[str, dict] = {}  # project id -> its indexing state
        self._warmed: dict[str, int] = {}  # project id -> its chunks when the model was loaded
        self._quit, self._wake = threading.Event(), threading.Event()
        self._stop_download = threading.Event()
        self._download_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None

    # The model's state

    def start(self) -> None:
        """Works out the state, goes on with a download a project asked for, starts the worker.
        With neither, the worker first looks for a project with text on this computer."""
        if not self._available():
            self._set("unavailable", copy.MEANING_NOT_ON_THIS_COMPUTER)
        elif fetch.installed(self._specs, self.root):
            with self._lock:
                self._state, self._done = "ready", self._total
            self._tidy()
        elif settings.load().get(SETTING) == "on" or self._begun():
            self._begin_download()
        self._worker = threading.Thread(target=self._work, name="qsone-meaning-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Quitting: stops the download and the worker within one batch, then unloads. What came
        is kept, and the next start goes on from there."""
        self._quit.set()
        self._stop_download.set()
        self._wake.set()
        for thread in (self._worker, self._download_thread):
            if thread is not None:
                thread.join(JOIN_SECONDS)
        self._host.unload_all()

    def status(self) -> dict:
        """The GET /meaning body; memory only."""
        opened = [pid for pid, _ in self._projects.opened()]
        with self._lock:
            return {
                "model": {
                    "state": self._state,
                    "done_bytes": self._done,
                    "total_bytes": self._total,
                    "reason": self._reason,
                },
                "indexing": {
                    "projects": {
                        pid: dict(self._jobs.get(pid) or _job("waiting")) for pid in opened
                    },
                },
            }

    def _begun(self) -> bool:
        """Some of the files are here: an earlier download, or files that failed to load."""
        return fetch.remaining(self._specs, self.root) < self._total

    def _set(self, state: str, reason: dict | None = None) -> None:
        with self._lock:
            self._state, self._reason = state, reason

    # The download

    def _want(self) -> None:
        """An open project has text: the download starts, and goes on after a restart."""
        with self._lock:
            if self._state != "off":
                return
        try:
            settings.save(SETTING, "on")
        except OSError:
            log.warning("could not save the download setting")
        self._begin_download()

    def _begin_download(self) -> None:
        with self._lock:
            self._state, self._reason = "downloading", None
            self._download_thread = threading.Thread(
                target=self._fetch, name="qsone-meaning-download", daemon=True
            )
            self._download_thread.start()

    def _fetch(self) -> None:
        def progress(done: int, total: int) -> None:
            with self._lock:
                if self._state in ("downloading", "checking"):
                    self._done = done
                    self._state = "checking" if done >= total else "downloading"

        with self._lock:
            self._done = self._total - fetch.remaining(self._specs, self.root)
        started = time.monotonic()
        try:
            with self._client() as client:
                fetch.download(
                    self._specs,
                    self.root,
                    client=client,
                    stop=self._stop_download,
                    on_progress=progress,
                    sleep=self._sleep,
                )
        except fetch.DownloadStopped:  # quitting
            return
        except fetch.DownloadError as error:
            outcome, reason = "failed", error.text
        except Exception as error:  # a disk or client error; what came is kept
            log.warning("model download failed (%s)", type(error).__name__)
            outcome, reason = "failed", copy.MEANING_DOWNLOAD_FAILED
        else:
            outcome, reason = "ready", None
            log.info("model ready after %.1f s", time.monotonic() - started)
        with self._lock:
            self._state, self._reason = outcome, reason
            if outcome == "ready":
                self._done = self._total
        if outcome == "ready":
            self._tidy()
            self._wake.set()

    def _tidy(self) -> None:
        """Deletes the folders of models One no longer uses; its own cache, nothing else."""
        for old in RETIRED:
            path = self.root / old
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                log.info("model %s: old files deleted", old)

    # The model

    def _load(self, spec: ModelSpec) -> object:
        """Runs inside the model host. A failure changes the state and raises `ModelFailed`."""
        started = time.monotonic()
        try:
            model = self._loader(spec, fetch.folder(spec, self.root))
        except ImportError:
            log.warning("model %s: the model runtime will not load here", spec.id)
            self._set("unavailable", copy.MEANING_NOT_ON_THIS_COMPUTER)
            raise ModelFailed from None
        except Exception as error:
            log.warning("model %s would not load (%s)", spec.id, type(error).__name__)
            # The next start hashes the files again and fetches only what is wrong.
            (fetch.folder(spec, self.root) / fetch.VERIFIED).unlink(missing_ok=True)
            self._set("failed", copy.MEANING_MODEL_FAILED)
            raise ModelFailed from error
        log.info("model %s loaded in %.1f s", spec.id, time.monotonic() - started)
        return model

    def _ready(self) -> bool:
        with self._lock:
            return self._state == "ready"

    def embedder(self) -> search.Embedder | None:
        return self._embedder if self._ready() else None

    # Background indexing

    def wake(self) -> None:
        """A file came in or a project opened."""
        self._wake.set()

    def _held(self) -> bool:
        with self._lock:
            return self._quit.is_set() or self._state != "ready"

    def _work(self) -> None:
        try:
            with self._lock:
                off = self._state == "off"
            if off and self._any_text():
                self._want()
        except Exception as error:  # the look at startup never stops the worker
            log.warning("search by meaning: the startup look failed (%s)", type(error).__name__)
        while not self._quit.is_set():
            self._wake.clear()
            self._host.unload_idle()
            opened = self._projects.opened()
            for pid in set(self._warmed) - {pid for pid, _ in opened}:
                del self._warmed[pid]  # closed: opening it again loads the model again
            for pid, rec in opened:
                if self._quit.is_set():
                    break
                self._look(pid, rec)
            self._wake.wait(WAKE_SECONDS)

    def _any_text(self) -> bool:
        """Has any project here text? Each file is opened on its own and closed again; one that
        will not open or read (damaged, locked) is passed over."""
        for project in self._projects.list():
            if self._quit.is_set():
                return False
            if "error" in project:
                continue
            try:
                rec = self._projects.open_file(project["id"])
            except Exception as error:
                log.warning("project %s: not looked at (%s)", project["id"], type(error).__name__)
                continue
            try:
                if search.vector_counts(rec, self._embedder)[1]:
                    return True
            except Exception as error:
                log.warning("project %s: not looked at (%s)", project["id"], type(error).__name__)
            finally:
                rec.close()
        return False

    def _look(self, pid: str, rec) -> None:
        """Vectors of another model go at once; text asks for the model; then indexing."""
        try:
            search.ensure_index(rec)
            search.drop_stale_vectors(rec, self._embedder)
            done, total = search.vector_counts(rec, self._embedder)
        except RecordsError:
            return self._drop(pid)
        if total:
            self._want()
        if not self._held():
            self._index(pid, rec, done, total)
            if total:
                self._warm(pid, total)

    def _warm(self, pid: str, total: int) -> None:
        """The model loads as soon as an open project has text (opened, or a file read), so the
        first search does not wait for it. Once per project and text: an idle model unloads."""
        if self._warmed.get(pid) == total:
            return
        self._warmed[pid] = total
        try:
            with self._host.use("embedder", background=True):
                pass
        except ModelFailed:  # the state now says why
            pass

    def _index(self, pid: str, rec, done: int, total: int) -> None:
        with self._lock:
            if (self._jobs.get(pid) or {}).get("state") == "failed":
                return  # until the next start
        if done >= total:
            return self._update(pid, _job("ready", done, total))
        self._update(pid, _job("indexing", done, total))

        def progress(n: int) -> None:  # a file that came in meanwhile is embedded too
            self._update(pid, _job("indexing", done + n, max(total, done + n)))

        def should_stop() -> bool:
            return self._held() or not any(r is rec for _, r in self._projects.opened())

        started = time.monotonic()
        try:
            n = search.index_vectors(
                rec, self._embedder, should_stop=should_stop, progress=progress
            )
        except RecordsError:  # the project closed
            return self._drop(pid)
        except ModelFailed:
            return self._update(pid, _job("waiting", done, total))
        except Exception as error:
            log.warning("project %s: indexing failed (%s)", pid, type(error).__name__)
            return self._update(pid, _job("failed", done, total, copy.MEANING_INDEX_FAILED))
        log.info("project %s: %d chunks in %.1f s", pid, n, time.monotonic() - started)
        finished = done + n >= total
        self._update(pid, _job("ready" if finished else "waiting", done + n, max(total, done + n)))

    def _update(self, pid: str, job: dict) -> None:
        with self._lock:
            self._jobs[pid] = job

    def _drop(self, pid: str) -> None:
        with self._lock:
            self._jobs.pop(pid, None)
        self._warmed.pop(pid, None)
