"""Search by meaning in the core API: the search model's state, its download, background indexing
and the two-step search. Everything is fake: sample specs on a FakeHub and test doubles for the
models, so no test opens a socket or loads a model file."""

import logging
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.meaning import download
from qsone.meaning.service import Meaning
from tests.conftest import AUTH, SECRET
from tests.doubles import ConceptEmbedder, GateEmbedder, PreferReranker
from tests.hub import FakeHub
from tests.samples import sample_xlsx

GB = 1_000_000_000
CORE = Path(__file__).resolve().parents[1]
NAME = "مدرسة - عينة"
BOQ_ROWS = [
    ["03/02", "خرسانه مسلّحه للأسقف", "م3", 120],
    ["03/20", "خرسانة عادية للأرضيات", "م3", 40],
    ["05/01", "عزل الرطوبة للأساسات", "م2", 300],
    ["08/22", "بردورة خرسانية", "م.ط", 519],
    ["09/01", "حفر للأساسات - عينة", "م3", 75],
    ["10/04", "حديد تسليح للأسقف - عينة", "طن", 12],
]
MANY_ROWS = [[f"{i:02}/01", f"بند خرسانة رقم {i} - عينة", "م3", i] for i in range(1, 41)]


@pytest.fixture
def hub():
    return FakeHub()


@pytest.fixture
def models(data_dir):
    return data_dir / "models"


@pytest.fixture
def installed(models, hub):
    """The sample models already downloaded and checked, before the app starts."""
    download.download(hub.specs, models, client=hub.client(), stop=threading.Event())
    hub.requests.clear()


def fake_loader(embedder, reranker):
    return lambda spec, folder: embedder if spec.kind == "embedder" else reranker


@pytest.fixture
def app_with(models, hub, data_dir):
    def make(loader=None, available=lambda: True, ram=8 * GB, client=None):
        def meaning(registry):
            return Meaning(
                registry,
                models,
                specs=hub.specs,
                client=client or hub.client,
                loader=loader or fake_loader(ConceptEmbedder(), PreferReranker("عادية")),
                available=available,
                ram=ram,
                sleep=lambda s: None,
            )

        return create_app(SECRET, data_dir=data_dir, meaning=meaning)

    return make


@pytest.fixture
def client(app_with):
    with TestClient(app_with()) as client:
        yield client


@pytest.fixture
def ready_client(app_with, installed):
    with TestClient(app_with()) as client:
        yield client


def wait_for(check, seconds: float = 5.0) -> None:
    end = time.monotonic() + seconds
    while not check():
        if time.monotonic() > end:
            raise AssertionError("timed out waiting")
        time.sleep(0.02)


def status(client) -> dict:
    r = client.get("/meaning", headers=AUTH)
    assert r.status_code == 200
    return r.json()


def project_state(client, pid) -> dict | None:
    return status(client)["indexing"]["projects"].get(pid)


def new_project(client, rows=None) -> str:
    pid = client.post("/projects", json={"name": NAME}, headers=AUTH).json()["id"]
    if rows:
        assert upload(client, pid, rows).status_code == 201
    return pid


def upload(client, pid, rows):
    return client.post(
        f"/projects/{pid}/files",
        params={"name": "جدول الكميات - عينة.xlsx"},
        content=sample_xlsx({"BOQ": rows}),
        headers=AUTH,
    )


def find(client, pid, q, **params) -> dict:
    r = client.get(f"/projects/{pid}/search", params={"q": q, **params}, headers=AUTH)
    assert r.status_code == 200
    return r.json()


def indexed(client, pid, total=None) -> bool:
    p = project_state(client, pid)
    return p is not None and p["state"] == "ready" and (total is None or p["done"] == total)


def held_client(hub, hold_at: int, gate: threading.Event):
    """A client to the hub that holds request number `hold_at` until `gate` is set."""
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == hold_at:
            gate.wait(5)
        return hub.handler(request)

    return seen, lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_off_until_asked_and_says_the_size(client, hub):
    assert status(client) == {
        "model": {
            "state": "off",
            "done_bytes": 0,
            "total_bytes": sum(s.size for s in hub.specs),
            "reason": None,
        },
        "indexing": {"paused": False, "projects": {}},
    }
    assert hub.requests == []


