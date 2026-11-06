"""The search model download: resumable over HTTP ranges, and no file is used until its SHA-256
matches. Everything goes through `FakeHub`; no test opens a socket."""

import shutil
import threading
import time
from threading import Event

import pytest
import truststore

from qsone import copy
from qsone.meaning import download as download_module
from qsone.meaning.download import (
    SPARE,
    DownloadError,
    DownloadStopped,
    NoSpace,
    default_client,
    download,
    folder,
    installed,
    remaining,
)
from qsone.meaning.manifest import MODELS
from tests.hub import FakeHub


@pytest.fixture
def hub():
    return FakeHub()


def no_sleep(seconds: float) -> None:
    pass


def total(specs) -> int:
    return sum(s.size for s in specs)


def test_downloads_every_file_checked_and_in_place(tmp_path, hub):
    specs = hub.specs
    seen = []
    download(
        specs,
        tmp_path,
        client=hub.client(),
        stop=Event(),
        on_progress=lambda d, t: seen.append((d, t)),
    )
    assert installed(specs, tmp_path) and not list(tmp_path.rglob("*.part"))
    assert seen[-1] == (total(specs),) * 2
    assert all(t == total(specs) for _, t in seen) and [d for d, _ in seen] == sorted(
        d for d, _ in seen
    )
    assert len(hub.requests) == 4
    assert all(any(f"/resolve/{s.revision}/" in str(r.url) for s in specs) for r in hub.requests)
    for spec in specs:
        for f in spec.files:
            assert (folder(spec, tmp_path) / f.path).read_bytes() == hub.files[spec.url(f)]
    assert remaining(specs, tmp_path) == 0


def test_a_dropped_connection_resumes_from_the_part(tmp_path, hub):
    hub.drop_after(100_000, times=1)
    slept = []
    download(hub.specs, tmp_path, client=hub.client(), stop=Event(), sleep=slept.append)
    assert installed(hub.specs, tmp_path)
    assert "range" not in hub.requests[0].headers
    assert hub.requests[1].headers["range"] == "bytes=100000-"
    assert slept == [2]


def test_stop_keeps_the_part_and_the_next_run_continues(tmp_path, hub):
    stop = Event()
    with pytest.raises(DownloadStopped):
        download(
            hub.specs,
            tmp_path,
            client=hub.client(),
            stop=stop,
            on_progress=lambda d, t: stop.set() if d > 50_000 else None,
        )
    assert list(tmp_path.rglob("*.part")) and not installed(hub.specs, tmp_path)
    assert remaining(hub.specs, tmp_path) < total(hub.specs)
    asked = len(hub.requests)
    download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    assert installed(hub.specs, tmp_path)
    assert hub.requests[asked].headers["range"].startswith("bytes=")  # continued, not started again


def test_a_server_that_ignores_ranges_starts_the_file_again(tmp_path, hub):
    hub.drop_after(100_000, times=1)
    hub.ignore_range()
    download(hub.specs, tmp_path, client=hub.client(), stop=Event(), sleep=no_sleep)
    assert hub.requests[1].headers["range"] == "bytes=100000-"  # asked, answered 200
    assert installed(hub.specs, tmp_path)
    spec, f = hub.specs[0], hub.specs[0].files[0]
    assert (folder(spec, tmp_path) / f.path).read_bytes() == hub.files[spec.url(f)]


def test_a_part_longer_than_the_file_is_deleted(tmp_path, hub):
    spec, f = hub.specs[0], hub.specs[0].files[0]
    part = folder(spec, tmp_path) / (f.path + ".part")
    part.parent.mkdir(parents=True)
    part.write_bytes(b"x" * (f.size + 10))
    download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    assert installed(hub.specs, tmp_path) and "range" not in hub.requests[0].headers


def test_a_wrong_byte_is_never_used(tmp_path, hub):
    hub.corrupt()
    with pytest.raises(DownloadError) as caught:
        download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    assert caught.value.text == copy.MEANING_FILE_DAMAGED
    spec, f = hub.specs[0], hub.specs[0].files[0]
    assert not (folder(spec, tmp_path) / f.path).exists()
    assert not list(tmp_path.rglob("*.part")) and not installed(hub.specs, tmp_path)


