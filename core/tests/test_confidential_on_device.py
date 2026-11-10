"""A Confidential Project with "On this computer only" on (contract section 1, `LeadBlock`):
its Lead and team run only on a model on this computer, and with none connected the tender is
blocked and no Brief runs. Also the refused key in `LeadBlock`, and the AI changes the plan
driver hears of. Scripted models behind fake links only; no real AI. Synthetic «عينة» data only."""

# ruff: noqa: F811 (the engine fixtures, imported)

import asyncio
from dataclasses import replace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from qsone import copy, settings
from qsone.app import create_app
from qsone.engine.connectors import key_refused
from qsone.engine.runner import NoAI
from qsone.engine.types import ModelChoice
from qsone.settings_registry import ON_DEVICE
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import DEEPSEEK, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    FakeLink,
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)

LOCAL = replace(DEEPSEEK, choice=ModelChoice("standard:local", "local-sample"), on_device=True)


def confidential(found, project_id: str) -> None:
    rec = found.get(project_id)
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")


def local_link(model=None) -> FakeLink:
    found = FakeLink("standard:local", "Local", "deepseek", sheet=[LOCAL], on_device=True)
    if model is not None:
        found.models[LOCAL.choice.model] = model
    return found


async def test_a_confidential_lead_runs_only_on_the_model_on_this_computer(
    make_engine, registry, project
):
    settings.save(ON_DEVICE, True)
    confidential(registry, project)
    cloud, local = scripted(said("سحابة - عينة")), scripted(said("محلي - عينة"))
    engine = await started(make_engine([*links(lead=cloud), local_link(local)]))
    await finish(engine, await engine.start_brief(project, "اقرا المقايسة - عينة"))
    assert (cloud.calls, local.calls) == (0, 1)


async def test_with_the_setting_off_the_confidential_lead_keeps_its_model(
    make_engine, registry, project
):
    confidential(registry, project)
    cloud = scripted(said("سحابة - عينة"))
    engine = await started(make_engine([*links(lead=cloud), local_link()]))
    await finish(engine, await engine.start_brief(project, "اقرا المقايسة - عينة"))
    assert cloud.calls == 1


async def test_with_no_model_on_this_computer_no_confidential_brief_starts(
    make_engine, registry, project
):
    settings.save(ON_DEVICE, True)
    confidential(registry, project)
    cloud = scripted(said("سحابة - عينة"))
    engine = await started(make_engine(links(lead=cloud)))
    with pytest.raises(NoAI) as refused:
        await engine.start_brief(project, "اقرا المقايسة - عينة")
    assert refused.value.text == copy.CONFIDENTIAL_NO_LOCAL_AI and cloud.calls == 0
    other = registry.create("مكشوف - عينة", "engineer")["id"]  # not Confidential: it runs
    await finish(engine, await engine.start_brief(other, "اقرا المقايسة - عينة"))
    assert cloud.calls == 1


# The tender's row --------------------------------------------------------------------------


def new(client, name: str, *, secret: bool = False) -> str:
    pid = client.post("/projects", json={"name": name}, headers=AUTH).json()["id"]
    if secret:
        confidential(client.app.state.projects, pid)
    return pid


def rows(client) -> dict:
    tenders = client.get("/home", headers=AUTH).json()["tenders"]
    return {r["project_id"]: r["blocked"] for r in tenders}


def test_a_confidential_tender_with_no_model_here_is_blocked(data_dir):
    client = TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))
    secret, other = new(client, "سري - عينة", secret=True), new(client, "مكشوف - عينة")
    block = {"reason": copy.CONFIDENTIAL_NO_LOCAL_AI, "fix": "ai"}
    assert rows(client) == {secret: None, other: None}  # the setting is off
    settings.save(ON_DEVICE, True)
    assert rows(client) == {secret: block, other: None}
    tender = client.get(f"/projects/{secret}/tender", headers=AUTH).json()["tender"]
    assert tender["blocked"] == block
    assert client.get("/home", headers=AUTH).json()["blocked"] is None  # Home's Lead can work

    here = TestClient(create_app(SECRET, connectors=lambda: [*links(), local_link()]))
    assert rows(here) == {secret: None, other: None}


# A refused key -----------------------------------------------------------------------------


class Refusing(FakeLink):
    async def cards(self):
        request = httpx.Request("GET", "https://api.anthropic.com/v1/models")
        raise anthropic.AuthenticationError(
            "refused", response=httpx.Response(401, request=request), body=None
        )


def test_a_key_refused_at_the_last_listing_blocks_the_lead(data_dir):
    found = [Refusing("anthropic", "Claude", "anthropic")]
    client = TestClient(create_app(SECRET, data_dir=data_dir, connectors=lambda: found))
    pid = new(client, "مشروع - عينة")
    assert client.get("/home", headers=AUTH).json()["blocked"] is None  # nothing listed yet
    with pytest.raises(NoAI):  # the listing finds the key refused
        asyncio.run(client.app.state.engine.sheet())
    block = {"reason": key_refused("Claude"), "fix": "ai"}
    assert client.get("/home", headers=AUTH).json()["blocked"] == block
    assert rows(client) == {pid: block}
    assert client.put("/settings/model", json={"id": "claude-opus-5-5"}, headers=AUTH).is_success
    assert client.get("/home", headers=AUTH).json()["blocked"] is None  # an AI change: unknown


# The plan driver hears of every AI change --------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [("/settings/model", {"id": "claude-opus-5-5"}), ("/setup/ai", {"state": "done"})],
)
def test_choosing_the_model_or_finishing_the_ai_step_tells_the_driver(data_dir, path, body):
    client = TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))
    heard: list[int] = []
    client.app.state.driver.on_ai_changed = lambda: heard.append(1)
    assert client.put(path, json=body, headers=AUTH).is_success
    assert heard == [1]


# Routes that start the Lead's work refuse as the row says ----------------------------------


def test_the_room_refuses_a_blocked_confidential_tender_and_stores_nothing(data_dir):
    client = TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))
    pid = new(client, "سري - عينة", secret=True)
    settings.save(ON_DEVICE, True)
    said = client.post(f"/projects/{pid}/room", json={"text": "سؤال - عينة"}, headers=AUTH)
    row = rows(client)[pid]
    assert said.status_code == 409 and said.json() == {"error": row["reason"], "fix": row["fix"]}
    assert row == {"reason": copy.CONFIDENTIAL_NO_LOCAL_AI, "fix": "ai"}
    room = client.get(f"/projects/{pid}/room", headers=AUTH).json()["messages"]
    assert [m for m in room if m["from_id"] == "engineer"] == []


def test_deciding_a_finding_in_a_blocked_confidential_tender_is_refused(data_dir):
    from tests.fakes_tools import tool_ctx
    from tests.test_findings import raise_, record, spec_file

    client = TestClient(create_app(SECRET, data_dir=data_dir, connectors=links))
    pid = new(client, "سري - عينة", secret=True)
    rec = client.app.state.projects.get(pid)
    ctx = tool_ctx(rec)
    first = record(ctx, spec_file(rec))
    raise_(ctx, first)
    settings.save(ON_DEVICE, True)
    path = f"/projects/{pid}/findings/{first}/decide"
    refused = client.post(path, json={"choice": 0}, headers=AUTH)
    assert refused.status_code == 409
    assert refused.json() == {"error": copy.CONFIDENTIAL_NO_LOCAL_AI, "fix": "ai"}
    found = client.get(f"/projects/{pid}/findings", headers=AUTH).json()["findings"]
    assert found[0]["status"] == "raised"  # nothing stored
