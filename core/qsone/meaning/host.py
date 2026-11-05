"""The model host: loads the search model only when it is needed, keeps it within a RAM budget,
unloads it when idle, and lets a search go before background work.

The loaders are plain callables, so nothing here imports the model runtime.
"""

import ctypes
import gc
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from qsone.meaning.manifest import ModelSpec

BUDGET_SHARE = 0.25  # of the computer's memory
IDLE_SECONDS = {"embedder": 600.0}
SLICE = 4  # background work gives way to a search after each slice


def total_ram() -> int:
    """The computer's memory in bytes."""
    if sys.platform == "win32":

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        return int(status.ullTotalPhys)
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def release_memory() -> None:
    """Hand freed memory back to the system after a model is dropped."""
    gc.collect()
    if sys.platform.startswith("linux"):
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):  # not glibc
            pass


class ModelHost:
    """One model user at a time. A background caller waits while any search is waiting."""

    def __init__(
        self,
        loaders: dict[str, Callable[[], object]],
        sizes: dict[str, int],
        *,
        ram: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._loaders, self._sizes, self._clock = loaders, sizes, clock
        self._budget = (ram if ram is not None else total_ram()) * BUDGET_SHARE
        self._cond = threading.Condition()
        self._busy = False
        self._foreground_waiting = 0
        self._models: dict[str, object] = {}
        self._last_use: dict[str, float] = {}

    @contextmanager
    def use(self, kind: str, *, background: bool = False) -> Iterator[object]:
        with self._cond:
            if not background:
                self._foreground_waiting += 1
            try:
                self._cond.wait_for(
                    lambda: not self._busy and (not background or not self._foreground_waiting)
                )
            finally:
                if not background:
                    self._foreground_waiting -= 1
            self._busy = True
        try:
            yield self._load(kind)
        finally:
            with self._cond:
                if kind in self._models:
                    self._last_use[kind] = self._clock()
                self._busy = False
                self._cond.notify_all()

    def _load(self, kind: str) -> object:
        """Runs while this caller holds the host."""
        if kind in self._models:
            return self._models[kind]
        if sum(self._sizes[k] for k in self._models) + self._sizes[kind] > self._budget:
            self._drop(list(self._models))
        model = self._loaders[kind]()
        self._models[kind] = model
        return model

    def _drop(self, kinds: list[str]) -> None:
        for kind in kinds:
            del self._models[kind]
            self._last_use.pop(kind, None)
        if kinds:
            release_memory()

    def unload_idle(self) -> None:
        """Unload models idle longer than their IDLE_SECONDS; skipped while a model is in use."""
        with self._cond:
            if self._busy:
                return
            now = self._clock()
            self._drop(
                [k for k in self._models if now - self._last_use.get(k, now) > IDLE_SECONDS[k]]
            )

    def unload_all(self) -> None:
        with self._cond:
            self._cond.wait_for(lambda: not self._busy)
            self._drop(list(self._models))

    def loaded(self) -> frozenset[str]:
        return frozenset(self._models)


class HostedEmbedder:
    """search.Embedder that loads nothing until it is used."""

    def __init__(self, host: ModelHost, spec: ModelSpec):
        self._host, self.name, self.dims = host, spec.name, spec.dims

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), SLICE):
            with self._host.use("embedder", background=True) as model:
                out += model.embed_documents(texts[start : start + SLICE])
        return out

    def embed_query(self, text: str) -> list[float]:
        with self._host.use("embedder") as model:
            return model.embed_query(text)
