"""The plan driver (Phase 1, C3): code moves an approved tender plan on, stage after stage, on the
real Brief runner and encrypted Records. Scripted models only, never a real AI or the network.
Synthetic «عينة» data only."""

import asyncio
import typing
from uuid import uuid4

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelRequest, UserPromptPart

from qsone.engine import agents, costs
from qsone.engine import types as engine_types
from qsone.engine.plan import driver as plan_driver
from qsone.engine.plan import store
from qsone.engine.runner import BriefBusy
from qsone.engine.tools import REGISTRY, Tool, register
from qsone.engine.types import Card, answer_value
from qsone.journey import setup_state
from qsone.projects import Projects
from tests.engine_fakes import OPUS, call, scripted
from tests.engine_fakes import text as said
from tests.plan_driver_kit import MAP, Tender, blocks, drivers, english, tender  # noqa: F401
from tests.test_engine_runner import (  # noqa: F401 - fixtures
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
    until,
)
from tests.test_tender_plan import pair

pytestmark = pytest.mark.anyio

# The engineer writes in English here (`english`), so the Lead asks in English.
QUESTION = {
    "questions": [
        {
            "id": "q1",
            "text": "Ready-mix or site-mixed concrete? (sample)",
            "options": ["Ready", "Site"],
        }
    ]
}
# The four points where driven work stops, by the card kinds that make each one (the fourth, the
# stage's end, is the sign-off and has no card). Every kind is named; keeping something beyond
# this tender is asked as well.
STOP_POINTS = {
    "missing information": ("question", "rows", "disagreement"),
    "money": ("cost", "cap", "budget", "price", "fallback"),
    "leaving the machine": ("outside", "online", "connector"),
    "sign-off": (),
}
BEYOND_THE_TENDER = ("keep", "keep_member", "desk")


def prompts(seen) -> list[str]:
    return [
        p.content
        for m in seen
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, UserPromptPart) and isinstance(p.content, str)
    ]


async def test_driver_runs_stage_after_stage(tender):  # noqa: F811
    lead = scripted(said("تمام أ - عينة"), said("تمام ب - عينة"), said("تمام ج - عينة"))
    t = await tender(lead)
    t.approve_plan()
    await t.ready(1)  # stage 1 ran with no message from the engineer, and waits for sign-off
    await t.settle()
    assert lead.calls == 1 and t.briefs() == (1, [1, 0, 0])
    assert t.stage(2).status == "pending"
    plan = store.current(t.rec)
    told = plan_driver.stage_brief_text(plan, plan.stages[0], setup_state.language())
    assert told in prompts(lead.seen[0])[-1]
    first = t.claim(1)["brief_id"]
    question, reply = t.engine.chat_messages(t.project)[:2]
    assert question["metadata"]["by"] == "one" and question["parts"][0]["text"] == told
    assert {"type": "data-stage", "id": t.stage(1).id, "data": {"stage_id": t.stage(1).id}} in (
        reply["parts"]
    )
    t.sign_off(1)
    await t.ready(2)
    assert lead.calls == 2 and t.claim(2)["brief_id"] != first
    t.sign_off(2)
    await t.ready(3)
    t.sign_off(3)
    await t.settle()
    assert [s.status for s in store.current(t.rec).stages] == ["approved"] * 3
    assert lead.calls == 3 and t.briefs() == (3, [1, 1, 1])