def test_keeps_failing_says_so_and_keeps_the_part(tmp_path, hub):
    hub.drop_after(10, times=99)
    slept = []
    with pytest.raises(DownloadError) as caught:
        download(hub.specs, tmp_path, client=hub.client(), stop=Event(), sleep=slept.append)
    assert caught.value.text == copy.MEANING_DOWNLOAD_FAILED
    assert slept == [2, 4, 8] and len(hub.requests) == 4
    (part,) = tmp_path.rglob("*.part")
    assert part.stat().st_size == 40


def test_not_found_does_not_retry(tmp_path, hub):
    hub.not_found()
    with pytest.raises(DownloadError) as caught:
        download(hub.specs, tmp_path, client=hub.client(), stop=Event(), sleep=no_sleep)
    assert caught.value.text == copy.MEANING_DOWNLOAD_FAILED and len(hub.requests) == 1


def test_no_space_asks_nothing(tmp_path, hub, monkeypatch):
    usage = shutil.disk_usage(tmp_path)
    free = total(hub.specs) + 200_000_000 - 1
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage._replace(free=free))
    with pytest.raises(NoSpace) as caught:
        download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    need = total(hub.specs) + 200_000_000  # what is still to come and the spare, worked out
    assert caught.value.need == need and hub.requests == []
    assert caught.value.text == copy.fill(copy.MEANING_NO_SPACE, size=f"{round(need / 1e6)} MB")
    assert "201 MB" in caught.value.text["en"] and "201 MB" in caught.value.text["ar"]
    # the real model: 135 MB to come and the 200 MB spare
    assert round((sum(s.size for s in MODELS) + SPARE) / 1e6) == 335


def test_a_try_that_moved_on_counts_the_retries_again(tmp_path, hub, monkeypatch):
    monkeypatch.setattr(download_module, "MOVED_ON", 50_000)
    hub.drop_after(60_000, times=8)  # far more drops than 3 retries, but each one moved on
    slept = []
    download(hub.specs, tmp_path, client=hub.client(), stop=Event(), sleep=slept.append)
    assert installed(hub.specs, tmp_path) and len(slept) > 3 and max(slept) <= 4


def test_the_wait_between_tries_ends_when_stopped(tmp_path, hub):
    hub.drop_after(10, times=99)
    stop = Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()
    with pytest.raises(DownloadStopped):
        download(hub.specs, tmp_path, client=hub.client(), stop=stop)  # waits on `stop`, 2 s
    assert time.monotonic() - started < 1.5


def put_by_hand(hub, root) -> None:
    for spec in hub.specs:
        for f in spec.files:
            path = folder(spec, root) / f.path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(hub.files[spec.url(f)])


def test_files_put_in_place_by_hand_are_hashed_once(tmp_path, hub):
    put_by_hand(hub, tmp_path)
    assert not installed(hub.specs, tmp_path)  # not yet checked
    download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    assert installed(hub.specs, tmp_path) and hub.requests == []


def test_a_wrong_file_put_by_hand_is_downloaded_again(tmp_path, hub):
    put_by_hand(hub, tmp_path)
    spec, f = hub.specs[1], hub.specs[1].files[1]
    (folder(spec, tmp_path) / f.path).write_bytes(b"\0" * f.size)
    download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    assert installed(hub.specs, tmp_path) and [str(r.url) for r in hub.requests] == [spec.url(f)]
    assert (folder(spec, tmp_path) / f.path).read_bytes() == hub.files[spec.url(f)]


def test_installed_notices_a_missing_or_cut_file(tmp_path, hub):
    download(hub.specs, tmp_path, client=hub.client(), stop=Event())
    spec = hub.specs[0]
    model = folder(spec, tmp_path) / spec.files[1].path
    data = model.read_bytes()
    model.write_bytes(data[:-1])
    assert not installed(hub.specs, tmp_path)
    model.write_bytes(data)
    assert installed(hub.specs, tmp_path)
    (folder(spec, tmp_path) / spec.files[0].path).unlink()
    assert not installed(hub.specs, tmp_path)
    assert installed(hub.specs[1:], tmp_path)


def test_default_client_uses_the_system_trust_store():
    with default_client() as client:
        assert isinstance(client._transport._pool._ssl_context, truststore.SSLContext)
        assert client.follow_redirects and client.timeout.read == 30
        assert "QS Mind One" in client.headers["user-agent"]
