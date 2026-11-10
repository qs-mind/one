"""The plan driver in the real app: approving the plan through route 9 starts stage 1, the
lifespan starts the driver and resumes at start-up, and a change in the AI settings lets a stage
that waited for an AI go on. Scripted models only, never a real AI. Synthetic «عينة» data only."""

import time

from fastapi.testclient import TestClient

from qsone.app import create_app
from qsone.engine.plan import driver as plan_driver
from qsone.engine.plan import store
from qsone.journey import setup_state
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import MAP
from tests.test_engine_runner import no_budget_card  # noqa: F401 - fixture
from tests.test_tender_plan import draft, due_in, pair, stage
from tests.test_tender_plan_routes import link


def _tender(client, app, name: str) -> str:
    """A tender with a proposed plan of two stages; its id."""
    pid = client.post("/projects", json={"name": name}, headers=AUTH).json()["id"]
    rec = app.state.projects.get(pid)
    due_in(rec)
    stages = [stage(rec, i, title=pair(f"Stage {i + 1}"), outputs=MAP) for i in range(2)]
    store.propose(rec, draft(rec, stages=stages, team=[]))
    return pid


def _approve(client, pid: str) -> None:
    done = client.post(f"/projects/{pid}/plan/approve", json={"version": 1}, headers=AUTH)
    assert done.status_code == 200, done.text


def _first(app, pid: str) -> str:
    """Stage 1's status, read without opening the tender (opening it would start its work)."""
    projects = app.state.projects
    opened = dict(projects.opened())
    rec = opened.get(pid) or projects.open_file(pid)
    try:
        return store.current(rec).stages[0].status
    finally:
        if pid not in opened:
            rec.close()


def _waits_for(app, pid: str, status: str) -> None:
    for _ in range(600):
        if _first(app, pid) == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"stage 1 is {_first(app, pid)}, not {status}")


def _approved_with_no_ai(app, pid: str) -> None:
    """Approved while no AI is linked (route 9 asks the AI for the figures, so the records)."""
    store.approve(app.state.projects.get(pid))
    plan_driver.on_plan_approved(pid)


def test_approving_the_plan_starts_stage_1(data_dir):
    lead = scripted(said("تمام - عينة"))
    app = create_app(SECRET, connectors=lambda: [link(lead=lead)])
    with TestClient(app) as client:
        pid = _tender(client, app, "مناقصة - عينة")
        _approve(client, pid)  # stage 1 starts with no message from the engineer
        _waits_for(app, pid, "waiting_engineer")
        assert lead.calls == 1


def test_a_stage_that_waited_for_an_ai_goes_on_when_the_ai_settings_change(data_dir):
    links: list = []  # no AI linked
    app = create_app(SECRET, connectors=lambda: links)
    with TestClient(app) as client:
        pid = _tender(client, app, "بلا ذكاء - عينة")
        _approved_with_no_ai(app, pid)
        time.sleep(0.2)
        assert _first(app, pid) == "pending"  # nothing used up: it waits for an AI
        links.append(link(lead=scripted(said("تمام - عينة"))))
        given = client.put(
            "/settings/ai-consent", json={"text_version": setup_state.CONSENT_VERSION}, headers=AUTH
        )
        assert given.status_code == 200  # a change in the AI settings
        _waits_for(app, pid, "waiting_engineer")


def test_the_app_resumes_tenders_at_start(data_dir):
    links: list = []
    first = create_app(SECRET, connectors=lambda: links, data_dir=data_dir)
    with TestClient(first) as client:
        pids = [_tender(client, first, f"مناقصة {n} - عينة") for n in (1, 2)]
        for pid in pids:
            _approved_with_no_ai(first, pid)
        time.sleep(0.2)
        assert [_first(first, pid) for pid in pids] == ["pending", "pending"]
    links.append(link(lead=scripted(said("تمام أ - عينة"), said("تمام ب - عينة"))))
    again = create_app(SECRET, connectors=lambda: links, data_dir=data_dir)
    with TestClient(again):  # ONE starts again: both go on by themselves
        for pid in pids:
            _waits_for(again, pid, "waiting_engineer")
