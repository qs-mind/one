"""Search by meaning as one service: the state the screen shows, the download thread and the one
background worker that embeds the chunks of open projects.

`status()` reads memory only, as the screen polls it every second. Logs carry model ids, project
ids, counts and timings only: never a query, a chunk text, a project name or a file name."""

import importlib.util
import logging
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from qsone import copy, settings
from qsone.meaning import download as fetch
from qsone.meaning.host import HostedEmbedder, HostedReranker, ModelHost
from qsone.meaning.manifest import MODELS, ModelSpec
from qsone.records import search
from qsone.records.project import RecordsError

log = logging.getLogger("qsone.meaning")

SETTING = "meaning_search"  # "on" once the engineer pressed Download; "off" after Stop
WAKE_SECONDS = 5.0
JOIN_SECONDS = 10.0


class ModelFailed(Exception):
    """A search model would not load; the service's state says why."""


def _onnx_loader(spec: ModelSpec, folder: Path) -> object:
    from qsone.meaning import onnx  # the model runtime loads only here, on first use

    model = onnx.OnnxEmbedder if spec.kind == "embedder" else onnx.OnnxReranker
    return model.load(spec, folder)


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
        specs: Sequence[ModelSpec] = MODELS,
        client: Callable[[], httpx.Client] = fetch.default_client,
        loader: Callable[[ModelSpec, Path], object] | None = None,
        available: Callable[[], bool] | None = None,
        ram: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.root = Path(root)
        self._projects, self._specs = projects, tuple(specs)
        self._client, self._sleep = client, sleep
        self._loader = loader or _onnx_loader
        self._available = available or _has_runtime
        by_kind = {s.kind: s for s in self._specs}
        self._host = ModelHost(
            {kind: (lambda spec=spec: self._load(spec)) for kind, spec in by_kind.items()},
            {kind: spec.ram_bytes for kind, spec in by_kind.items()},
            ram=ram,
        )
        self._embedder = HostedEmbedder(self._host, by_kind["embedder"])
        self._reranker = HostedReranker(self._host, by_kind["reranker"])

        self._lock = threading.Lock()
        self._starting = threading.Lock()  # one Download press at a time
        self._state, self._reason = "off", None
        self._done, self._total = 0, sum(s.size for s in self._specs)
        self._paused = False
        self._jobs: dict[str, dict] = {}  # project id -> its indexing state
        self._turns: dict[str, int] = {}  # project id -> the latest rerank's number
        self._quit, self._wake = threading.Event(), threading.Event()
        self._stop_download = threading.Event()
        self._download_thread: threading.Thread | None = None
        self._run = object()  # the current download; a finished older one changes nothing
        self._worker: threading.Thread | None = None

    # The model's state

    def start(self) -> None:
        """Works out the state, resumes a download the engineer asked for, starts the worker."""
        if not self._available():
            self._set("unavailable", copy.MEANING_NOT_ON_THIS_COMPUTER)
        elif fetch.installed(self._specs, self.root):
            with self._lock:
                self._state, self._done = "ready", self._total
        elif settings.load().get(SETTING) == "on":
            self._begin_download()
        self._worker = threading.Thread(target=self._work, name="qsone-meaning-worker", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Quitting: stops the download and the worker within one batch, then unloads."""
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
                    "paused": self._paused,
                    "projects": {
                        pid: dict(self._jobs.get(pid) or _job("waiting")) for pid in opened
                    },
                },
            }

    def unavailable(self) -> bool:
        with self._lock:
            return self._state == "unavailable"

    def _set(self, state: str, reason: dict | None = None) -> None:
        with self._lock:
            self._state, self._reason = state, reason

    # The download

    def download(self) -> None:
        """The engineer pressed Download (or Try again): it goes on after a restart until done."""
        try:
            settings.save(SETTING, "on")
        except OSError:
            log.warning("could not save the download setting")
        with self._starting:
            with self._lock:
                if self._state in ("downloading", "checking", "ready", "unavailable"):
                    return
            self._begin_download()

    def stop_download(self) -> None:
        """Keeps what came. A restart does not undo it: the next Download resumes."""
        with self._lock:
            if self._state not in ("downloading", "checking"):
                return
            self._state = "stopped"
            self._stop_download.set()
        try:
            settings.save(SETTING, "off")
        except OSError:
            log.warning("could not save the download setting")

    def _begin_download(self) -> None:
        old = self._download_thread
        if old is not None:
            old.join(JOIN_SECONDS)
            if old.is_alive():  # two downloads must never write the same part file
                log.warning("the stopped download has not ended yet")
                return
        with self._lock:
            self._state, self._reason = "downloading", None
            self._stop_download = threading.Event()
            self._run = run = object()
            self._download_thread = threading.Thread(
                target=self._fetch,
                args=(run, self._stop_download),
                name="qsone-meaning-download",
                daemon=True,
            )
            self._download_thread.start()

    def _fetch(self, run: object, stop: threading.Event) -> None:
        def progress(done: int, total: int) -> None:
            with self._lock:
                if self._run is run and self._state in ("downloading", "checking"):
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
                    stop=stop,
                    on_progress=progress,
                    sleep=self._sleep,
                )
        except fetch.DownloadStopped:
            outcome, reason = "stopped", None
        except fetch.DownloadError as error:
            outcome, reason = "failed", error.text
        except Exception as error:  # a disk or client error; what came is kept
            log.warning("model download failed (%s)", type(error).__name__)
            outcome, reason = "failed", copy.MEANING_DOWNLOAD_FAILED
        else:
            outcome, reason = "ready", None
            log.info("models ready after %.1f s", time.monotonic() - started)
        with self._lock:
            if self._run is not run:
                return
            self._state, self._reason = outcome, reason
            if outcome == "ready":
                self._done = self._total
        if outcome == "ready":
            self._wake.set()

    # The models

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
            # The next Download hashes the files again and fetches only what is wrong.
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

    def reranker(self) -> search.Reranker | None:
        return self._reranker if self._ready() else None

    def rerank_turn(self, project_id: str) -> Callable[[], bool]:
        """Starts a rerank for this project; the answer turns true once a newer one starts."""
        with self._lock:
            turn = self._turns[project_id] = self._turns.get(project_id, 0) + 1
        return lambda: self._quit.is_set() or self._turns.get(project_id) != turn

    # Background indexing

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            for pid, job in list(self._jobs.items()):
                if job["state"] == "failed":
                    del self._jobs[pid]  # tried again
        self._wake.set()

    def wake(self) -> None:
        """A file came in or a project opened."""
        self._wake.set()

    def _held(self) -> bool:
        with self._lock:
            return self._quit.is_set() or self._paused or self._state != "ready"

    def _work(self) -> None:
        while not self._quit.is_set():
            self._wake.clear()
            self._host.unload_idle()
            for pid, rec in self._projects.opened():
                if self._held():
                    break
                self._index(pid, rec)
            self._wake.wait(WAKE_SECONDS)

    def _index(self, pid: str, rec) -> None:
        with self._lock:
            if (self._jobs.get(pid) or {}).get("state") == "failed":
                return  # until Resume
        try:
            done, total = search.vector_counts(rec, self._embedder)
        except RecordsError:
            return self._drop(pid)
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
