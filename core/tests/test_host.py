"""The model host: lazy loading, the RAM budget, idle unload and searches before background work.

One ships one model; the host stays general, so "second" stands in for any other model."""

import threading
import time

import pytest

from qsone.meaning import host as host_module
from qsone.meaning.host import HostedEmbedder, ModelHost, total_ram
from qsone.meaning.manifest import EMBEDDER

GB = 1_000_000_000
SIZES = {"embedder": 1_800_000_000, "second": 1_700_000_000}


def host(ram, clock=None):
    made = []
    loaders = {k: (lambda k=k: made.append(k) or object()) for k in ("embedder", "second")}
    return ModelHost(loaders, SIZES, ram=ram, clock=clock or time.monotonic), made


def wait_until(check, seconds=5.0):
    end = time.monotonic() + seconds
    while not check():
        assert time.monotonic() < end, "timed out"
        time.sleep(0.005)


class FakeModel:
    def __init__(self):
        self.calls = []

    def embed_documents(self, texts):
        self.calls.append(len(texts))
        return [[float(len(t))] for t in texts]

    def embed_query(self, text):
        return [float(len(text))]


class SpyHost(ModelHost):
    def __init__(self, model, **kw):
        super().__init__({"embedder": lambda: model}, SIZES, **kw)
        self.uses = []

    def use(self, kind, *, background=False):
        self.uses.append((kind, background))
        return super().use(kind, background=background)


def test_nothing_loads_until_used():
    h, made = host(8 * GB)
    assert h.loaded() == frozenset() and made == []


def test_eight_gigabytes_never_holds_both():
    h, made = host(8 * GB)
    with h.use("embedder"):
        assert h.loaded() == {"embedder"}
    with h.use("second"):
        assert h.loaded() == {"second"}
    with h.use("embedder"):
        assert h.loaded() == {"embedder"}
    assert made == ["embedder", "second", "embedder"]


def test_sixteen_gigabytes_keeps_both():
    h, made = host(16 * GB)
    for kind in ("embedder", "second", "embedder"):
        with h.use(kind):
            pass
    assert h.loaded() == {"embedder", "second"} and made == ["embedder", "second"]


def test_idle_models_unload(monkeypatch):
    released = []
    monkeypatch.setattr(host_module, "release_memory", lambda: released.append(1))
    now = [0.0]
    h, _ = host(16 * GB, clock=lambda: now[0])
    with h.use("embedder"):
        pass
    now[0] = 600
    h.unload_idle()
    assert h.loaded() == {"embedder"} and released == []
    now[0] = 601
    h.unload_idle()
    assert h.loaded() == frozenset() and released == [1]


def test_a_model_in_use_is_not_unloaded_as_idle():
    now = [0.0]
    h, _ = host(16 * GB, clock=lambda: now[0])
    with h.use("embedder"):
        now[0] = 10_000
        h.unload_idle()
        assert h.loaded() == {"embedder"}


def test_unload_all():
    h, made = host(16 * GB)
    for kind in ("embedder", "second"):
        with h.use(kind):
            pass
    h.unload_all()
    assert h.loaded() == frozenset()
    with h.use("embedder"):
        pass
    assert made == ["embedder", "second", "embedder"]


def test_a_search_goes_before_background_work():
    h, _ = host(16 * GB)
    order, held, release = [], threading.Event(), threading.Event()

    def holder():
        with h.use("embedder", background=True):
            held.set()
            release.wait(5)

    def caller(name, background):
        with h.use("embedder", background=background):
            order.append(name)

    first = threading.Thread(target=holder)
    first.start()
    assert held.wait(5)
    waiting = [
        threading.Thread(target=caller, args=("background", True)),
        threading.Thread(target=caller, args=("search", False)),
    ]
    waiting[0].start()
    time.sleep(0.05)  # the background caller is in line first
    waiting[1].start()
    wait_until(lambda: h._foreground_waiting == 1)
    release.set()
    for t in [first, *waiting]:
        t.join(5)
    assert order == ["search", "background"]


def test_a_failing_loader_leaves_nothing_loaded():
    def broken():
        raise RuntimeError("the model would not start")

    h = ModelHost({"embedder": broken, "second": object}, SIZES, ram=8 * GB)
    with h.use("second"):
        pass
    with pytest.raises(RuntimeError), h.use("embedder"):
        pass
    assert h.loaded() == frozenset()
    with h.use("second"):  # the host is free again
        assert h.loaded() == {"second"}


def test_hosted_embedder_slices_background_work_by_four():
    model = FakeModel()
    h = SpyHost(model, ram=8 * GB)
    emb = HostedEmbedder(h, EMBEDDER)
    texts = ["x" * n for n in range(1, 11)]
    assert emb.embed_documents(texts) == [[float(n)] for n in range(1, 11)]
    assert model.calls == [4, 4, 2] and h.uses == [("embedder", True)] * 3
    assert emb.embed_query("abc") == [3.0] and h.uses[-1] == ("embedder", False)


def test_hosted_names_come_from_the_spec_without_loading():
    h, made = host(8 * GB)
    emb = HostedEmbedder(h, EMBEDDER)
    assert (emb.name, emb.dims) == (EMBEDDER.name, EMBEDDER.dims) == (EMBEDDER.name, 384)
    assert made == [] and h.loaded() == frozenset()


def test_total_ram_is_plausible():
    assert 1 * GB < total_ram() < 4096 * GB


def test_release_memory_runs():
    host_module.release_memory()
