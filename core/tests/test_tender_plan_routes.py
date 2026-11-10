"""The tender plan's routes (contract rows 8-12) on the real app, and a plan written by a
scripted Lead end to end. Scripted models only, never a real AI. Synthetic «عينة» data only."""

import time
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.deliverables import events
from qsone.deliverables.store import status
from qsone.engine.plan import routes, store
from qsone.engine.runner import Engine
from qsone.journey import understand
from qsone.projects import Projects
from qsone.records import schema
from qsone.records.project import Records
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import call as step
from tests.engine_fakes import scripted, text
from tests.samples import sample_sheet
from tests.test_engine_runner import FakeLink
from tests.test_review import check
from tests.test_tender_plan import CARD, draft, due_in, pair, plan_args, stage

UNKNOWN = "5a" + "0" * 30


def link(card=CARD, lead=None) -> FakeLink:
    found = FakeLink("anthropic", "Claude", "anthropic", sheet=[card])
    found.models[card.choice.model] = lead or scripted(lambda messages, info: text("عينة"))
    return found


@pytest.fixture
def links() -> list:
    return [link()]


@pytest.fixture
def app(links):
    return create_app(SECRET, connectors=lambda: links)


@pytest.fixture
def client(app):
    with TestClient(app) as found:
        yield found


@pytest.fixture
def pid(client) -> str:
    return client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]


@pytest.fixture
def rec(app, pid) -> Records:
    return app.state.projects.get(pid)


def post(client, path: str, body: dict | None = None):
    return client.post(path, json=body, headers=AUTH)


def refusal(answer, status: int, text: dict, **more) -> None:
    assert answer.status_code == status, answer.text
    got = c.Refusal.model_validate_json(answer.text, strict=True)
    assert got.error.model_dump() == text
    for key, value in more.items():
        assert getattr(got, key) == value


def ended(app, pid: str) -> None:
    """Waits until no work runs in the tender (the app's own loop runs it)."""
    for _ in range(500):
        if app.state.engine.active(pid) is None:
            return
        time.sleep(0.01)
    raise AssertionError("the work did not end")


