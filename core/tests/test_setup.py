"""Automatic setup (C8): the parts ONE fetches or checks by itself, against a fake hub. Nothing
here opens a socket or downloads a real file. Synthetic «عينة» data only."""

import hashlib
import io
import os
import threading
import time
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.meaning import download as fetch
from qsone.sandbox import runtime
from qsone.setup import manifest, runner
from qsone.setup.manifest import DWG_READER, Part, PartFile
from qsone.setup.runner import Setup
from tests.conftest import AUTH, SECRET
from tests.hub import FakeHub


class Hub(FakeHub):
    """The fake hub, able to go offline (no host can be reached) and to damage some answers."""

    def __init__(self) -> None:
        super().__init__()
        self.offline = False
        self.offline_after: int | None = None  # answers served before going offline
        self.damaged = 0  # answers left to damage

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.offline_after is not None:
            if self.offline_after == 0:
                self.offline = True
            self.offline_after -= 1
        if self.offline:
            raise httpx.ConnectError("no network (fake hub)", request=request)
        self._corrupt = self.damaged > 0
        self.damaged = max(self.damaged - 1, 0)
        return super().handler(request)

    def asked(self, part: Part) -> list[httpx.Request]:
        urls = {f.url for f in part.files}
        return [r for r in self.requests if str(r.url) in urls]


def _part(id: str, spec, *, broken: bool = False) -> Part:
    """A sample part made of one of the hub's sample specs; `broken` points at nothing."""
    tail = "-gone" if broken else ""
    return Part(
        id=id,
        kind="model",
        title=copy.SETUP_SEARCH_MODEL,
        affects=copy.SETUP_SEARCH_MODEL_AFFECTS,
        cannot_run=copy.MEANING_NOT_ON_THIS_COMPUTER,
        files=tuple(PartFile(f.path, spec.url(f) + tail, f.size, f.sha256) for f in spec.files),
        folder=spec.id,
        revision=spec.revision,
    )


@pytest.fixture
def hub():
    return Hub()


@pytest.fixture
def parts(hub):
    first, second = hub.specs
    return _part("first", first), _part("second", second), DWG_READER


@pytest.fixture
def helper(tmp_path):
    binary = tmp_path / "qsone-drawings"
    binary.write_bytes(b"sample helper")
    return binary


def make(hub, parts, tmp_path, helper=None, **more) -> Setup:
    return Setup(
        tmp_path / "models",
        tmp_path / "sandbox",
        parts=parts,
        client=hub.client,
        runs_here=more.pop("runs_here", lambda part: True),
        helper=lambda: helper,
        sleep=lambda seconds: None,
        **more,
    )


def states(setup: Setup) -> dict[str, str]:
    return {part.id: part.state for part in setup.state().parts}


def test_the_manifest_pins_every_part():
    assert [p.id for p in manifest.PARTS] == [
        "search-model",
        "sandbox-runtime",
        "dwg-reader",
        "ocr",
    ]
    for part in manifest.PARTS:
        assert set(part.title) == set(part.affects) == set(part.cannot_run) == {"en", "ar"}
        for f in part.files:
            assert f.url.startswith("https://") and f.size > 0 and len(f.sha256) == 64
    assert manifest.SEARCH_MODEL.size == 135_390_915
    assert manifest.OCR.size == 12_832_533  # the OCR spike's detector, recogniser and two yml
    assert manifest.DWG_READER.files == () and manifest.DWG_READER.size == 0


def test_setup_downloads_only_missing(hub, parts, tmp_path, helper):
    first, second, _ = parts
    with hub.client() as client:  # the search model is already here
        fetch.download(
            [runner._spec(first)], tmp_path / "models", client=client, stop=threading.Event()
        )
    hub.requests.clear()
    setup = make(hub, parts, tmp_path, helper)
    assert states(setup) == {"first": "present", "second": "queued", "dwg-reader": "present"}

    setup.ensure()
    assert hub.asked(first) == [] and len(hub.asked(second)) == len(second.files)
    state = setup.state()
    assert state.ready and all(p.done_bytes == p.total_bytes for p in state.parts)

    hub.requests.clear()
    setup.ensure()  # again: nothing more
    assert hub.requests == []