def test_download_then_existing_files_are_indexed_in_the_background(client, hub):
    pid = new_project(client, BOQ_ROWS)
    r = find(client, pid, "waterproofing")
    assert r["mode"] == "words" and r["note"] == copy.SEARCH_WORDS_ONLY and r["rerank"] is False
    assert project_state(client, pid) == {"state": "waiting", "done": 0, "total": 0, "reason": None}

    r = client.post("/meaning/download", headers=AUTH)
    assert r.status_code == 202 and r.json()["model"]["state"] in ("downloading", "checking")
    wait_for(lambda: indexed(client, pid, total=len(BOQ_ROWS)))
    model = status(client)["model"]
    assert model["state"] == "ready" and model["done_bytes"] == model["total_bytes"]
    assert download.installed(hub.specs, client.app.state.meaning.root)

    r = find(client, pid, "waterproofing for the foundations", k=30)
    assert r["mode"] == "hybrid" and r["note"] is None and r["rerank"] is True
    assert r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert all(isinstance(x["chunk_id"], int) for x in r["results"])
    ids = [x["chunk_id"] for x in r["results"]]
    rr = client.post(
        f"/projects/{pid}/rerank", json={"q": "خرسانة", "chunk_ids": ids}, headers=AUTH
    )
    assert rr.status_code == 200
    results = rr.json()["results"]
    assert results[0]["locator"] == {"sheet": "BOQ", "row": 2} and len(results) == len(ids)
    assert set(results[0]) == {"chunk_id", "file_id", "file_name", "locator", "text", "score"}


def test_exact_mode_offers_no_rerank(ready_client):
    pid = new_project(ready_client, BOQ_ROWS)
    r = find(ready_client, pid, "03/02")
    assert r["mode"] == "exact" and r["rerank"] is False
    assert r["results"][0]["locator"] == {"sheet": "BOQ", "row": 1}


def test_rerank_needs_the_model_and_a_short_list(client):
    pid = new_project(client, BOQ_ROWS)
    r = client.post(f"/projects/{pid}/rerank", json={"q": "خرسانة", "chunk_ids": [1]}, headers=AUTH)
    assert r.status_code == 409 and r.json() == {"error": copy.MEANING_NOT_READY}
    for body in (
        {"q": "", "chunk_ids": [1]},
        {"q": "x" * 1001, "chunk_ids": [1]},
        {"q": "خرسانة", "chunk_ids": []},
        {"q": "خرسانة", "chunk_ids": list(range(31))},
    ):
        assert client.post(f"/projects/{pid}/rerank", json=body, headers=AUTH).status_code == 422


def test_upload_does_not_wait_for_embedding(app_with, installed):
    gate = GateEmbedder()
    with TestClient(app_with(loader=fake_loader(gate, PreferReranker("x")))) as client:
        pid = new_project(client)
        assert upload(client, pid, MANY_ROWS).status_code == 201  # while the gate is shut
        wait_for(lambda: gate.entered == 1)
        assert gate.passed == 0 and project_state(client, pid)["state"] == "indexing"
        gate.release()
        wait_for(lambda: indexed(client, pid, total=40))


def test_pause_holds_and_resume_finishes(app_with, installed):
    gate = GateEmbedder()
    with TestClient(app_with(loader=fake_loader(gate, PreferReranker("x")))) as client:
        pid = new_project(client, MANY_ROWS)
        wait_for(lambda: gate.entered == 1)
        r = client.post("/meaning/pause", headers=AUTH)
        assert r.status_code == 200 and r.json()["indexing"]["paused"] is True
        gate.release()
        wait_for(lambda: project_state(client, pid)["state"] == "waiting")
        assert project_state(client, pid)["done"] == 16 and gate.passed == 4  # one batch of 16
        time.sleep(0.3)
        assert project_state(client, pid)["done"] == 16 and gate.passed == 4
        assert find(client, pid, "خرسانة")["results"]  # search still works while paused
        r = client.post("/meaning/resume", headers=AUTH)
        assert r.status_code == 200 and r.json()["indexing"]["paused"] is False
        wait_for(lambda: indexed(client, pid, total=40))


