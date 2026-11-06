"""Usage Stats (Plan 8, Task 9): nothing before yes or after no; only allow-listed numbers and
codes; a crash report holds no message and no path. Every send goes to `FakeUmami` on
127.0.0.1, never to the real server. Synthetic «عينة» data only."""

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from qsone import usage
from qsone.app import create_app
from qsone.journey import setup_state
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import FakeSleep, scripted, text
from tests.test_engine_runner import links


@pytest.fixture(autouse=True)
def website(monkeypatch):
    monkeypatch.setenv("QSONE_USAGE_WEBSITE_ID", "website-sample")


def names(umami) -> list[str]:
    return [e["payload"]["name"] for e in umami.received]


def queued(data_dir) -> list[str]:
    path = data_dir / usage.QUEUE_FILE
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def test_nothing_is_sent_before_yes(fake_umami, data_dir):
    assert usage.is_on() is None
    usage.track("app_start", version="0.1.0", os="linux", arch="x64", language="ar")
    assert usage.Sender().flush() == 0
    assert fake_umami.received == [] and queued(data_dir) == []


def test_before_the_choice_nothing_is_said_either(caplog, fake_umami, data_dir):
    """Real walk: «Usage Stats: event ai_link refused» was logged before the usage choice, for
    the "standard" link (Gemini, Ollama, …) the first launch saves."""
    usage.track("ai_link", via="standard")
    usage.track("anything", x=1)
    assert "Usage Stats" not in caplog.text and queued(data_dir) == []
    usage.set_on(True)
    usage.track("ai_link", via="standard")  # another provider is a link the list knows
    assert usage.Sender().flush() == 1 and "refused" not in caplog.text


def test_nothing_is_sent_after_no(fake_umami, data_dir):
    usage.set_on(False)
    usage.track("app_start", version="0.1.0", os="linux", arch="x64", language="ar")
    usage.Sender().flush()
    assert fake_umami.received == [] and queued(data_dir) == []


def test_after_yes_only_allowed_numbers_go(fake_umami):
    usage.set_on(True)
    usage.track("brief_done", desks=2, specialists=3, off_desk=False, cost_usd_cents=184, minutes=7)
    usage.track(
        "brief_done",
        desks="Pricing Desk for مستشفى",  # refused: not an int
        specialists=3,
        off_desk=False,
        cost_usd_cents=184,
        minutes=7,
    )
    usage.track("anything", x=1)  # refused: unknown event
    usage.track("brief_done", desks=2)  # refused: keys missing
    usage.track("ai_link", via="api_key", key="sk-sample")  # refused: an unknown key
    usage.track("ai_link", via="openai")  # refused: not in the list
    usage.track("backup_run", projects=True, ok=True)  # refused: a boolean is not a count
    usage.track("update", **{"from": "0.1.0", "to": "0.1.1 مشروع", "ok": True})  # free text
    assert usage.Sender().flush() == 1
    assert names(fake_umami) == ["brief_done"]
    sent = fake_umami.received[0]
    assert sent["type"] == "event"
    assert sent["payload"] == {
        "website": "website-sample",
        "hostname": "one.qsmind.app",
        "url": "/app",
        "name": "brief_done",
        "data": {
            "desks": 2,
            "specialists": 3,
            "off_desk": False,
            "cost_usd_cents": 184,
            "minutes": 7,
        },
        "language": setup_state.language(),
    }
    said = json.dumps(fake_umami.received, ensure_ascii=False)
    assert "مستشفى" not in said and "sk-sample" not in said


def test_a_refused_event_is_logged_by_its_name_only(caplog):
    usage.set_on(True)
    usage.track("brief_done", desks="Pricing Desk for مستشفى")
    usage.track("مشروع سري", x=1)
    assert "brief_done" in caplog.text
    assert "مستشفى" not in caplog.text and "مشروع" not in caplog.text


def test_crash_has_no_message_and_no_path(fake_umami):
    usage.set_on(True)
    try:
        raise KeyError("خرسانة /home/user/مشروع")
    except KeyError as e:
        usage.crash(e)
    usage.Sender().flush()
    data = fake_umami.received[0]["payload"]["data"]
    assert data["kind"] == "KeyError" and data["from"] == "core"
    assert re.fullmatch(r"qsone\.[\w.]+:\d+|qsone:0", data["where"])
    said = json.dumps(fake_umami.received, ensure_ascii=False)
    assert "home" not in said and "خرسانة" not in said and "مشروع" not in said