@pytest.fixture
def side_tools(monkeypatch):
    """A tool that sends something out of ONE and one that costs money, both for the Lead."""

    class ToArgs(BaseModel):
        to: str

    async def send(ctx, args):
        return "sent - sample"

    async def costly(ctx, args):
        title = pair("Read scanned pages")
        card = Card(uuid4().hex, "cost", title, pair("Costs money"), ("yes", "no"))
        ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
        choice = await ctx.host.ask(card)
        try:
            ctx.store.settle(card.id, choice)
        except LookupError:
            pass  # the host saved the answer itself
        return "read - sample"

    def words(verb):
        return lambda a: {"en": f"{verb} {a.to}", "ar": f"{verb} {a.to}"}

    made = [
        Tool("send_sample", "Send - sample.", ToArgs, "outside", send, words("send")),
        Tool("read_scans_sample", "Read - sample.", ToArgs, "read", costly, words("read")),
    ]
    for t in made:
        register(t)
    monkeypatch.setattr(agents, "LEAD_TOOLS", (*agents.LEAD_TOOLS, *(t.name for t in made)))
    yield
    for t in made:
        REGISTRY.pop(t.name)


async def test_driver_stops_only_at_four_points(tender, side_tools):  # noqa: F811
    kinds = typing.get_args(engine_types.CardKind)
    named = [k for found in STOP_POINTS.values() for k in found] + list(BEYOND_THE_TENDER)
    assert sorted(named) == sorted(kinds)  # a new card kind must be placed here
    lead = scripted(
        call("ask_engineer", QUESTION),
        call("send_sample", {"to": "supplier - sample"}),
        call("read_scans_sample", {"to": "drawings - sample"}),
        call("search_records", {"query": "خرسانة - عينة"}),  # reads: it does not stop
        said("تمام - عينة"),
    )
    t = await tender(lead)
    t.approve_plan()
    for calls_before, kind, point in (
        (1, "question", "missing information"),
        (2, "outside", "leaving the machine"),
        (3, "cost", "money"),
    ):
        await until(lambda: t.claim(1) and t.pending(1))
        [card] = t.pending(1)
        assert card.kind == kind and kind in STOP_POINTS[point]
        await t.settle()
        assert lead.calls == calls_before  # the work waits for the engineer
        assert t.claim(1)["status"] == "waiting_engineer" and t.stage(1).status == "now"
        answers = {"q1": "Ready"} if kind == "question" else None
        choice = "sent" if kind == "question" else "yes"
        await t.engine.answer(card.id, answer_value(card, choice, answers=answers))
    await t.ready(1)  # the fourth point: the stage's end
    await t.settle()
    with t.rec.read() as conn:
        (asked,) = conn.execute("SELECT count(*) FROM approvals").fetchone()
    assert asked == 3 and lead.calls == 5 and t.stage(2).status == "pending"


async def test_driver_resume_no_double_start(make_engine, registry, project, data_dir, drivers):  # noqa: F811
    lead1 = scripted(blocks)
    e1 = await started(make_engine(links(lead=lead1)))
    t1 = Tender(e1, registry, project)
    drivers.append(t1.driver)
    t1.approve_plan()
    await until(lambda: lead1.calls == 1)
    brief = t1.claim(1)["brief_id"]
    await t1.driver.stop()
    await e1.crash()  # a power cut in the middle of stage 1
    registry.close_all()

    lead2 = scripted(said("تمام أ - عينة"), said("تمام ب - عينة"))
    second = Projects(data_dir)  # the tender is closed when ONE starts again
    try:
        e2 = await started(make_engine(links(lead=lead2), projects=second))
        driver = plan_driver.PlanDriver(e2)
        drivers.append(driver)
        driver.start()
        await driver.resume_all()
        await driver.resume_all()  # twice changes nothing
        await until(lambda: lead2.calls == 1 and e2.active(project) is None)
        await driver.idle()
        # it closes when its Brief ends (late on a slow machine); then the engineer opens it
        await until(lambda: not any(p["id"] == project and p["open"] for p in second.list()))
        second.open(project)
        e2.opened(project)
        t2 = Tender(e2, second, project, propose=False, driver=driver)
        await t2.ready(1)  # the driver's own cut-off stage went on by itself, as the same Brief
        assert t2.claim(1)["brief_id"] == brief and t2.claim(1)["attempt"] == 1
        assert lead2.calls == 1 and t2.briefs() == (1, [1, 0, 0])
        assert e2.unfinished() == []
        t2.sign_off(1)
        await t2.ready(2)
        assert t2.briefs() == (2, [1, 1, 0])
    finally:
        second.close_all()