def test_closing_a_project_stops_its_indexing(app_with, installed, caplog):
    caplog.set_level(logging.INFO, logger="qsone.meaning")
    gate = GateEmbedder()
    with TestClient(app_with(loader=fake_loader(gate, PreferReranker("x")))) as client:
        pid = new_project(client, MANY_ROWS)
        gate.release(4)  # the first batch of 16, in slices of 4
        wait_for(lambda: gate.entered == 5)
        assert project_state(client, pid) == {
            "state": "indexing",
            "done": 16,
            "total": 40,
            "reason": None,
        }
        assert client.post(f"/projects/{pid}/close", headers=AUTH).status_code == 200
        assert project_state(client, pid) is None  # open projects only
        gate.release()
        wait_for(lambda: gate.passed == 8)  # the batch in flight ends; its commit cannot happen
        assert client.post(f"/projects/{pid}/open", headers=AUTH).status_code == 200
        wait_for(lambda: indexed(client, pid, total=40))
        assert gate.passed == 14  # 24 chunks left after reopening: what was committed is kept
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_download_asked_for_resumes_after_a_restart(app_with, hub, models):
    gate = threading.Event()
    seen, held = held_client(hub, hold_at=2, gate=gate)
    with TestClient(app_with(client=held)) as client:
        client.post("/meaning/download", headers=AUTH)
        wait_for(lambda: len(seen) == 2)
        threading.Timer(0.2, gate.set).start()  # quitting while the second file comes
    assert not download.installed(hub.specs, models) and list(models.rglob("*.part"))

    hub.requests.clear()
    with TestClient(app_with()) as client:
        wait_for(lambda: status(client)["model"]["state"] == "ready")
    assert hub.requests[0].headers["range"].startswith("bytes=")
    assert download.installed(hub.specs, models)


def test_stop_keeps_what_came_and_stays_stopped_after_a_restart(app_with, hub, models):
    gate = threading.Event()
    seen, held = held_client(hub, hold_at=2, gate=gate)
    with TestClient(app_with(client=held)) as client:
        client.post("/meaning/download", headers=AUTH)
        wait_for(lambda: len(seen) == 2)
        r = client.post("/meaning/stop", headers=AUTH)
        assert r.status_code == 200 and r.json()["model"]["state"] == "stopped"
        gate.set()
        time.sleep(0.2)
        assert status(client)["model"]["state"] == "stopped"
        assert status(client)["model"]["done_bytes"] > 0
    assert list(models.rglob("*.part"))  # what came is kept

    hub.requests.clear()
    with TestClient(app_with()) as client:
        time.sleep(0.2)
        assert status(client)["model"]["state"] == "off"  # Stop is not undone by a restart
        assert hub.requests == []
        client.post("/meaning/download", headers=AUTH)
        wait_for(lambda: status(client)["model"]["state"] == "ready")


def test_failed_download_says_why_and_try_again_works(client, hub):
    pid = new_project(client, BOQ_ROWS)
    hub.drop_after(10, times=99)
    client.post("/meaning/download", headers=AUTH)
    wait_for(lambda: status(client)["model"]["state"] == "failed")
    assert status(client)["model"]["reason"] == copy.MEANING_DOWNLOAD_FAILED
    assert find(client, pid, "عزل")["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    hub.heal()
    assert client.post("/meaning/download", headers=AUTH).status_code == 202
    wait_for(lambda: status(client)["model"]["state"] == "ready")
    assert status(client)["model"]["reason"] is None


def test_a_model_that_will_not_load_is_fetched_again(app_with, installed, hub, models):
    def broken(spec, folder):
        raise RuntimeError("sample: this model will not start")

    with TestClient(app_with(loader=broken)) as client:
        assert status(client)["model"]["state"] == "ready"
        pid = new_project(client, BOQ_ROWS)  # the worker loads the embedder for it
        wait_for(lambda: status(client)["model"]["state"] == "failed")
        assert status(client)["model"]["reason"] == copy.MEANING_MODEL_FAILED
        assert not (download.folder(hub.specs[0], models) / download.VERIFIED).exists()
        assert project_state(client, pid)["state"] != "failed"  # the model failed, not the project
        r = find(client, pid, "عزل")
        assert r["mode"] == "words" and r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert not download.installed(hub.specs, models)


def test_a_missing_runtime_makes_it_unavailable(app_with, installed):
    def no_runtime(spec, folder):
        raise ImportError("sample: no onnxruntime")

    with TestClient(app_with(loader=no_runtime)) as client:
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: status(client)["model"]["state"] == "unavailable")
        assert status(client)["model"]["reason"] == copy.MEANING_NOT_ON_THIS_COMPUTER
        assert find(client, pid, "عزل")["mode"] == "words"