def test_a_crash_names_the_deepest_frame_in_qsone(fake_umami):
    usage.set_on(True)
    try:
        setup_state.mark("no-such-step", "done")
    except KeyError as e:
        usage.crash(e)
    usage.Sender().flush()
    where = fake_umami.received[0]["payload"]["data"]["where"]
    assert re.fullmatch(r"qsone\.journey\.setup_state:\d+", where)


def test_offline_keeps_at_most_200(fake_umami, data_dir):
    usage.set_on(True)
    fake_umami.down = True
    for _ in range(250):
        usage.track("project_archived")
    assert usage.Sender().flush() == 0
    assert len(queued(data_dir)) == 200
    fake_umami.down = False
    assert usage.Sender().flush() == 200
    assert queued(data_dir) == []


def test_a_server_error_keeps_the_queue_and_a_refusal_drops_it(fake_umami, data_dir):
    usage.set_on(True)
    usage.track("project_archived")
    fake_umami.status = 503
    assert usage.Sender().flush() == 0 and len(queued(data_dir)) == 1
    fake_umami.status = 400
    assert usage.Sender().flush() == 0 and queued(data_dir) == []


def test_off_empties_the_queue(fake_umami, data_dir):
    usage.set_on(True)
    fake_umami.down = True
    usage.track("project_archived")
    assert len(queued(data_dir)) == 1
    usage.set_on(False)
    assert queued(data_dir) == []
    fake_umami.down = False
    usage.track("project_archived")
    assert usage.Sender().flush() == 0 and fake_umami.received == []  # not even the "off"


def test_umami_does_not_take_one_for_a_bot(fake_umami):
    from tests.fakes import is_bot

    usage.set_on(True)
    usage.track("project_archived")
    assert usage.Sender().flush() == 1
    assert names(fake_umami) == ["project_archived"]
    [agent] = fake_umami.agents
    assert not is_bot(agent) and re.fullmatch(
        r"Mozilla/5\.0 \([^)]+\) QSMindOne/\d+\.\d+\.\d+", agent
    )


def test_no_website_id_sends_nothing(fake_umami, monkeypatch, data_dir):
    monkeypatch.delenv("QSONE_USAGE_WEBSITE_ID")
    usage.set_on(True)
    usage.track("project_archived")
    assert usage.Sender().flush() == 0 and fake_umami.received == []
    assert len(queued(data_dir)) == 1  # kept until One knows its Umami


def test_core_stopped_from_the_last_run(data_dir, fake_umami):
    usage.set_on(True)
    note = data_dir / "last-core-exit.json"
    note.write_text('{"code": 3}', encoding="utf-8")
    usage.core_stopped(data_dir)
    assert not note.exists()
    note.write_text('{"code": null}', encoding="utf-8")  # a signal ended it
    usage.core_stopped(data_dir)
    usage.core_stopped(data_dir)  # no note: nothing
    usage.Sender().flush()
    assert [e["payload"]["data"] for e in fake_umami.received] == [{"code": 3}, {"code": -1}]


def test_the_sender_runs_and_stops(fake_umami, monkeypatch):
    monkeypatch.setattr(usage, "EVERY", 0.01)
    usage.set_on(True)
    usage.track("project_archived")
    sender = usage.Sender()
    sender.start()
    try:
        for _ in range(500):
            if fake_umami.received:
                break
            time.sleep(0.01)
    finally:
        sender.stop()
    assert names(fake_umami) == ["project_archived"]


# The routes --------------------------------------------------------------------------------


@pytest.fixture
def client(data_dir):
    lead = scripted(text("تم - عينة"))
    app = create_app(SECRET, connectors=lambda: links(lead=lead), sleep=FakeSleep())
    with TestClient(app) as client:
        yield client


