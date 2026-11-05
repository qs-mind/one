"""Before an update installs (Plan 8, Task 12): Briefs pause at their Checkpoints, the projects
are backed up and every open project is closed; after the restart, Usage Stats count the update
from the versions in settings.json. Synthetic «عينة» data only; Umami is the loopback fake."""

import pytest
from fastapi.testclient import TestClient

import qsone
from qsone import settings, usage
from qsone.app import create_app
from tests.conftest import AUTH, SECRET


@pytest.fixture
def app(data_dir):
    return create_app(SECRET, data_dir=data_dir)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fake_briefs(app):
    """Plan 4's pause, recorded: two Briefs were running."""
    paused = []

    async def pause_all() -> int:
        paused.append(True)
        return 2

    app.state.engine.pause_all = pause_all
    return paused


@pytest.fixture
def backups(app):
    """The real Backups, with each run's reason recorded."""
    runner, reasons = app.state.backups, []
    real = runner.run

    def run(project_id=None, *, reason):
        reasons.append(reason)
        return real(project_id, reason=reason)

    runner.run = run
    return reasons


@pytest.fixture
def projects(client, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    assert client.put("/backup/folder", json={"path": str(usb)}, headers=AUTH).status_code == 200
    ids = [
        client.post("/projects", json={"name": f"برج {i} - عينة"}, headers=AUTH).json()["id"]
        for i in range(2)
    ]
    client.post(f"/projects/{ids[1]}/close", headers=AUTH)
    return ids


def test_prepare_update_pauses_backs_up_and_closes(client, projects, backups, fake_briefs):
    r = client.post("/app/prepare-update", headers=AUTH)
    assert r.status_code == 200
    # the engineer's own records and the open project; the other was copied when it closed
    assert r.json() == {"paused_briefs": 2, "backed_up": 2}
    assert fake_briefs == [True] and backups == ["update"]
    listed = client.get("/projects", headers=AUTH).json()["projects"]
    assert [p["open"] for p in listed] == [False, False]
    assert "update_to" not in settings.load()  # no version given: nothing to count later


def test_prepare_update_keeps_the_version_it_installs(client, fake_briefs):
    r = client.post("/app/prepare-update", json={"to": "0.1.1"}, headers=AUTH)
    assert r.json() == {"paused_briefs": 2, "backed_up": 0}  # no backup folder, no project
    assert settings.load()["update_to"] == "0.1.1"
    for bad in ({"to": "0.1.1 مشروع"}, {"to": ""}, {"version": "0.1.1"}):
        assert client.post("/app/prepare-update", json=bad, headers=AUTH).status_code == 422
    assert client.post("/app/prepare-update").status_code == 401


def sent(umami) -> list[dict]:
    usage.Sender().flush()
    return [e["payload"]["data"] for e in umami.received if e["payload"]["name"] == "update"]


@pytest.fixture
def stats_on(monkeypatch):
    monkeypatch.setenv("QSONE_USAGE_WEBSITE_ID", "website-sample")
    usage.set_on(True)


def test_the_first_start_counts_no_update_and_keeps_the_version(stats_on, fake_umami):
    usage.updated()
    assert settings.load()["version"] == qsone.__version__
    usage.updated()  # the same version again: nothing
    assert sent(fake_umami) == []


def test_a_new_version_counts_a_finished_update(stats_on, fake_umami):
    settings.save("version", "0.0.9")
    settings.save("update_to", qsone.__version__)
    usage.updated()
    assert sent(fake_umami) == [{"from": "0.0.9", "to": qsone.__version__, "ok": True}]
    assert settings.load()["version"] == qsone.__version__
    assert "update_to" not in settings.load()


def test_the_same_version_with_an_update_pending_counts_a_failed_one(stats_on, fake_umami):
    settings.save("version", qsone.__version__)
    settings.save("update_to", "9.9.9")
    usage.updated()
    assert sent(fake_umami) == [{"from": qsone.__version__, "to": "9.9.9", "ok": False}]
    assert "update_to" not in settings.load()


def test_nothing_is_counted_without_a_yes(fake_umami, monkeypatch):
    monkeypatch.setenv("QSONE_USAGE_WEBSITE_ID", "website-sample")
    settings.save("version", "0.0.9")
    usage.updated()
    assert sent(fake_umami) == []
    assert settings.load()["version"] == qsone.__version__  # still kept for the next one