def test_unavailable_computer_downloads_nothing(app_with, hub):
    with TestClient(app_with(available=lambda: False)) as client:
        model = status(client)["model"]
        assert model["state"] == "unavailable"
        assert model["reason"] == copy.MEANING_NOT_ON_THIS_COMPUTER
        r = client.post("/meaning/download", headers=AUTH)
        assert r.status_code == 409 and r.json() == {"error": copy.MEANING_NOT_ON_THIS_COMPUTER}
        pid = new_project(client, BOQ_ROWS)
        assert find(client, pid, "عزل")["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert hub.requests == []


def test_a_newer_rerank_supersedes_the_older(app_with, installed):
    calls, go = [], threading.Event()

    class SlowReranker(PreferReranker):
        def rerank(self, query, texts):
            calls.append(len(texts))
            go.wait(5)
            return super().rerank(query, texts)

    app = app_with(loader=fake_loader(ConceptEmbedder(), SlowReranker("عادية")))
    with TestClient(app) as client:
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: indexed(client, pid))
        ids = [x["chunk_id"] for x in find(client, pid, "concrete", k=30)["results"]]
        assert len(ids) > 4  # more than one slice
        meaning, turns = app.state.meaning, []
        turn = meaning.rerank_turn
        meaning.rerank_turn = lambda project_id: turns.append(project_id) or turn(project_id)
        answers = {}

        def post(n):
            body = {"q": "خرسانة", "chunk_ids": ids}
            answers[n] = client.post(f"/projects/{pid}/rerank", json=body, headers=AUTH)

        first = threading.Thread(target=post, args=(1,))
        first.start()
        wait_for(lambda: len(calls) == 1)
        second = threading.Thread(target=post, args=(2,))
        second.start()
        wait_for(lambda: len(turns) == 2)
        go.set()
        first.join(5)
        second.join(5)
    assert answers[1].status_code == 409 and answers[1].json() == {"error": copy.SEARCH_SUPERSEDED}
    assert answers[2].status_code == 200
    assert answers[2].json()["results"][0]["locator"] == {"sheet": "BOQ", "row": 2}


def test_eight_gigabytes_never_hold_both_models(app_with, installed):
    live, most, made = weakref.WeakSet(), [0], []

    def loader(spec, folder):
        most[0] = max(most[0], len(live) + 1)
        model = ConceptEmbedder() if spec.kind == "embedder" else PreferReranker("عادية")
        live.add(model)
        made.append(spec.kind)
        return model

    with TestClient(app_with(loader=loader, ram=8 * GB)) as client:
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: indexed(client, pid))
        for _ in range(2):
            ids = [x["chunk_id"] for x in find(client, pid, "concrete", k=30)["results"]]
            body = {"q": "خرسانة", "chunk_ids": ids}
            assert (
                client.post(f"/projects/{pid}/rerank", json=body, headers=AUTH).status_code == 200
            )
    assert made[:4] == ["embedder", "reranker", "embedder", "reranker"] and most[0] == 1


def test_nothing_readable_in_the_data_folder_after_indexing(ready_client, data_dir):
    pid = new_project(ready_client, BOQ_ROWS)
    wait_for(lambda: indexed(ready_client, pid))
    assert find(ready_client, pid, "waterproofing")["mode"] == "hybrid"
    assert (data_dir / "models").is_dir()
    blob = b"".join(p.read_bytes() for p in data_dir.rglob("*") if p.is_file())
    for word in ["عزل الرطوبة", NAME, "05/01"]:
        assert word.encode() not in blob, word


def test_routes_need_the_secret(client):
    pid = "0" * 32
    routes = [
        ("GET", "/meaning"),
        ("POST", "/meaning/download"),
        ("POST", "/meaning/stop"),
        ("POST", "/meaning/pause"),
        ("POST", "/meaning/resume"),
        ("POST", f"/projects/{pid}/rerank"),
    ]
    for method, url in routes:
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert client.request(method, url, headers=headers).status_code == 401, url
    assert status(client)["model"]["state"] == "off"


def test_quitting_stops_the_worker(app_with):
    def ours():
        return [t for t in threading.enumerate() if t.name.startswith("qsone-meaning")]

    with TestClient(app_with()):
        assert ours()
    assert not ours()


def test_core_starts_without_the_model_runtime():
    code = "import sys, qsone.app; print('onnxruntime' in sys.modules, 'tokenizers' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=CORE
    )
    assert out.stdout.strip() == "False False", out.stderr
