"""The Lead's kit (Phase 1, C7): the engineer's profile, Lessons Learned and one line per tender,
at most 2 KB, given to the Lead at the start of any work. A Confidential Project is in its own
kit only. Scripted models; no real AI. Synthetic «عينة» data only."""

import pytest
from fastapi.testclient import TestClient

from qsone import home
from qsone.app import create_app
from qsone.engine import kit
from qsone.records import ledger
from qsone.tools.lessons import KIND
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import FakeSleep, scripted
from tests.test_engine_runner import links


@pytest.fixture
def client(data_dir):
    return TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))


def new(client, name: str, *, confidential: bool = False) -> str:
    pid = client.post("/projects", json={"name": name}, headers=AUTH).json()["id"]
    if confidential:
        rec = client.app.state.projects.get(pid)
        with rec.write("engineer") as conn:
            rec.set_meta(conn, "confidential", "1")
    return pid


def lesson(client, text: str, project_id: str | None = None) -> str:
    fields = {"text": text, "kind": "method"} | ({"from_project": project_id} if project_id else {})
    engineer = client.app.state.engine.engineer_records()
    return ledger.add_item(engineer, kind=KIND, actor="engineer", fields=fields)


def kit_of(client, project_id: str | None) -> str:
    app = client.app.state
    return kit.text(app.projects, app.engine, project_id)


def test_kit_contents(client):
    profile = {"first_name": "A", "last_name": "B", "position": "Senior QS", "company": "Sample Co"}
    profile |= {"org_type": "contractor", "country": "EG", "currency": "EGP"}
    assert client.put("/engineer/profile", json=profile, headers=AUTH).status_code == 200
    one = new(client, "فيلا - عينة")
    two = new(client, "مدرسة - عينة")
    lesson(client, "Check the BOQ units before pricing - sample.")
    lesson(client, "Ask for the addendum list first - sample.")

    found = kit_of(client, one)
    line = "The engineer: first name A; position Senior QS; works for a contractor; based in Egypt."
    assert line in found
    assert "Sample Co" not in found and "EGP" not in found  # never the company or the currency
    assert found.count("- فيلا - عينة (this tender) | no plan yet | no date\n") == 1
    assert found.count("- مدرسة - عينة |") == 1 and two
    newest, older = found.index("addendum"), found.index("BOQ units")
    assert newest < older  # newest first
    assert found.startswith("<<data id=") and found.endswith(">>")


def test_kit_excludes_confidential(client):
    open_one = new(client, "مكشوف - عينة")
    secret = new(client, "سري جدا - عينة", confidential=True)
    assert "سري جدا" not in kit_of(client, open_one)
    assert "سري جدا" not in kit_of(client, None)  # the Home conversation's kit
    assert "سري جدا - عينة (this tender)" in kit_of(client, secret)

    answer = client.get("/home", headers=AUTH).json()
    assert [r["confidential"] for r in answer["tenders"] if r["project_id"] == secret] == [True]
    assert answer["summary"] is None  # nothing writes one yet, and none may name it


def test_lessons_of_a_tender_made_confidential_stay_in_its_own_kit(client):
    """A tender's lessons carried at close-out, and the tender marked Confidential after: they
    are in its own kit only, never in another tender's or in Home's."""
    secret, other = new(client, "سري - عينة"), new(client, "مكشوف - عينة")
    lesson(client, "Secret client's slab rate - sample.", secret)
    lesson(client, "Ask for the addendum list first - sample.", other)
    lesson(client, "Saved from Home - sample.")
    rec = client.app.state.projects.get(secret)
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    for place in (other, None):
        found = kit_of(client, place)
        assert "slab rate" not in found and "addendum" in found and "Saved from Home" in found
    assert "slab rate" in kit_of(client, secret)


def test_kit_size(client, monkeypatch):
    """At most 2 KB for 20 tenders with long names and plans, and every tender is in it; the
    lessons that do not fit are counted, newest kept."""
    plan = {
        "status": "approved",
        "stages": [
            {"status": s, "title": {"en": "Pricing of the structural works " * 3, "ar": "تسعير"}}
            for s in ("approved", "now", "pending", "pending")
        ],
    }
    monkeypatch.setattr(home, "plan_reader", lambda rec: plan)
    for n in range(20):
        new(client, f"Tender {n:02} - a long sample name for a big project - عينة")
    for n in range(30):
        lesson(client, f"Lesson {n:02}: " + "a long sample lesson about method " * 8)

    found = kit_of(client, None)
    assert len(found) <= kit.LIMIT
    assert all(f"Tender {n:02}" in found for n in range(20))
    assert "Lesson 29" in found and "more lessons not shown" in found


def test_the_lead_gets_the_kit_at_the_start_of_work(data_dir):
    model = scripted("تمام - عينة")
    app = create_app(SECRET, connectors=lambda: links(lead=model), sleep=FakeSleep())
    with TestClient(app) as client:
        pid = new(client, "مشروع الكيت - عينة")
        lesson(client, "Price the steel by the ton - sample.")
        body = ui_message("ابدأ - عينة") | {"id": pid}
        assert client.post("/chat", json=body, headers=AUTH).status_code == 200
    instructions = model.seen[0][-1].instructions
    assert "مشروع الكيت - عينة (this tender)" in instructions
    assert "Price the steel by the ton - sample." in instructions
