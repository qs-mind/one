"""What every chat's Briefs are doing, for the screen outside that chat: the top bar's mark, the
projects' rows and the notice (GET /briefs/activity, POST /chat/{id}/seen). And a project's file
stays open while a Brief runs in it, so moving to another project never cuts the Brief short.

Scripted models only, behind fake connectors; no test calls a real AI. Synthetic «عينة» data only."""

import asyncio
import threading

from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAuthenticationError

from qsone.engine import costs
from qsone.engine.runner import GENERAL
from tests.conftest import AUTH
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.team_samples import BRIEF
from tests.test_engine_routes import Waits, app_with, message
from tests.test_engine_runner import (  # noqa: F401 (fixtures)
    PLAN,
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    store_of,
    until,
)


def refused(messages, info):
    raise ModelAuthenticationError("sample-model", "invalid x-api-key")


def by_chat(engine) -> dict[str, dict]:
    return {c["chat_id"]: c for c in engine.chats()}


async def test_every_chat_says_working_waiting_failed_or_done(make_engine, registry, project):
    go = asyncio.Event()

    async def works(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "تم - عينة"

    done_in = registry.create("خلص - عينة", "engineer")["id"]
    failed_in = registry.create("اتعطل - عينة", "engineer")["id"]
    lead = scripted(said("تم - عينة"), refused, works, call("plan_brief", PLAN))
    engine = await started(make_engine(links(lead=lead)))
    assert engine.chats() == []  # nothing runs, nothing ended unseen

    await finish(engine, await engine.start_brief(done_in, BRIEF))
    await finish(engine, await engine.start_brief(failed_in, BRIEF))
    working = await engine.start_brief(project, BRIEF)
    await until(lambda: lead.calls == 3)
    costs.save_caps({"budget_above": "0"})  # the General chat's Brief asks about its budget
    waiting = await engine.start_brief(GENERAL, BRIEF)
    general = store_of(engine, GENERAL)
    await until(lambda: general.pending(waiting))

    chats = by_chat(engine)
    assert {k: c["state"] for k, c in chats.items()} == {
        done_in: "done",
        failed_in: "failed",
        project: "working",
        GENERAL: "waiting",
    }
    assert chats[project]["brief_id"] == working and chats[GENERAL]["brief_id"] == waiting
    assert chats[done_in]["name"] == "خلص - عينة" and chats[GENERAL]["name"] is None

    # seen: an ended Brief's mark clears once the engineer opens its chat; a running one stays
    engine.seen(done_in)
    engine.seen(failed_in)
    engine.seen(project)
    assert set(by_chat(engine)) == {project, GENERAL}

    go.set()
    await engine.stop(waiting)
    await engine.result(working)
    assert by_chat(engine) == {
        project: {"chat_id": project, "brief_id": working, "state": "done", "name": "مشروع - عينة"}
    }  # stopped by the engineer: no mark


async def test_a_new_brief_replaces_its_chats_ended_mark(make_engine, project):
    go = asyncio.Event()

    async def works(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "تم - عينة"

    engine = await started(make_engine(links(lead=scripted(refused, works))))
    await finish(engine, await engine.start_brief(project, BRIEF))
    assert by_chat(engine)[project]["state"] == "failed"
    again = await engine.start_brief(project, BRIEF)
    assert by_chat(engine)[project]["state"] == "working"
    go.set()
    await finish(engine, again)
    assert by_chat(engine)[project]["state"] == "done"


async def test_a_projects_file_stays_open_while_its_brief_runs(make_engine, registry, project):
    go = asyncio.Event()

    async def works(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "تم - عينة"

    engine = await started(make_engine(links(lead=scripted(works, said("تاني - عينة")))))
    brief = await engine.start_brief(project, BRIEF)
    assert engine.keep_open(project) is True  # the engineer moved to another project
    assert registry.get(project).is_open
    go.set()
    await finish(engine, brief)
    assert by_chat(engine)[project]["state"] == "done"  # not cut short
    await until(lambda: project not in dict(registry.opened()))  # closed once the Brief ended

    # opened again before its Brief ends: it stays open after
    registry.open(project)
    brief = await engine.start_brief(project, BRIEF)
    assert engine.keep_open(project) is True
    engine.opened(project)
    await finish(engine, brief)
    await asyncio.sleep(0.05)
    assert registry.get(project).is_open
    assert engine.keep_open(project) is False  # nothing runs: the screen closes it now


def test_the_routes_list_chats_and_mark_one_seen():
    with TestClient(app_with(links(lead=scripted(said("تم - عينة"))))) as client:
        assert client.get("/briefs/activity", headers=AUTH).json() == {"chats": []}
        made = client.post("/projects", json={"name": "مشروع - عينة"}, headers=AUTH).json()
        brief = client.post("/chat", json=message("سعّر - عينة", made["id"]), headers=AUTH)
        assert brief.status_code == 200
        chats = client.get("/briefs/activity", headers=AUTH).json()["chats"]
        assert [(c["chat_id"], c["state"]) for c in chats] == [(made["id"], "done")]
        assert client.post(f"/chat/{made['id']}/seen", headers=AUTH).status_code == 204
        assert client.get("/briefs/activity", headers=AUTH).json() == {"chats": []}


def test_closing_a_project_keeps_it_open_while_its_brief_runs():
    waits = Waits()
    with TestClient(app_with(links(lead=scripted(waits)))) as client:
        made = client.post("/projects", json={"name": "مشروع - عينة"}, headers=AUTH).json()
        app = client.app
        engine = app.state.engine

        def start():
            return client.post("/chat", json=message("سعّر - عينة", made["id"]), headers=AUTH)

        answer: list = []
        worker = threading.Thread(target=lambda: answer.append(start()))
        worker.start()
        for _ in range(500):
            if engine.active(made["id"]):
                break
            threading.Event().wait(0.01)
        closed = client.post(f"/projects/{made['id']}/close", headers=AUTH)
        assert closed.json() == {"open": True}
        assert app.state.projects.get(made["id"]).is_open
        waits.release.set()
        worker.join(10)
        assert answer[0].status_code == 200
        chats = client.get("/briefs/activity", headers=AUTH).json()["chats"]
        assert [c["state"] for c in chats] == ["done"]
        for _ in range(500):
            if made["id"] not in dict(app.state.projects.opened()):
                break
            threading.Event().wait(0.01)
        assert made["id"] not in dict(app.state.projects.opened())