def test_routes(client, fake_umami):
    assert client.get("/settings/usage-stats", headers=AUTH).json() == {"on": None}
    assert client.put("/settings/usage-stats", json={"on": True}, headers=AUTH).json() == {
        "on": True
    }
    assert client.get("/settings/usage-stats", headers=AUTH).json() == {"on": True}
    good = {"from": "screen", "kind": "TypeError", "where": "Chat.tsx:120", "version": "0.1.0"}
    assert client.post("/usage/crash", json=good, headers=AUTH).status_code == 204
    shell = {"from": "shell", "kind": "panic", "where": "qs_mind_one::core:88", "version": "0.1.0"}
    assert client.post("/usage/crash", json=shell, headers=AUTH).status_code == 204
    for bad in (
        good | {"where": "https://x.example/app.js:1"},  # not our code
        good | {"where": "/home/user/مشروع/Chat.tsx:1"},  # a path
        good | {"kind": "TypeError: cannot read خرسانة"},  # a message
        good | {"from": "core"},  # the core reports its own
        good | {"message": "x"},
        shell | {"where": "tokio::runtime:1"},  # not our crate
    ):
        assert client.post("/usage/crash", json=bad, headers=AUTH).status_code == 422
    usage.Sender().flush()
    crashes = [e["payload"]["data"] for e in fake_umami.received if e["payload"]["name"] == "crash"]
    assert crashes == [good, shell]
    assert client.put("/settings/usage-stats", json={"on": False}, headers=AUTH).json() == {
        "on": False
    }
    assert client.get("/settings/usage-stats", headers=AUTH).json() == {"on": False}
    assert client.get("/settings/usage-stats").status_code == 401


def test_skipping_the_step_means_dont_share(client):
    client.put("/setup/usage", json={"state": "skipped"}, headers=AUTH)
    assert usage.is_on() is False


def test_skipping_after_yes_keeps_yes(client):
    usage.set_on(True)
    client.put("/setup/usage", json={"state": "skipped"}, headers=AUTH)
    assert usage.is_on() is True


def test_steps_and_a_brief_are_counted(client, fake_umami):
    usage.set_on(True)
    client.put("/setup/language", json={"state": "done", "lang": "ar"}, headers=AUTH)
    client.put("/setup/ai", json={"state": "skipped"}, headers=AUTH)
    r = client.post("/chat", json=ui_message("سؤال - عينة") | {"id": "general"}, headers=AUTH)
    assert "تم - عينة" in r.text
    usage.Sender().flush()
    assert names(fake_umami) == ["setup_step", "setup_step", "ai_link", "brief_done"]
    data = [e["payload"]["data"] for e in fake_umami.received]
    assert data[0] == {"step": "language", "state": "done"} and data[2] == {"via": "none"}
    done = data[3]
    assert done["desks"] == 0 and done["specialists"] == 0 and done["off_desk"] is False
    assert type(done["cost_usd_cents"]) is int and type(done["minutes"]) is int
    assert all(e["payload"]["language"] == "ar" for e in fake_umami.received)


def test_app_start_is_counted_when_on(data_dir, fake_umami):
    usage.set_on(True)
    with TestClient(create_app(SECRET, connectors=lambda: [], sleep=FakeSleep())):
        pass
    usage.Sender().flush()
    [start] = fake_umami.received
    data = start["payload"]["data"]
    assert start["payload"]["name"] == "app_start" and set(data) == {
        "version",
        "os",
        "arch",
        "language",
    }


def test_a_crash_in_a_request_is_reported(data_dir, fake_umami):
    usage.set_on(True)
    app = create_app(SECRET, connectors=lambda: [], sleep=FakeSleep())

    @app.get("/boom")
    def boom():
        raise ValueError("خرسانة /home/user/مشروع")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/boom", headers=AUTH).status_code == 500
    usage.Sender().flush()
    crashes = [e["payload"]["data"] for e in fake_umami.received if e["payload"]["name"] == "crash"]
    assert [c["kind"] for c in crashes] == ["ValueError"]
    assert "home" not in json.dumps(crashes) and "خرسانة" not in json.dumps(crashes)


def test_thread_crashes_are_reported(fake_umami, monkeypatch):
    import sys
    import threading

    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    usage.install_hooks()
    usage.set_on(True)

    def fail():
        raise RuntimeError("مشروع")

    worker = threading.Thread(target=fail)
    worker.start()
    worker.join()
    usage.Sender().flush()
    assert [e["payload"]["data"]["kind"] for e in fake_umami.received] == ["RuntimeError"]
