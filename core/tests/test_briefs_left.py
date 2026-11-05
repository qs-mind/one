"""What the chat shows of a Brief once nothing waits on its cards: an unfinished Brief's card is
withdrawn until Continue asks it again, «Leave it» ends the Brief for good, and a stored card
keeps its place in time next to the Lead's words. And a project's Brief that waits on a card
goes on after the engineer moves to another project (B1).

Scripted models only, behind fake connectors; no test calls a real AI. Synthetic «عينة» data
only."""

# ruff: noqa: F811 (the engine fixtures, imported)

from fastapi.testclient import TestClient

from qsone import copy
from qsone.engine.types import answer_value
from tests.conftest import AUTH
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.team_samples import BRIEF
from tests.test_engine_routes import app_with
from tests.test_engine_runner import (  # noqa: F401
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    states,
    store_of,
    until,
)

QUESTION = {
    "questions": [{"id": "q1", "text": "الخرسانة جاهزة؟ - عينة", "options": ["أيوه", "لأ"]}]
}


def reply_parts(engine, chat_id: str) -> list[dict]:
    return engine.chat_messages(chat_id)[-1]["parts"]


def card_parts(parts: list[dict]) -> list[dict]:
    return [p for p in parts if p["type"] == "data-card"]


async def crashed_while_asking(make_engine, project):
    """A Brief whose question card waited when the core went down, and a new core."""
    e1 = await started(make_engine(links(lead=scripted(call("ask_engineer", QUESTION)))))
    brief = await e1.start_brief(project, BRIEF)
    await until(lambda: store_of(e1, project).pending(brief))
    await e1.crash()
    e2 = await started(make_engine(links(lead=scripted(said("عينة")))))
    return e2, brief


async def test_an_unfinished_briefs_card_shows_withdrawn(make_engine, project):
    engine, brief = await crashed_while_asking(make_engine, project)
    [card] = card_parts(reply_parts(engine, project))
    assert card["data"]["status"] == "withdrawn"  # no live buttons that answer 404
    assert [b["id"] for b in engine.unfinished()] == [brief]  # Continue is still offered


async def test_leave_ends_the_brief_and_it_is_never_offered_again(make_engine, project):
    engine, brief = await crashed_while_asking(make_engine, project)
    engine.leave_brief(brief)
    assert engine.unfinished() == []
    stored = store_of(engine, project).brief(brief)
    assert stored["status"] == "stopped" and stored["step"] == copy.STOPPED
    assert store_of(engine, project).pending(brief) == []
    parts = reply_parts(engine, project)
    assert card_parts(parts)[0]["data"]["status"] == "withdrawn"
    assert [p["data"]["state"] for p in parts if p["type"] == "data-status"] == ["stopped"]
    try:
        engine.leave_brief(brief)
    except LookupError:
        pass
    else:
        raise AssertionError("a Brief left once is not unfinished any more")


def test_the_leave_route():
    with TestClient(app_with(links(lead=scripted()))) as client:
        assert client.post("/briefs/b1/leave").status_code == 401
        r = client.post("/briefs/nope/leave", headers=AUTH)
        assert r.status_code == 404 and r.json() == {"error": copy.BRIEF_NOT_FOUND}


async def test_a_card_asked_before_the_lead_spoke_comes_before_its_words(make_engine, project):
    lead = scripted(call("ask_engineer", QUESTION), said("الخرسانة جاهزة - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    store = store_of(engine, project)
    await until(lambda: store.pending(brief))
    [card] = store.pending(brief)
    await engine.answer(card.id, answer_value(card, "sent", answers={"q1": "أيوه"}))
    await finish(engine, brief)
    kinds = [p["type"] for p in reply_parts(engine, project) if p["type"] in ("text", "data-card")]
    assert kinds == ["data-card", "text"]


async def test_a_waiting_brief_goes_on_after_the_engineer_moves_on(make_engine, registry, project):
    lead = scripted(call("ask_engineer", QUESTION), said("تم - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    store = store_of(engine, project)
    await until(lambda: store.pending(brief))
    assert engine.keep_open(project) is True  # the screen switched to another project
    assert registry.get(project).is_open
    [card] = store.pending(brief)
    await engine.answer(card.id, answer_value(card, "sent", answers={"q1": "أيوه"}))
    events = await finish(engine, brief)
    assert states(events)[-1] == "done"  # never «افتح المشروع الأول»
    await until(lambda: project not in dict(registry.opened()))
