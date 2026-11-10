"""Answering a Suggested change (route 12) in the real app: an accepted change moves the plan on
(a stage it adds starts), accepting needs an AI to work its figures out again, and the Lead is
told the answer in one line, by a steer to its running work or in the next work's instruction.
Scripted models only, never a real AI. Synthetic «عينة» data only."""

import time

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.engine.plan import store
from qsone.journey import understand
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import scripted
from tests.plan_driver_kit import MAP, english  # noqa: F401 - the engineer writes English
from tests.test_tender_plan import draft, due_in, stage
from tests.test_tender_plan_routes import UNKNOWN, link, post, refusal


class Lead:
    """A scripted Lead that says one line per Brief and keeps each Brief's instructions."""

    def __init__(self) -> None:
        self.instructions: list[str] = []
        self.model = scripted(*([self._said] * 4))

    def _said(self, messages, info) -> str:
        self.instructions.append(info.instructions or "")
        return "تمام - عينة"


def waits(check, what: str) -> None:
    for _ in range(600):
        if check():
            return
        time.sleep(0.01)
    raise AssertionError(f"{what} did not happen")


@pytest.fixture
def lead() -> Lead:
    return Lead()


@pytest.fixture
def links(lead) -> list:
    return [link(lead=lead.model)]


@pytest.fixture
def app(links, data_dir):
    return create_app(SECRET, connectors=lambda: links)


@pytest.fixture
def client(app):
    with TestClient(app) as found:
        yield found


def signed_off_plan(client, app) -> tuple[str, object]:
    """A tender whose one stage ran and is signed off; (its id, its Records)."""
    pid = client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]
    rec = app.state.projects.get(pid)
    due_in(rec)
    store.propose(rec, draft(rec, stages=[stage(rec, 0, outputs=MAP)], team=[]))
    assert post(client, f"/projects/{pid}/plan/approve", {"version": 1}).status_code == 200
    waits(lambda: store.current(rec).stages[0].status == "waiting_engineer", "stage 1's end")
    first = store.current(rec).stages[0].id
    path = f"/projects/{pid}/plan/stages/{first}/approve"
    assert post(client, path, {"version": 1}).status_code == 200
    return pid, rec


def suggest_a_second_stage(rec):
    first = store.current(rec).stages[0]
    stages = [stage(rec, 0, id=first.id, outputs=MAP), stage(rec, 1, outputs=MAP)]
    return store.suggest(rec, draft(rec, stages=stages, team=[]), "ملحق - عينة").change


def test_an_accepted_change_starts_the_stage_it_adds_and_tells_the_lead(client, app, lead):
    pid, rec = signed_off_plan(client, app)
    change = suggest_a_second_stage(rec)
    answer = post(client, f"/projects/{pid}/plan/change", {"change_id": change.id, "accept": True})
    assert answer.status_code == 200, answer.text
    waits(lambda: store.current(rec).stages[1].status == "waiting_engineer", "stage 2's work")
    said = copy.fill(copy.PLAN_CHANGE_ACCEPTED_TOLD, version=2)["en"]
    assert len(lead.instructions) == 2 and said in lead.instructions[1]  # told once, in its kit
    assert said not in lead.instructions[0]


def test_a_change_is_not_accepted_without_an_ai_and_rejecting_needs_none(client, app, links):
    pid, rec = signed_off_plan(client, app)
    change = suggest_a_second_stage(rec)
    links.clear()
    path = f"/projects/{pid}/plan/change"
    refusal(post(client, path, {"change_id": change.id, "accept": True}), 409, copy.NO_AI, fix="ai")
    assert store.current(rec).change.id == change.id  # refused: it still waits
    rejected = post(client, path, {"change_id": change.id, "accept": False})
    assert (rejected.status_code, rejected.json()["plan"]["change"]) == (200, None)


def test_a_rejected_change_is_told_to_the_running_work(client, app, monkeypatch):
    pid, rec = signed_off_plan(client, app)
    change = suggest_a_second_stage(rec)
    engine, steered = app.state.engine, []

    async def steer(brief_id, text):
        steered.append((brief_id, text))

    monkeypatch.setattr(engine, "active", lambda project_id, **_: UNKNOWN)
    monkeypatch.setattr(engine, "steer", steer)
    path = f"/projects/{pid}/plan/change"
    assert post(client, path, {"change_id": change.id, "accept": False}).status_code == 200
    assert steered == [(UNKNOWN, copy.PLAN_CHANGE_REJECTED_TOLD["en"])]
    assert store.untold(rec) is None  # told: the next work is not told again
    assert post(client, path, {"change_id": change.id, "accept": False}).status_code == 200
    assert len(steered) == 1  # the same answer again tells nothing more


def test_the_understand_brief_keeps_its_own_instruction(client, app, lead):
    """The told line waits for ordinary work: the reading state and the card check know the
    'I understood this' Brief by its exact instruction."""
    pid, rec = signed_off_plan(client, app)
    change = suggest_a_second_stage(rec)
    assert (
        post(
            client, f"/projects/{pid}/plan/change", {"change_id": change.id, "accept": False}
        ).status_code
        == 200
    )
    started = client.post(f"/projects/{pid}/understand", headers=AUTH)
    assert started.status_code == 202, started.text
    brief = app.state.engine._briefs.get(started.json()["brief_id"])
    waits(lambda: len(lead.instructions) >= 2, "the understand Brief's Lead")
    assert brief.instruction == understand.INSTRUCTION
    assert copy.PLAN_CHANGE_REJECTED_TOLD["en"] not in lead.instructions[-1]
    assert store.untold(rec) is not None  # still owed: the next ordinary work is told
