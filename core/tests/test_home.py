"""Home and a tender's header (Phase 1, C7): GET /home and GET /projects/{id}/tender answer from
what the core holds, in the contract's order and states, and the Lead's summary never disagrees
with the lists under it. Synthetic «عينة» data only; no AI is called."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from qsone import activity, copy, home, home_pulse, home_summary, phase1_contract
from qsone.app import create_app
from qsone.engine.store import Store
from qsone.journey import understand
from qsone.records import files
from qsone.records.project import Records
from tests.conftest import AUTH, SECRET
from tests.test_engine_runner import links


@pytest.fixture
def client(data_dir):
    return TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))


def new(client, name: str, *, due: str | None = None, confidential: bool = False) -> str:
    pid = client.post("/projects", json={"name": name}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(pid)
    if due:
        understand.correct(rec, {"submission_date": due}, approve=False)
    if confidential:
        with rec.write("engineer") as conn:
            rec.set_meta(conn, "confidential", "1")
    return pid


def shown(client) -> dict:
    answer = client.get("/home", headers=AUTH)
    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store"
    return phase1_contract.Home.model_validate_json(answer.text, strict=True).model_dump(
        mode="json"
    )


def plan(*statuses: str, status: str = "approved") -> dict:
    stages = [
        {"id": f"{n:032x}", "title": {"en": f"Stage {n}", "ar": f"مرحلة {n}"}, "status": s}
        for n, s in enumerate(statuses, 1)
    ]
    return {"status": status, "stages": stages}


def test_home_rows(client, monkeypatch):
    """Each tender's stage, its index among the stages, their count, the submission date and
    its source, files, and what waits; in the order the contract fixes."""
    late = new(client, "متأخر - عينة", due="2026-12-20")
    soon = new(client, "قريب - عينة", due="2026-12-01")
    undated = new(client, "بلا موعد - عينة")
    finished = new(client, "منتهي - عينة", due="2026-10-01")
    rec = client.app.state.projects.get(soon)
    files.add_file(rec, "boq.xlsx", b"sample bytes", actor="engineer")
    plans = {soon: plan("approved", "now", "pending"), finished: plan("approved", "approved")}
    monkeypatch.setattr(home, "plan_reader", lambda r: plans.get(r.id))
    for pid in (soon, finished):  # a plan changed: the row is read again
        client.app.state.projects._remember(client.app.state.projects.get(pid))

    rows = shown(client)["tenders"]
    assert [r["project_id"] for r in rows] == [soon, late, undated, finished]
    first = rows[0]
    assert first["stage"] == {"en": "Stage 2", "ar": "مرحلة 2"}
    assert first["stages"] == ["approved", "now", "pending"]
    assert first["submission_date"] == "2026-12-01"
    assert first["submission_source"]["kind"] == "engineer"
    assert first["submission_source"]["dated"] is not None
    assert (first["files_total"], first["files_read"], first["waiting"]) == (1, 0, 0)
    assert first["state"] == "working"  # approved plan, nothing runs: the driver is next
    assert rows[1]["state"] == "no_plan" and rows[1]["stages"] == []
    assert rows[3]["state"] == "finished"


def test_a_cut_off_brief_waits_and_a_closed_tender_answers_from_memory(client, monkeypatch):
    pid = new(client, "مقطوع - عينة")
    rec = client.app.state.projects.get(pid)
    store = Store(rec, project_id=pid)
    brief = store.new_brief(pid, "سعّر - عينة")
    store.set_status(brief, "running")
    client.post(f"/projects/{pid}/close", headers=AUTH)

    def never(folder):
        raise AssertionError("a closed project was opened")

    monkeypatch.setattr(Records, "open", never)
    view = client.get(f"/projects/{pid}/tender", headers=AUTH)
    assert view.status_code == 200
    found = phase1_contract.TenderView.model_validate_json(view.text, strict=True)
    assert [(i.kind, i.id, i.blocking) for i in found.waiting] == [("unfinished", brief, True)]
    assert found.tender.state == "waiting" and found.tender.waiting == 1
    assert found.tender.line.model_dump() == copy.WAITING_UNFINISHED
    assert shown(client)["waiting"][0]["id"] == brief


def test_unknown_unreadable_and_archived_tenders(client, data_dir):
    pid = new(client, "مؤرشف - عينة")
    rec = client.app.state.projects.get(pid)
    with rec.write("engineer", archive_change=True) as conn:
        rec.set_meta(conn, "archived_at", rec.clock())
    broken = data_dir / "projects" / ("b" * 32)
    broken.mkdir(parents=True)
    (broken / "records.db").write_bytes(b"not a records file")

    answer = shown(client)
    assert answer["tenders"] == []  # archived: never on Home
    assert [u["project_id"] for u in answer["unreadable"]] == ["b" * 32]
    assert client.get(f"/projects/{pid}/tender", headers=AUTH).json()["tender"]["state"] == (
        "archived"
    )
    refused = client.get(f"/projects/{'b' * 32}/tender", headers=AUTH)
    assert refused.status_code in (409, 503) and set(refused.json()["error"]) == {"en", "ar"}
    gone = client.get(f"/projects/{'c' * 32}/tender", headers=AUTH)
    assert (gone.status_code, gone.json()["error"]) == (404, copy.PROJECT_NOT_FOUND)


def test_the_last_opened_tender_and_the_lead_block(client, monkeypatch):
    pid = new(client, "مفتوح - عينة")
    client.post(f"/projects/{pid}/open", headers=AUTH)
    answer = shown(client)
    assert answer["last_project_id"] == pid
    assert answer["blocked"] is None and answer["tenders"][0]["blocked"] is None

    no_ai = TestClient(create_app(SECRET, connectors=lambda: []))
    assert shown(no_ai)["blocked"] == {"reason": copy.NO_AI, "fix": "ai"}
    from qsone.journey import setup_state

    monkeypatch.setattr(setup_state, "consent", lambda: None)
    assert shown(no_ai)["blocked"] == {"reason": copy.AI_CONSENT_NEEDED, "fix": "consent"}


def brief(state: str, *, waiting: dict | None = None, step=None, reading: bool = False):
    return SimpleNamespace(
        brief_id="d" * 32,
        state=state,
        step=step or {"en": "reading file 1 of 2", "ar": "بيقرا ملف 1 من 2"},
        waiting=waiting or {},
        mapping_files=["f"] if reading else None,
        instruction=None,
    )


@pytest.mark.parametrize(
    ("briefs", "snap", "items", "expected"),
    [
        (
            [brief("waiting_engineer")],
            {},
            [{"blocking": True, "title": copy.WAITING_PLAN}],
            "waiting",
        ),
        ([], {}, [{"blocking": True, "title": copy.WAITING_PLAN}], "waiting"),
        ([brief("paused_cap")], {}, [], "paused"),
        ([brief("waiting_connection")], {}, [], "offline"),
        ([brief("running", reading=True)], {}, [], "reading"),
        ([], {"files_reading": True}, [], "reading"),
        ([brief("running")], {"plan": {"finished": False}}, [], "working"),
        ([], {"plan": {"finished": True}}, [], "finished"),
        ([], {"last": {"status": "failed", "step": copy.CORE_FAILED}}, [], "failed"),
        ([], {"last": {"status": "stopped", "step": None}}, [], "stopped"),
        ([], {}, [], "no_plan"),
        ([], {"plan": {"finished": False}}, [{"blocking": False, "title": {}}], "working"),
    ],
)
def test_the_state_is_the_first_rule_that_holds(briefs, snap, items, expected):
    snap = {"plan": None, "last": None, "files_reading": False} | snap
    assert home._state({}, snap, briefs, items)[0] == expected
    assert home._state({"archived_at": "x"}, snap, briefs, items)[0] == "archived"


def test_the_summary_never_disagrees_with_the_lists(client):
    one = new(client, "فيلا - عينة", due="2026-12-01")
    secret = new(client, "سري - عينة", confidential=True)
    engine = client.app.state.engine
    answer = shown(client)
    rows, waiting = answer["tenders"], answer["waiting"]
    assert [r["confidential"] for r in rows if r["project_id"] == secret] == [True]
    engineer = engine.engineer_records()
    assert not home_summary.save(engineer, "سري - عينة ينتظر", rows, waiting, actor="lead")
    assert shown(client)["summary"] is None  # nothing was kept
    assert home_summary.save(engineer, "فيلا واحدة - عينة", rows, waiting, actor="lead")
    summary = shown(client)["summary"]
    assert (summary["text"], summary["covers"]) == ("فيلا واحدة - عينة", 1)

    rec = client.app.state.projects.get(one)
    understand.correct(rec, {"submission_date": "2026-12-05"}, approve=False)
    assert shown(client)["summary"] is None  # the date it spoke of moved
    rows, waiting = shown(client)["tenders"], shown(client)["waiting"]
    assert home_summary.save(engineer, "فيلا واحدة - عينة", rows, waiting, actor="lead")
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    assert shown(client)["summary"] is None  # a covered tender became Confidential
    kept = json.loads(engineer.meta()[home_summary.META])
    assert secret not in kept["covers"]


def test_home_and_tender_events_come_at_most_once_a_second():
    async def run() -> list[dict]:
        seen: list[dict] = []
        made = []
        pulse = home_pulse.Pulse(
            lambda pid: made.append(pid) or {"tender": {}, "waiting": []}, gap_s=0.2
        )
        pulse.start(asyncio.get_running_loop())
        pid = "e" * 32

        async def listen(channel):
            async for event in activity.subscribe(channel):
                seen.append(event)

        tasks = [asyncio.create_task(listen(c)) for c in ("general", pid)]
        await asyncio.sleep(0)
        for _ in range(5):
            activity.publish(pid, {"type": "agent", "id": "x"})
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.5)
        pulse.stop()
        for task in tasks:
            task.cancel()
        assert len(made) == 2  # one at once, one at the end of the second for the last state
        return seen

    seen = asyncio.run(run())
    kinds = [e["type"] for e in seen if e["type"] in ("home", "tender")]
    assert kinds.count("home") == 2 and kinds.count("tender") == 2