def test_setup_verifies_checksum(hub, parts, tmp_path, helper):
    first, second, _ = parts
    folder = fetch.folder(runner._spec(first), tmp_path / "models")
    wrong = folder / first.files[0].path
    wrong.parent.mkdir(parents=True)
    wrong.write_bytes(b"x" * first.files[0].size)  # the right size, the wrong bytes
    hub.damaged = 1  # and the first answer comes damaged too
    setup = make(hub, parts, tmp_path, helper)
    setup.ensure()

    assert states(setup)["first"] == "present"
    for f in first.files:
        assert hashlib.sha256((folder / f.path).read_bytes()).hexdigest() == f.sha256
        assert not (folder / (f.path + ".part")).exists()
    assert len(hub.asked(first)) == len(first.files) + 1  # the damaged one came again


def test_setup_offline_then_resume(hub, parts, tmp_path, helper, data_dir):
    first, second, _ = parts
    hub.drop_after(100_000)  # the first file breaks off half-way, then no host answers
    hub.offline_after = 1
    setup = make(hub, parts, tmp_path, helper)
    setup.ensure()

    state = setup.state()
    assert not state.ready
    assert states(setup) == {
        "first": "waiting_network",
        "second": "waiting_network",
        "dwg-reader": "present",
    }
    assert state.parts[0].done_bytes == 100_000 and state.parts[0].reason is None
    client = TestClient(create_app(SECRET, data_dir=data_dir, setup=setup))  # passes driven here
    assert client.get("/health", headers=AUTH).json() == {"ok": True}  # the core answers
    shown = client.get("/setup/parts", headers=AUTH).json()
    assert [p["state"] for p in shown["parts"]][:2] == ["waiting_network"] * 2

    hub.offline, hub.requests = False, []
    setup.ensure()
    assert setup.state().ready
    assert hub.requests[0].headers["range"] == "bytes=100000-"  # from the .part file


def test_failed_part_names_what_breaks(hub, parts, tmp_path, helper):
    first, second, dwg = parts
    gone = _part("gone", hub.specs[1], broken=True)
    setup = make(hub, (gone, first, dwg), tmp_path, helper)
    setup.ensure()

    state = setup.state()
    failed = state.parts[0]
    assert failed.state == "failed" and not state.ready
    assert failed.reason == c.Text(**copy.SETUP_REFUSED)
    assert failed.affects == c.Text(**copy.SETUP_SEARCH_MODEL_AFFECTS)  # what does not work
    assert len(hub.asked(gone)) == 3  # three tries, then it stops
    assert states(setup)["first"] == "present"  # the others finish

    hub.requests.clear()
    setup.ensure()  # a failed part waits for Retry
    assert hub.requests == []
    assert states(setup)["gone"] == "failed"
    assert {p.id: p.state for p in setup.retry().parts}["gone"] == "queued"


def test_damaged_three_times_says_so(hub, parts, tmp_path, helper):
    hub.damaged = 99
    setup = make(hub, parts[:1], tmp_path, helper)
    setup.ensure()
    (part,) = setup.state().parts
    assert part.state == "failed" and part.reason == c.Text(**copy.SETUP_FILE_DAMAGED)


def test_unavailable_counts_as_ready_and_is_never_fetched(hub, parts, tmp_path):
    first, second, _ = parts
    setup = make(hub, parts, tmp_path, None, runs_here=lambda part: part.id != "first")
    setup.ensure()
    state = setup.state()
    assert states(setup) == {
        "first": "unavailable",
        "second": "present",
        "dwg-reader": "unavailable",
    }
    assert state.ready and hub.asked(first) == []
    assert state.parts[0].reason == c.Text(**copy.MEANING_NOT_ON_THIS_COMPUTER)
    assert state.parts[2].reason == c.Text(**copy.SETUP_DWG_MISSING)
    assert state.parts[2].total_bytes == 0  # bundled: nothing to download
    assert setup.retry() == state  # Retry skips them


def test_part_path_finds_a_part_in_place(hub, parts, tmp_path, helper):
    first, second, _ = parts
    setup = make(hub, parts, tmp_path, helper)
    assert setup.part_path("first") is None
    assert setup.part_path("dwg-reader") == helper
    assert setup.part_path("no-such-part") is None
    setup.ensure()
    found = setup.part_path("first")
    assert found == fetch.folder(runner._spec(first), tmp_path / "models")
    assert all((found / f.path).is_file() for f in first.files)