def test_plan_absent_for_old_project(client, app, data_dir):
    """A project made before plans existed: its file is brought up to date and has no plan."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:-1])
        old = client.post("/projects", json={"name": "قديم - عينة"}, headers=AUTH).json()["id"]
        client.post(f"/projects/{old}/close", headers=AUTH)
    assert client.post(f"/projects/{old}/open", headers=AUTH).status_code == 200
    got = client.get(f"/projects/{old}/plan", headers=AUTH)
    assert (got.status_code, got.json()) == (200, {"plan": None})
    assert got.headers["cache-control"] == "no-store"
    refusal(client.get(f"/projects/{UNKNOWN}/plan", headers=AUTH), 404, copy.PROJECT_NOT_FOUND)


def test_approving_the_plan(client, pid, rec, links):
    path = f"/projects/{pid}/plan/approve"
    refusal(post(client, path, {"version": 1}), 404, copy.PLAN_NOT_FOUND)
    due_in(rec)
    plan = store.propose(rec, draft(rec))
    shown = client.get(f"/projects/{pid}/plan", headers=AUTH).json()
    assert shown == {"plan": plan.model_dump(mode="json")}
    refusal(post(client, path, {"version": 2}), 409, copy.PLAN_CHANGED, field="version")
    done = post(client, path, {"version": 1})
    assert done.status_code == 200
    approved = c.PlanView.model_validate_json(done.text, strict=True).plan
    assert (approved.status, approved.version, approved.approved_at is not None) == (
        "approved",
        1,
        True,
    )
    assert post(client, path, {"version": 1}).json() == done.json()  # a retry: the same plan


def test_the_figures_are_worked_out_again_at_approval(client, pid, rec, links):
    due_in(rec)
    store.propose(rec, draft(rec))
    links[:] = [link(replace(CARD, price_in=Decimal("30"), price_out=Decimal("150")))]
    path = f"/projects/{pid}/plan/approve"
    refusal(post(client, path, {"version": 1}), 409, copy.PLAN_CHANGED, field="version")
    again = store.current(rec)  # stored, with the figures of now, for the engineer to see
    assert (again.version, again.status) == (2, "proposed")
    assert Decimal(again.expected_cost_usd) == 2 * Decimal(draft(rec).estimate.usd)
    assert post(client, path, {"version": 2}).json()["plan"]["status"] == "approved"


def test_approval_is_refused_while_work_runs_without_ai_or_a_date(client, app, pid, rec, links):
    due_in(rec)
    store.propose(rec, draft(rec))
    path = f"/projects/{pid}/plan/approve"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(app.state.engine, "active", lambda project_id, **_: UNKNOWN)
        refusal(post(client, path, {"version": 1}), 409, copy.WORK_RUNNING, brief_id=UNKNOWN)
    links.clear()
    refusal(post(client, path, {"version": 1}), 409, copy.NO_AI, fix="ai")
    links.append(link())
    understand.correct(rec, {"submission_date": "2026-01-01"}, approve=False)
    answer = post(client, path, {"version": 1})
    refusal(answer, 409, copy.PLAN_NEEDS_SUBMISSION_DATE, field="submission_date")
    assert store.current(rec).status == "proposed"


def test_asking_for_a_plan(client, app, pid, rec, links):
    path = f"/projects/{pid}/plan/request"
    links.clear()
    refusal(post(client, path), 409, copy.NO_AI, fix="ai")
    links.append(link())
    started = post(client, path)
    assert started.status_code == 202
    brief_id = c.BriefStarted.model_validate_json(started.text, strict=True).brief_id
    refusal(post(client, path), 409, copy.WORK_RUNNING, brief_id=brief_id)
    ended(app, pid)
    due_in(rec)
    store.propose(rec, draft(rec))
    refusal(post(client, path), 409, copy.PLAN_EXISTS)


def test_signing_off_a_stage(client, pid, rec):
    due_in(rec)
    summary = {"kind": "summary", "title": pair("Tender summary")}
    priced = {"kind": "deliverable", "title": pair("Priced BOQ")}
    plan = store.propose(rec, draft(rec, stages=[stage(rec, 0, outputs=[summary, priced])]))
    store.approve(rec, version=1)
    first = plan.stages[0].id
    path = f"/projects/{pid}/plan/stages/{first}/approve"
    refusal(post(client, path, {"version": 1}), 409, copy.STAGE_NOT_WAITING)
    unknown = f"/projects/{pid}/plan/stages/{UNKNOWN}/approve"
    refusal(post(client, unknown, {"version": 1}), 404, copy.STAGE_NOT_FOUND)
    store.set_stage_status(rec, first, "waiting_engineer")
    not_made = copy.fill(
        copy.STAGE_OUTPUT_NOT_READY, output=priced["title"], reason=copy.STAGE_OUTPUT_MISSING
    )
    refusal(post(client, path, {"version": 1}), 409, not_made, field="outputs")
    sheet = sample_sheet(rec)
    store.set_stage_status(rec, first, "waiting_engineer", output_ids=[None, sheet])
    seen = []
    stop = events.listen(lambda project, event: seen.append(event["type"]))
    try:
        unchecked = copy.fill(
            copy.STAGE_OUTPUT_NOT_READY, output=priced["title"], reason=copy.SIGNOFF_NEEDS_CHECK
        )
        refusal(post(client, path, {"version": 1}), 409, unchecked, field="outputs")
        assert seen == []  # refused: nothing changed, nothing published
        check(rec, sheet)
        seen.clear()
        done = post(client, path, {"version": 1})
    finally:
        stop()
    assert done.status_code == 200 and done.json()["plan"]["stages"][0]["status"] == "approved"
    assert status(rec, sheet)["status"] == "signed_off"
    assert understand.facts(rec)["approved"] is True
    assert seen == ["deliverable", "plan"]  # after the one write committed
    assert post(client, path, {"version": 1}).json() == done.json()  # a retry: nothing more


def test_answering_a_suggested_change(client, pid, rec):
    due_in(rec)
    plan = store.propose(rec, draft(rec))
    store.approve(rec, version=1)
    later = [stage(rec, 0, id=plan.stages[0].id), stage(rec, 3, id=plan.stages[1].id)]
    change = store.suggest(rec, draft(rec, stages=later), "ملحق - عينة").change
    path = f"/projects/{pid}/plan/change"
    wrong = post(client, path, {"change_id": UNKNOWN, "accept": True})
    refusal(wrong, 409, copy.PLAN_CHANGED, field="change_id")
    accepted = post(client, path, {"change_id": change.id, "accept": True})
    assert accepted.status_code == 200
    got = accepted.json()["plan"]
    assert (got["version"], got["change"], got["stages"][1]["ends"]) == (2, None, later[1]["ends"])
    assert post(client, path, {"change_id": change.id, "accept": True}).json() == accepted.json()
    # A change whose date is no longer the tender's cannot be accepted, and can be rejected.
    again = store.suggest(rec, draft(rec, stages=later), "عينة").change
    understand.correct(rec, {"submission_date": plan_args(rec)["stages"][1]["ends"]}, approve=False)
    late = post(client, path, {"change_id": again.id, "accept": True})
    refusal(late, 409, copy.PLAN_NEEDS_SUBMISSION_DATE, field="submission_date")
    rejected = post(client, path, {"change_id": again.id, "accept": False}).json()["plan"]
    assert (rejected["version"], rejected["change"]) == (2, None)


async def test_a_scripted_lead_writes_the_plan(data_dir, fake_sleep, fake_clock):
    projects = Projects(data_dir)
    pid = projects.create("مناقصة - عينة", "engineer")["id"]
    rec = projects.get(pid)
    lead = scripted(
        step("tender_plan_write", plan_args(rec, stages=[stage(rec, 0, owner="pricing-qs")])),
        text("دي الخطة - عينة"),
    )
    due_in(rec)
    engine = Engine(
        projects=projects,
        data_dir=data_dir,
        connectors=lambda: [link(lead=lead)],
        clock=fake_clock,
        sleep=fake_sleep,
    )
    await engine.start()
    try:
        brief = await engine.start_brief(pid, "اكتب الخطة - عينة", instruction=routes.INSTRUCTION)
        await engine.result(brief)
        plan = store.current(rec)
        assert plan is not None and plan.status == "proposed" and plan.expected_cost_usd
        parts = [p for p in engine.chat_messages(pid)[-1]["parts"] if p["type"] == "data-plan"]
        assert parts == [
            {"type": "data-plan", "id": plan.id, "data": {"plan_id": plan.id, "version": 1}}
        ]
    finally:
        await engine.shutdown()
        projects.close_all()
