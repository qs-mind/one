"""Home and a tender's header (Phase 1, C7), the rest of the contract's rules: what waits in a
running Brief and in the Home conversation, the last opened tender, the Spending-Cap block, the
order of tenders without a date, the sample flag, and the events Lessons Learned and a changed
row send. Synthetic «عينة» data only; no AI is called."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy, home, home_pulse, phase1_contract
from qsone.app import create_app
from qsone.engine import costs
from qsone.engine.store import Store
from qsone.records import ledger
from qsone.tools.lessons import KIND
from tests.conftest import AUTH, SECRET
from tests.test_engine_runner import links
from tests.test_home import new, shown

ASKED = {"en": "Which floor is priced? - sample", "ar": "أنهي دور هيتسعّر؟ - عينة"}
CAP_CARD = {"en": "Raise the cap? - sample", "ar": "نرفع الحد؟ - عينة"}


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir, connectors=links)) as found:
        yield found


def card(kind: str, title: dict, text: str | None = None):
    return SimpleNamespace(
        kind=kind, title=title, payload={"questions": [{"text": text}]} if text else {}
    )


def running(rec, brief_id: str, cards: dict) -> SimpleNamespace:
    """A Brief this core runs now, waiting on `cards` ({card id: card})."""
    return SimpleNamespace(
        brief_id=brief_id,
        state="waiting_engineer",
        step=None,
        waiting={cid: (c, None) for cid, c in cards.items()},
        mapping_files=None,
        instruction=None,
        store=SimpleNamespace(rec=rec),
    )


def cut_off(rec, chat_id: str, project_id: str | None) -> str:
    store = Store(rec, project_id=project_id)
    brief_id = store.new_brief(chat_id, "سعّر - عينة")
    store.set_status(brief_id, "running")
    return brief_id


def test_cards_running_briefs_wait_on_and_the_home_conversations_own(client, monkeypatch):
    app = client.app.state
    pid = new(client, "فيلا - عينة")
    rec = app.projects.get(pid)
    again = cut_off(rec, pid, pid)  # cut off, and this core runs it again
    app.projects._remember(rec)
    engineer = app.engine.engineer_records()
    home_cut = cut_off(engineer, home.GENERAL, None)
    asked = card("question", ASKED, "Ground or first? - sample")
    briefs = {
        pid: [running(rec, again, {"a" * 32: asked})],
        home.GENERAL: [running(engineer, "b" * 32, {"c" * 32: card("cap", CAP_CARD)})],
    }
    monkeypatch.setattr(app.engine, "running", lambda channel: briefs.get(channel, []))

    view = client.get(f"/projects/{pid}/tender", headers=AUTH)
    found = phase1_contract.TenderView.model_validate_json(view.text, strict=True)
    assert [(i.kind, i.id, i.project_id, i.text) for i in found.waiting] == [
        ("question", "a" * 32, pid, "Ground or first? - sample")
    ]  # the running Brief's own cut-off item is gone
    assert found.tender.state == "waiting" and found.tender.waiting == 1

    waiting = {(i["kind"], i["id"], i["project_id"]) for i in shown(client)["waiting"]}
    assert waiting == {
        ("question", "a" * 32, pid),
        ("unfinished", home_cut, None),
        ("cap", "c" * 32, None),
    }


def test_the_last_opened_tender_is_null_when_it_is_not_on_home(client):
    pid = new(client, "مفتوح - عينة")
    client.post(f"/projects/{pid}/open", headers=AUTH)
    assert shown(client)["last_project_id"] == pid
    rec = client.app.state.projects.get(pid)
    with rec.write("engineer", archive_change=True) as conn:
        rec.set_meta(conn, "archived_at", rec.clock())
    client.app.state.projects._remember(rec)
    answer = shown(client)
    assert answer["tenders"] == [] and answer["last_project_id"] is None


def test_a_reached_spending_cap_blocks_the_lead(client):
    new(client, "فيلا - عينة")
    costs.save_caps({"day": "0"})
    zero = costs.usd_text(Decimal(0))
    reason = copy.fill(copy.CAP_STOPPED, scope_name=copy.SCOPE_DAY, spent=zero, cap=zero)
    answer = shown(client)
    assert answer["blocked"] == {"reason": reason, "fix": "caps"}
    assert answer["tenders"][0]["blocked"] == answer["blocked"]


def test_tenders_without_a_date_come_newest_first():
    def row(name: str, state: str = "no_plan", date: str | None = None) -> dict:
        return {"project_id": name, "state": state, "submission_date": date}

    rows = [
        (row("old"), "2026-11-01T08:00:00"),
        (row("done-early", "finished", "2026-09-01"), "2026-08-01T08:00:00"),
        (row("dated", "working", "2026-12-01"), "2026-11-01T09:00:00"),
        (row("new"), "2026-11-03T08:00:00"),
        (row("done-late", "finished", "2026-10-01"), "2026-08-02T08:00:00"),
    ]
    assert [r["project_id"] for r in home._ordered(rows)] == [
        "dated",
        "new",
        "old",
        "done-late",
        "done-early",
    ]


def test_a_tender_with_sample_data_says_so(client):
    plain = new(client, "حقيقي")
    pid = new(client, "عينة")
    rec = client.app.state.projects.get(pid)
    ledger.add_source(rec, kind="sample", title="Sample data", actor="engineer")
    client.app.state.projects._remember(rec)
    rows = {r["project_id"]: r["sample"] for r in shown(client)["tenders"]}
    assert rows == {plain: False, pid: True}


def test_lessons_send_an_event_on_edit_remove_and_undo(client, monkeypatch):
    heard: list[tuple[str, str]] = []
    monkeypatch.setattr(activity, "LISTENERS", [lambda ch, e: heard.append((ch, e["type"]))])
    engineer = client.app.state.engine.engineer_records()
    lesson_id = ledger.add_item(
        engineer, kind=KIND, actor="engineer", fields={"text": "Old - sample.", "kind": "method"}
    )
    path = f"/engineer/lessons/{lesson_id}"
    steps = [
        lambda: client.patch(path, json={"text": "New - sample."}, headers=AUTH),
        lambda: client.post(
            f"/undo/{client.delete(path, headers=AUTH).json()['undo']}", headers=AUTH
        ),
    ]
    for step in steps:
        assert step().status_code in (200, 204)
    assert heard.count(("general", "lessons")) == 3  # edited, removed, put back


def test_a_changed_row_sends_its_events(client, monkeypatch):
    pokes: list[str | None] = []
    monkeypatch.setattr(home_pulse, "_running", SimpleNamespace(poke=pokes.append))
    projects = client.app.state.projects
    pid = new(client, "فيلا - عينة")
    rec = projects.get(pid)
    projects._remember(rec)
    pokes.clear()
    projects._remember(rec)
    assert pokes == []  # nothing changed: nothing sent
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    projects._remember(rec)
    assert pokes == [pid, None]
