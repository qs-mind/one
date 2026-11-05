"""Close a project and archive it (Plan 8, Task 7): the checklist that never blocks, lessons
carried one at a time, the archive and its final backup, read-only, and unarchiving. A scripted
Lead QS only (never a real AI). Synthetic «عينة» data only."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from qsone import copy, usage
from qsone.app import create_app
from qsone.backup import store as backup_store
from qsone.deliverables import store
from qsone.deliverables.comments import add as add_comment
from qsone.deliverables.review import sign_off
from qsone.engine import costs, general
from qsone.engine.runner import Engine
from qsone.engine.tools import call
from qsone.journey import closing
from qsone.projects import Projects
from qsone.records import db, ledger, vault
from qsone.records.files import add_file
from qsone.records.project import RecordsError
from qsone.records.search import search
from qsone.workspace import save_open
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import OPUS, scripted, text
from tests.engine_fakes import call as step
from tests.fakes_tools import tool_ctx
from tests.samples import sample_sheet
from tests.test_backup_store import Machine
from tests.test_engine_runner import FakeLink, links

LESSON = {"text": "راجع وحدات البنود قبل التسعير - عينة", "kind": "correction"}


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


@pytest.fixture
def tracked(monkeypatch) -> list:
    sent: list = []
    monkeypatch.setattr(usage, "track", lambda name, **data: sent.append((name, data)))
    return sent


@pytest.fixture
def machine(data_dir):
    m = Machine(data_dir)
    yield m
    m.projects.close_all()


@pytest.fixture
def engineer(data_dir):
    mine = general.open_engineer_records(data_dir)
    yield mine
    mine.close()


def audit_rows(rec, action: str) -> list[dict]:
    with rec.read() as c:
        rows = c.execute(
            "SELECT actor, row_id, before, after FROM audit WHERE action = ? ORDER BY id", (action,)
        ).fetchall()
    return [
        {"actor": a, "row_id": r, "before": json.loads(b), "after": json.loads(f)}
        for a, r, b, f in rows
    ]


def lesson(rec, **fields) -> str:
    return ledger.add_item(rec, kind="lesson", actor="Lead QS", fields=LESSON | fields)


class FakeBackups:
    """Records when the final backup ran, and whether the project was archived by then."""

    def __init__(self, rec, copies: int):
        self.rec, self.copies, self.calls = rec, copies, []

    def run(self, project_id=None, *, reason: str) -> int:
        self.calls.append((project_id, reason, self.rec.archived_at))
        return self.copies


# Read-only --------------------------------------------------------------------------------------


def test_archived_project_reads_and_searches_but_refuses_changes(machine):
    pid = machine.new_project()
    rec = machine.projects.get(pid)
    closing.archive(rec, machine.backups)
    assert search(rec, "03/02").hits
    with pytest.raises(RecordsError) as e:
        ledger.add_item(rec, kind="boq_item", actor="engineer")
    assert e.value.text == copy.PROJECT_ARCHIVED and e.value.status == 423
    with pytest.raises(RecordsError) as e:
        add_file(rec, "ملحق - عينة.txt", b"addendum", actor="engineer")
    assert e.value.status == 423
    save_open(rec, "files:all", None)  # the open document is not project data


def test_archive_then_the_final_backup_with_nothing_left_to_copy(machine, tmp_path, tracked):
    usb = tmp_path / "usb"
    usb.mkdir()
    machine.backups.set_folder(str(usb))
    pid = machine.new_project()
    rec = machine.projects.get(pid)
    done = closing.archive(rec, machine.backups)
    assert done["backed_up"] is True and done["note"] is None
    assert done["archived_at"] == rec.archived_at
    assert machine.backups.run(reason="timer") == 0  # the archive is already in the backup
    newest = sorted((backup_store.base(usb) / pid).glob("*.db"))[-1]
    conn = db.connect(newest, vault.get_key(pid))
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
    finally:
        conn.close()
    assert meta["archived_at"] == rec.archived_at
    assert ("project_archived", {}) in tracked
    assert [name for name, _ in tracked].count("project_new") == 1


def test_archive_happens_even_when_the_backup_does_not(rec, tracked):
    backups = FakeBackups(rec, copies=0)
    done = closing.archive(rec, backups)
    assert rec.archived_at is not None and done["archived_at"] == rec.archived_at
    assert done["backed_up"] is False and done["note"] == copy.ARCHIVE_BACKUP_FAILED
    assert backups.calls == [(rec.id, "archive", rec.archived_at)]  # archived first, then copied
    again = closing.archive(rec, backups)
    assert again["archived_at"] == done["archived_at"] and len(backups.calls) == 1
    assert len(audit_rows(rec, "archive")) == 1


def test_unarchive_is_audited(rec):
    archived = closing.archive(rec, None)["archived_at"]
    closing.unarchive(rec)
    assert rec.archived_at is None and "archived_at" not in rec.meta()
    (row,) = audit_rows(rec, "unarchive")
    assert row["actor"] == "engineer" and row["row_id"] == rec.id
    assert row["before"] == {"archived_at": archived} and row["after"] == {"archived_at": None}
    lesson(rec)  # changes are taken again
    closing.unarchive(rec)  # not archived: nothing more
    assert len(audit_rows(rec, "unarchive")) == 1


def test_archived_stays_archived_after_reopen(machine):
    pid = machine.new_project()
    at = closing.archive(machine.projects.get(pid), None)["archived_at"]
    machine.projects.close(pid)
    machine.projects.open(pid)
    assert machine.projects.get(pid).archived_at == at
    (listed,) = machine.projects.list()
    assert listed["archived_at"] == at and listed["confidential"] is False
    reopened = Projects(machine.data_dir)
    assert next(p for p in reopened.list() if p["id"] == pid)["archived_at"] == at


# The checklist and the lessons -------------------------------------------------------------------


def test_checklist_lists_open_comments_and_unsigned(rec, engineer):
    sheet = sample_sheet(rec)
    add_comment(
        rec,
        sheet,
        kind="note",
        anchor={"type": "deliverable"},
        body="راجع الكميات - عينة",
        actor="estimator",
    )
    letter = store.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب - عينة",
        language="ar",
        actor="lead_qs",
        blocks=[{"type": "p", "children": [{"text": "نص بدون أرقام - عينة"}]}],
    )
    assert sign_off(rec, letter, actor="engineer") == 1
    got = closing.checklist(rec, engineer)
    sheet_name = store.entry(rec, sheet)["title"]
    assert got["open_comments"] == 1
    assert got["unsigned"] == [{"id": sheet, "name": sheet_name}]
    assert got["reports"] == [{"id": letter, "name": "خطاب - عينة", "revision": 1}]
    assert got["confidential"] is False and got["archived_at"] is None and got["lessons"] == []
    closing.archive(rec, None)  # the checklist never blocks; what was open is in the audit
    (row,) = audit_rows(rec, "archive")
    assert row["after"]["open_comments"] == 1 and row["after"]["unsigned"] == [sheet]


def test_checklist_lists_a_broken_deliverable_as_a_blocker(rec, engineer, monkeypatch):
    """Tender day: the card said «مفيش حاجة هنا بتمنعك» while the priced BOQ did not open."""
    from tests.samples import sample_source
    from tests.test_numbers_newest import _legacy_rate, _row

    sheet = sample_sheet(rec)
    assert closing.checklist(rec, engineer)["broken"] == []
    _legacy_rate(rec, _row(store.view(rec, sheet), "1-1")["item_id"], "15", sample_source(rec))
    got = closing.checklist(rec, engineer)
    [broken] = got["broken"]
    assert broken["id"] == sheet and broken["name"] == store.entry(rec, sheet)["title"]
    assert "1-1" in broken["why"]["ar"] and "الفئة" in broken["why"]["ar"]

    def fails(*a, **k):
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND)

    monkeypatch.setattr(closing.store, "view", fails)  # one that does not open at all
    assert closing.checklist(rec, engineer)["broken"][0]["why"] == copy.DELIVERABLE_NOT_FOUND


async def test_confidential_project_proposes_no_lessons(rec, engineer):
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    assert await closing.propose_lessons(rec, engine=None) is None
    with pytest.raises(RecordsError) as e:
        closing.carry(rec, engineer, lesson(rec), carry=True)
    assert e.value.text == copy.LESSON_STAYS_CONFIDENTIAL
    assert closing.checklist(rec, engineer)["confidential"] is True


async def test_a_carried_lesson_lands_in_engineer_records_once(rec, engineer):
    noted = json.loads(
        await call(
            "note_lesson", LESSON | {"source_ref": "file:abc#sheet=BOQ&row=4"}, tool_ctx(rec)
        )
    )["lesson_id"]
    kept = lesson(rec, text="سجّل مصدر كل سعر - عينة", kind="method")
    assert closing.carry(rec, engineer, kept, carry=False) is False
    closing.archive(rec, None)  # carrying writes only Engineer Records
    assert closing.carry(rec, engineer, noted, carry=True) is True
    assert closing.carry(rec, engineer, noted, carry=True) is True
    assert closing.carry(rec, engineer, noted, carry=False) is True  # carried stays carried
    with engineer.read() as c:
        rows = c.execute("SELECT fields, created_by FROM items WHERE kind = 'lesson'").fetchall()
    assert [(json.loads(f), by) for f, by in rows] == [
        (LESSON | {"from_project": rec.id, "from_lesson": noted}, "engineer")
    ]
    assert [(x["id"], x["carried"]) for x in closing.checklist(rec, engineer)["lessons"]] == [
        (noted, True),
        (kept, False),
    ]
    with pytest.raises(RecordsError) as e:
        closing.carry(rec, engineer, "0" * 32, carry=True)
    assert e.value.status == 404


def test_the_lessons_instruction_keeps_the_client_in_the_project():
    assert len(closing.INSTRUCTION.split()) <= 120
    assert (
        "method or correction" in closing.INSTRUCTION and "never the client" in closing.INSTRUCTION
    )


async def test_the_lessons_brief_with_a_function_model(data_dir, fake_sleep, fake_clock):
    registry = Projects(data_dir)
    pid = registry.create("مناقصة - عينة", "engineer")["id"]
    rec = registry.get(pid)
    lead = scripted(step("note_lesson", LESSON), text("سجّلت درس واحد - عينة."))
    engine = Engine(
        projects=registry,
        data_dir=data_dir,
        connectors=lambda: links(lead=lead),
        clock=fake_clock,
        sleep=fake_sleep,
    )
    try:
        await engine.start()
        brief = await closing.propose_lessons(rec, engine)
        await engine.result(brief)
        assert closing.INSTRUCTION in str(lead.seen[0])
        lessons = closing.checklist(rec, engine.engineer_records())["lessons"]
        assert [(x["text"], x["carried"]) for x in lessons] == [(LESSON["text"], False)]
    finally:
        await engine.shutdown()
        registry.close_all()


# The routes ----------------------------------------------------------------------------------


def test_routes(tracked):
    model = scripted(lambda messages, info: text("تمام - عينة"))
    found = [FakeLink("anthropic", "Claude", "anthropic", {OPUS.choice.model: model}, [OPUS])]
    with TestClient(create_app(SECRET, connectors=lambda: found)) as client:
        pid = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]
        got = client.get(f"/projects/{pid}/closing", headers=AUTH).json()
        assert {k: got[k] for k in ("open_comments", "unsigned", "reports", "confidential")} == {
            "open_comments": 0,
            "unsigned": [],
            "reports": [],
            "confidential": False,
        }
        carry = client.post(
            f"/projects/{pid}/lessons/{'0' * 32}", json={"carry": True}, headers=AUTH
        )
        assert carry.status_code == 404
        engine = client.app.state.engine
        real_active = engine.active
        engine.active = lambda chat_id: "b" * 32
        r = client.post(f"/projects/{pid}/archive", headers=AUTH)
        assert r.status_code == 409 and r.json()["error"] == copy.ARCHIVE_WAITS_FOR_BRIEF
        engine.active = real_active
        r = client.post(f"/projects/{pid}/archive", headers=AUTH)
        assert r.status_code == 200
        done = r.json()
        assert done["archived_at"] and done["backed_up"] is False  # no Backup folder picked
        assert done["note"] == copy.ARCHIVE_BACKUP_FAILED
        listed = next(
            p for p in client.get("/projects", headers=AUTH).json()["projects"] if p["id"] == pid
        )
        assert listed["archived_at"] == done["archived_at"] and listed["confidential"] is False
        name = quote("خطاب - عينة.txt")
        r = client.post(f"/projects/{pid}/files?name={name}", content=b"letter", headers=AUTH)
        assert r.status_code == 423 and r.json()["error"] == copy.PROJECT_ARCHIVED
        r = client.post(f"/projects/{pid}/lessons/propose", headers=AUTH)
        assert r.status_code == 423  # its chat is part of the project
        r = client.post(f"/projects/{pid}/unarchive", headers=AUTH)
        assert r.json() == {"archived_at": None}
        r = client.post(f"/projects/{pid}/lessons/propose", headers=AUTH)
        assert r.status_code == 202 and set(r.json()) == {"brief_id"}
        rec = client.app.state.projects.get(pid)
        with rec.write("engineer") as conn:
            rec.set_meta(conn, "confidential", "1")
        r = client.post(f"/projects/{pid}/lessons/propose", headers=AUTH)
        assert r.status_code == 409 and r.json()["error"] == copy.LESSON_STAYS_CONFIDENTIAL
    assert ("project_archived", {}) in tracked
