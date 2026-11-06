"""Search by meaning in the core API: the search model's state, its quiet download, background
indexing and the re-embedding after a model change. Everything is fake: sample specs on a FakeHub
and test doubles for the model, so no test opens a socket or loads a model file."""

import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import copy, settings
from qsone.app import create_app
from qsone.meaning import download
from qsone.meaning.manifest import RETIRED
from qsone.meaning.service import SETTING, Meaning
from qsone.projects import Projects
from qsone.records import search
from tests.conftest import AUTH, SECRET
from tests.doubles import ConceptEmbedder, GateEmbedder
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


class OldEmbedder:
    """Stands in for BGE-M3: another name and 1,024 numbers per chunk."""

    name, dims = "Xenova/bge-m3@4de132583038", 1024

    def embed_documents(self, texts):
        return [[1.0] + [0.0] * 1023 for _ in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * 1023


@pytest.fixture
def hub():
    return FakeHub()


@pytest.fixture
def spec(hub):
    return hub.specs[0]


@pytest.fixture
def models(data_dir):
    return data_dir / "models"


@pytest.fixture
def installed(models, spec, hub):
    """The sample model already downloaded and checked, before the app starts."""
    download.download([spec], models, client=hub.client(), stop=threading.Event())
    hub.requests.clear()


@pytest.fixture
def app_with(models, hub, spec, data_dir):
    def make(loader=None, available=lambda: True, ram=8 * GB, client=None):
        embedder = ConceptEmbedder()

        def meaning(registry):
            return Meaning(
                registry,
                models,
                spec=spec,
                client=client or hub.client,
                loader=loader or (lambda spec, folder: embedder),
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


def model_state(client) -> str:
    return status(client)["model"]["state"]


def project_state(client, pid) -> dict | None:
    return status(client)["indexing"]["projects"].get(pid)


def new_project(client, rows=None) -> str:
    pid = client.post("/projects", json={"name": NAME}, headers=AUTH).json()["id"]
    if rows:
        assert upload(client, pid, rows).status_code == 201
    return pid


def upload(client, pid, rows, name="جدول الكميات - عينة.xlsx"):
    return client.post(
        f"/projects/{pid}/files",
        params={"name": name},
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


def vector_meta(client, pid) -> dict:
    meta = client.app.state.projects.get(pid).meta()
    return {k: v for k, v in meta.items() if k.startswith("embed_")}


def has_vector_table(client, pid) -> bool:
    with client.app.state.projects.get(pid).read() as conn:
        found = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'chunk_vectors'")
        return found.fetchone() is not None


def test_off_and_quiet_until_a_project_has_text(client, spec, hub):
    assert status(client) == {
        "model": {"state": "off", "done_bytes": 0, "total_bytes": spec.size, "reason": None},
        "indexing": {"projects": {}},
    }
    pid = new_project(client)  # a project with no file asks for nothing
    time.sleep(0.2)
    assert model_state(client) == "off" and hub.requests == []
    assert settings.load().get(SETTING) is None
    assert project_state(client, pid) == {"state": "waiting", "done": 0, "total": 0, "reason": None}


def test_the_first_file_downloads_the_model_and_indexes_by_itself(client, spec, hub):
    pid = new_project(client, BOQ_ROWS)  # no question, no button
    r = find(client, pid, "waterproofing")
    assert r["mode"] in ("words", "hybrid") and set(r) == {"mode", "note", "results"}
    wait_for(lambda: indexed(client, pid, total=len(BOQ_ROWS)))
    model = status(client)["model"]
    assert model["state"] == "ready" and model["done_bytes"] == model["total_bytes"] == spec.size
    assert download.installed([spec], client.app.state.meaning.root)
    assert settings.load()[SETTING] == "on"  # it goes on after a restart until in place
    assert {str(r.url) for r in hub.requests} == {spec.url(f) for f in spec.files}

    r = find(client, pid, "waterproofing for the foundations", k=30)
    assert r["mode"] == "hybrid" and r["note"] is None
    assert r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert set(r["results"][0]) == {"chunk_id", "file_id", "file_name", "locator", "text", "score"}
    assert vector_meta(client, pid) == {"embed_model": spec.name, "embed_dims": "5"}


def test_words_work_while_it_downloads(app_with, hub):
    gate = threading.Event()
    seen, held = held_client(hub, hold_at=1, gate=gate)
    with TestClient(app_with(client=held)) as client:
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: len(seen) == 1)
        assert model_state(client) == "downloading"
        r = find(client, pid, "عزل")
        assert r["mode"] == "words" and r["note"] == copy.SEARCH_WORDS_ONLY
        assert r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
        gate.set()
        wait_for(lambda: indexed(client, pid, total=len(BOQ_ROWS)))


def test_an_older_project_with_text_starts_it_at_startup(app_with, hub, spec, models):
    with TestClient(app_with(available=lambda: False)) as client:  # made where it cannot run
        pid = new_project(client, BOQ_ROWS)
    assert hub.requests == [] and settings.load().get(SETTING) is None

    with TestClient(app_with()) as client:  # no project opened: the start looks for itself
        wait_for(lambda: model_state(client) == "ready")
        assert download.installed([spec], models) and settings.load()[SETTING] == "on"
        assert project_state(client, pid) is None  # nothing was opened for it
        assert client.post(f"/projects/{pid}/open", headers=AUTH).status_code == 200
        wait_for(lambda: indexed(client, pid, total=len(BOQ_ROWS)))


def test_projects_without_text_download_nothing_at_startup(app_with, hub):
    with TestClient(app_with(available=lambda: False)) as client:
        new_project(client)  # no file
        client.post("/projects", json={"name": "مستشفى - عينة"}, headers=AUTH)
    with TestClient(app_with()) as client:
        time.sleep(0.3)
        assert model_state(client) == "off" and hub.requests == []
        assert client.app.state.projects.opened() == []  # looked at, then closed again


def test_an_app_without_a_fake_hub_fails_at_once_and_quits_at_once(data_dir):
    """The core's own default client (refused in every test by conftest): the first file asks,
    the 403 fails it without retries, and nothing waits when the app stops."""
    started = time.monotonic()
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        new_project(client, BOQ_ROWS)
        wait_for(lambda: model_state(client) == "failed")
    assert time.monotonic() - started < 3


def test_exact_mode(ready_client):
    pid = new_project(ready_client, BOQ_ROWS)
    r = find(ready_client, pid, "03/02")
    assert r["mode"] == "exact" and r["results"][0]["locator"] == {"sheet": "BOQ", "row": 1}


def test_upload_does_not_wait_for_embedding(app_with, installed):
    gate = GateEmbedder()
    with TestClient(app_with(loader=lambda spec, folder: gate)) as client:
        pid = new_project(client)
        assert upload(client, pid, MANY_ROWS).status_code == 201  # while the gate is shut
        wait_for(lambda: gate.entered == 1)
        assert gate.passed == 0 and project_state(client, pid)["state"] == "indexing"
        gate.release()
        wait_for(lambda: indexed(client, pid, total=40))


def test_closing_a_project_stops_its_indexing(app_with, installed, caplog):
    caplog.set_level(logging.INFO, logger="qsone.meaning")
    gate = GateEmbedder()
    with TestClient(app_with(loader=lambda spec, folder: gate)) as client:
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


def test_a_download_resumes_after_a_restart(app_with, hub, spec, models):
    gate = threading.Event()
    seen, held = held_client(hub, hold_at=2, gate=gate)
    with TestClient(app_with(client=held)) as client:
        new_project(client, BOQ_ROWS)
        wait_for(lambda: len(seen) == 2)
        threading.Timer(0.2, gate.set).start()  # quitting while the second file comes
    assert not download.installed([spec], models) and list(models.rglob("*.part"))

    hub.requests.clear()
    with TestClient(app_with()) as client:  # no project open: the setting says go on
        wait_for(lambda: model_state(client) == "ready")
    assert hub.requests[0].headers["range"].startswith("bytes=")
    assert download.installed([spec], models)


def test_a_failed_download_waits_for_the_next_start(app_with, hub):
    with TestClient(app_with()) as client:
        hub.drop_after(10, times=99)
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: model_state(client) == "failed")
        assert status(client)["model"]["reason"] == copy.MEANING_DOWNLOAD_FAILED
        assert find(client, pid, "عزل")["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
        asked = len(hub.requests)
        assert upload(client, pid, MANY_ROWS, name="بنود - عينة.xlsx").status_code == 201
        time.sleep(0.3)
        assert model_state(client) == "failed" and len(hub.requests) == asked  # no retry loop
    hub.heal()
    with TestClient(app_with()) as client:
        wait_for(lambda: model_state(client) == "ready")
        assert status(client)["model"]["reason"] is None


def test_a_model_that_will_not_load_is_fetched_again_at_the_next_start(
    app_with, installed, spec, hub, models
):
    def broken(spec, folder):
        raise RuntimeError("sample: this model will not start")

    with TestClient(app_with(loader=broken)) as client:
        assert model_state(client) == "ready"
        pid = new_project(client, BOQ_ROWS)  # the worker loads the embedder for it
        wait_for(lambda: model_state(client) == "failed")
        assert status(client)["model"]["reason"] == copy.MEANING_MODEL_FAILED
        assert not (download.folder(spec, models) / download.VERIFIED).exists()
        assert project_state(client, pid)["state"] != "failed"  # the model failed, not the project
        r = find(client, pid, "عزل")
        assert r["mode"] == "words" and r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert not download.installed([spec], models)
    with TestClient(app_with()) as client:  # rehashed: the files were right, nothing fetched
        wait_for(lambda: model_state(client) == "ready")
    assert download.installed([spec], models) and hub.requests == []


def test_a_missing_runtime_makes_it_unavailable(app_with, installed):
    def no_runtime(spec, folder):
        raise ImportError("sample: no onnxruntime")

    with TestClient(app_with(loader=no_runtime)) as client:
        pid = new_project(client, BOQ_ROWS)
        wait_for(lambda: model_state(client) == "unavailable")
        assert status(client)["model"]["reason"] == copy.MEANING_NOT_ON_THIS_COMPUTER
        assert find(client, pid, "عزل")["mode"] == "words"


def test_unavailable_computer_downloads_nothing(app_with, hub):
    with TestClient(app_with(available=lambda: False)) as client:
        model = status(client)["model"]
        assert model["state"] == "unavailable"
        assert model["reason"] == copy.MEANING_NOT_ON_THIS_COMPUTER
        pid = new_project(client, BOQ_ROWS)
        time.sleep(0.2)
        assert find(client, pid, "عزل")["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
    assert hub.requests == []


def test_vectors_of_the_old_model_are_dropped_on_open_and_made_again(
    app_with, hub, spec, models, data_dir
):
    """A project indexed by BGE-M3 (1,024 numbers a chunk): opened with the new model missing, its
    vectors go at once and words still work; once the model is in place, every chunk is embedded
    again at the new size (the sample's 5; e5-small's 384). The old models' folders go too."""
    with TestClient(app_with(available=lambda: False)) as client:
        pid = new_project(client, BOQ_ROWS)
    registry = Projects(data_dir)  # as the old One left it
    registry.open(pid)
    rec = registry.get(pid)
    assert search.index_vectors(rec, OldEmbedder()) == 6
    assert rec.meta()["embed_model"] == OldEmbedder.name and rec.meta()["embed_dims"] == "1024"
    registry.close_all()
    for old in RETIRED:
        (models / old / "rev").mkdir(parents=True)
        (models / old / "rev" / "verified.json").write_text("{}")

    gate = threading.Event()
    seen, held = held_client(hub, hold_at=1, gate=gate)
    with TestClient(app_with(client=held)) as client:
        assert client.post(f"/projects/{pid}/open", headers=AUTH).status_code == 200
        wait_for(lambda: not has_vector_table(client, pid))
        assert vector_meta(client, pid) == {}
        assert model_state(client) == "downloading"
        r = find(client, pid, "عزل")
        assert r["mode"] == "words" and r["results"][0]["locator"] == {"sheet": "BOQ", "row": 3}
        assert all((models / old).is_dir() for old in RETIRED)  # until the new one is ready
        gate.set()
        wait_for(lambda: indexed(client, pid, total=len(BOQ_ROWS)))
        assert vector_meta(client, pid) == {"embed_model": spec.name, "embed_dims": "5"}
        assert find(client, pid, "waterproofing for the foundations")["mode"] == "hybrid"
    assert not any((models / old).exists() for old in RETIRED)
    assert download.installed([spec], models)


def test_nothing_readable_in_the_data_folder_after_indexing(ready_client, data_dir):
    pid = new_project(ready_client, BOQ_ROWS)
    wait_for(lambda: indexed(ready_client, pid))
    assert find(ready_client, pid, "waterproofing")["mode"] == "hybrid"
    assert (data_dir / "models").is_dir()
    blob = b"".join(p.read_bytes() for p in data_dir.rglob("*") if p.is_file())
    for word in ["عزل الرطوبة", NAME, "05/01"]:
        assert word.encode() not in blob, word


def test_the_route_needs_the_secret_and_nothing_is_left_to_press(client):
    for headers in ({}, {"Authorization": "Bearer wrong"}):
        assert client.get("/meaning", headers=headers).status_code == 401
    pid = "0" * 32
    gone = ["/meaning/download", "/meaning/stop", "/meaning/pause", "/meaning/resume"]
    for url in [*gone, f"/projects/{pid}/rerank"]:
        assert client.post(url, headers=AUTH).status_code in (404, 405), url
    assert model_state(client) == "off"


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