async def test_engineer_message_steers_running_stage(tender):  # noqa: F811
    go = asyncio.Event()

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return call("search_records", {"query": "خرسانة - عينة"})

    lead = scripted(waits, said("تمام - عينة"))
    t = await tender(lead)
    t.approve_plan()
    await until(lambda: lead.calls == 1)
    with pytest.raises(BriefBusy) as busy:  # what POST /chat gets: 409 with the Brief's id
        await t.engine.start_brief(t.project, "ركّز على الخرسانة - عينة")
    assert busy.value.brief_id == t.claim(1)["brief_id"]
    await t.engine.steer(busy.value.brief_id, "ركّز على الخرسانة - عينة")
    go.set()
    await t.ready(1)
    assert "ركّز على الخرسانة - عينة" in str(lead.seen[1])
    assert t.briefs() == (1, [1, 0, 0])
    reply = t.engine.chat_messages(t.project)[1]
    [steer] = [p for p in reply["parts"] if p["type"] == "data-steer"]
    assert steer["data"]["text"] == "ركّز على الخرسانة - عينة"


async def test_driver_respects_caps(tender, fake_clock):  # noqa: F811
    """At 80% of a cap the stage stays `now` while the cap card waits; the report ends the work
    stopped, nothing moves on, and Try again goes on with the same stage."""
    lead = scripted(said("تمام، ده اللي وصلت له - عينة"))
    t = await tender(lead)
    t.engine.book.add(  # spent today by earlier work: 90% of the day's cap
        brief_id="earlier",
        project_id=None,
        run_id="earlier",
        role="lead",
        choice=OPUS.choice,
        input_tokens=1,
        output_tokens=1,
        usd=costs.RECOMMENDED.day * 9 / 10,
        equivalent=False,
        basis="sample",
        at=fake_clock(),
    )
    t.approve_plan()
    await until(lambda: t.claim(1) and t.pending(1))
    [card] = t.pending(1)
    assert card.kind == "cap" and t.claim(1)["status"] == "paused_cap"
    assert t.stage(1).status == "now" and lead.calls == 0
    await t.engine.answer(card.id, "report")
    await until(lambda: t.claim(1)["status"] == "stopped")
    await t.settle()
    assert t.stage(1).status == "now" and t.stage(2).status == "pending"
    assert t.briefs() == (1, [1, 0, 0])
    costs.save_caps({"day": "1000"})  # the engineer raised the cap, then tries again
    lead.steps.append(said("تمام - عينة"))
    stopped = t.claim(1)["brief_id"]
    await t.driver.retry(t.project, t.stage(1).id, stopped)
    with pytest.raises(LookupError):  # that Brief is no longer the stage's latest
        await t.driver.retry(t.project, t.stage(1).id, stopped)
    await t.ready(1)
    assert t.briefs() == (2, [2, 0, 0]) and t.claim(1)["attempt"] == 2


async def test_unbuilt_stage_hands_over(tender):  # noqa: F811
    supplies = pair("The supplier quotes for the lifts")

    def asks(messages, info):
        assert supplies["en"] in prompts(messages)[-1] or supplies["ar"] in prompts(messages)[-1]
        question = {"id": "q1", "text": "Send the lift quotes (sample)", "free_text": True}
        return call("ask_engineer", {"questions": [question]})

    lead = scripted(asks, said("تمام - عينة"))
    t = await tender(lead, supplies=supplies)
    t.approve_plan()
    await until(lambda: t.claim(1) and t.pending(1))
    [card] = t.pending(1)
    assert card.kind == "question" and t.stage(1).status == "now"
    answers = {"q1": "In the files (sample)"}
    await t.engine.answer(card.id, answer_value(card, "sent", answers=answers))
    await t.ready(1)  # it asked for what ONE cannot do, and did not fail
    assert t.claim(1)["status"] == "done"