def test_the_app_default_finds_parts_in_its_data_folder(data_dir):
    assert runner.default().models == data_dir / "models"
    assert runner.part_path("search-model") is None  # nothing downloaded in tests


@pytest.mark.skipif(os.name == "nt", reason="the stand-in helper is a shell script")
def test_the_dwg_helper_is_checked_by_its_version_answer(tmp_path, monkeypatch):
    script = tmp_path / "qsone-drawings"
    script.write_text("#!/bin/sh\necho qsone-drawings 0.1.0\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(runner, "find_binary", lambda: script)
    assert runner.answering_helper() == script
    script.write_text("#!/bin/sh\necho something else\n", encoding="utf-8")
    assert runner.answering_helper() is None
    monkeypatch.setattr(runner, "find_binary", lambda: None)
    assert runner.answering_helper() is None


def _zip(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return out.getvalue()


def test_the_sandbox_runtime_is_fetched_and_unpacked(tmp_path):
    served = {
        "https://sample.invalid/python.zip": _zip({"python.wasm": b"\0asm sample", "lib/x": b""}),
        "https://sample.invalid/pkg.whl": _zip({"pkg/__init__.py": b"# sample"}),
    }
    files = tuple(
        PartFile(url.rsplit("/", 1)[1], url, len(data), hashlib.sha256(data).hexdigest())
        for url, data in served.items()
    )
    part = Part(
        "sandbox-runtime",
        "sandbox",
        copy.SETUP_SANDBOX,
        copy.SETUP_SANDBOX_AFFECTS,
        copy.SETUP_SANDBOX_NOT_HERE,
        files,
        "cpython-wasi",
        runtime.VERSION,
    )

    def answer(request):
        return httpx.Response(200, content=served[str(request.url)])

    def client():
        return httpx.Client(transport=httpx.MockTransport(answer))

    setup = Setup(
        tmp_path / "models",
        tmp_path / "sandbox",
        parts=(part,),
        client=client,
        runs_here=lambda p: True,
    )
    assert states(setup) == {"sandbox-runtime": "queued"}
    setup.ensure()
    assert states(setup) == {"sandbox-runtime": "present"}
    assert setup.part_path("sandbox-runtime") == runtime.find(tmp_path / "sandbox")
    assert (
        setup.part_path("sandbox-runtime") / "lib" / runtime.LIB / "site-packages" / "pkg"
    ).is_dir()


def test_setup_starts_with_the_app_and_never_blocks_it(
    hub, parts, tmp_path, helper, data_dir, monkeypatch
):
    release = threading.Event()
    slow = hub.handler

    def held(request):
        release.wait(10)
        return slow(request)

    hub.handler = held
    published = []
    monkeypatch.setattr(
        activity, "publish", lambda channel, event: published.append((channel, event))
    )
    setup = make(hub, parts, tmp_path, helper)
    with TestClient(create_app(SECRET, data_dir=data_dir, setup=setup)) as client:
        assert client.get("/health", headers=AUTH).status_code == 200  # while a part downloads
        assert not client.get("/setup/parts", headers=AUTH).json()["ready"]
        release.set()
        for _ in range(200):
            if client.get("/setup/parts", headers=AUTH).json()["ready"]:
                break
            time.sleep(0.05)
        assert client.get("/setup/parts", headers=AUTH).json()["ready"]
        for _ in range(100):  # the last event reaches the loop after the state changed
            if published and published[-1][1]["setup"]["ready"]:
                break
            time.sleep(0.05)
    assert published and {channel for channel, _ in published} == {"general"}
    for _, event in published:
        assert c.SetupEvent.model_validate(event).type == "setup"
    assert published[-1][1]["setup"]["ready"]


def test_the_retry_route_queues_a_failed_part(hub, parts, tmp_path, helper, data_dir):
    gone = _part("gone", hub.specs[1], broken=True)
    setup = make(hub, (gone,), tmp_path, helper)
    setup.ensure()
    client = TestClient(create_app(SECRET, data_dir=data_dir, setup=setup))  # no setup thread
    assert [p["state"] for p in client.get("/setup/parts", headers=AUTH).json()["parts"]] == [
        "failed"
    ]
    answer = client.post("/setup/parts/retry", headers=AUTH)
    assert answer.status_code == 200
    state = c.SetupState.model_validate_json(answer.text, strict=True)
    assert [p.state for p in state.parts] == ["queued"] and not state.ready
