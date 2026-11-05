"""The Brief Runner (Plan 4, Task 8): durable steps, continue, stop, steer, failures, the stream.

Scripted models only, behind fake connectors; no test calls a real AI or the real `claude`.
Synthetic «عينة» data only."""

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelRequest, ToolReturnPart, UserPromptPart

from qsone import activity, copy
from qsone.deliverables import review as deliverable_review
from qsone.deliverables import store as deliverables
from qsone.engine import costs, roles
from qsone.engine.runner import GENERAL, WORK, Engine, _stored_events
from qsone.engine.store import Store
from qsone.engine.types import (
    Asked,
    Data,
    Progress,
    Reviewed,
    Settled,
    Status,
    TextDelta,
    Unsourced,
)
from qsone.projects import Projects
from tests.engine_fakes import DEEPSEEK, HAIKU, OPUS, SAMPLE_SHEET, SONNET, call, calls, scripted
from tests.engine_fakes import text as said
from tests.samples import sample_boq_rows, sample_sheet
from tests.team_samples import BRIEF, TeamFakeHost, lead_ctx, quote_source, sample_ledger

PLAN = {
    "steps": [
        {"specialist": "Take-off QS", "task": "Quantities", "requests": 2},
        {"specialist": "Pricing QS", "task": "Rates", "requests": 2},
    ]
}
TAKE_OFF = {
    "name_en": "Take-off QS",
    "name_ar": "مهندس الحصر",
    "instructions": "You measure quantities from the BOQ. Every number comes from a tool.",
    "tools": ["search_records", "send_message"],
}
PRICING = TAKE_OFF | {"name_en": "Pricing QS", "name_ar": "مهندس التسعير"}


@dataclass
class FakeLink:
    """A model connector that serves scripted models by model id."""

    id: str
    name: str
    provider: str
    models: dict = field(default_factory=dict)
    sheet: list | None = None  # its cards; default: the sample sheet's
    kind: str = "model"
    on_device: bool = False

    async def cards(self):
        if self.sheet is not None:
            return list(self.sheet)
        return [c for c in SAMPLE_SHEET if c.choice.connector == self.id]

    def model(self, model_id: str):
        if model_id not in self.models:
            self.models[model_id] = scripted()
        return self.models[model_id]


def links(*, lead=None, specialist=None, checker=None, quick=None, only_anthropic=False):
    """The sample sheet's links. Its roles: Lead QS on OPUS, specialists on SONNET, the
    Checking QS and quick answers on DEEPSEEK (another provider)."""
    claude = FakeLink("anthropic", "Claude", "anthropic")
    deepseek = FakeLink("standard:deepseek", "DeepSeek", "deepseek")
    for card, model in ((OPUS, lead), (SONNET, specialist), (DEEPSEEK, checker or quick)):
        if model is not None:
            (claude if card.choice.connector == "anthropic" else deepseek).models[
                card.choice.model
            ] = model
    return [claude] if only_anthropic else [claude, deepseek]


@pytest.fixture
def registry(data_dir):
    found = Projects(data_dir)
    yield found
    found.close_all()


@pytest.fixture
def project(registry):
    return registry.create("مشروع - عينة", "engineer")["id"]


@pytest.fixture
async def make_engine(data_dir, registry, fake_sleep, fake_clock):
    made: list[Engine] = []

    def make(found, **options) -> Engine:
        engine = Engine(
            projects=options.pop("projects", registry),
            data_dir=data_dir,
            connectors=lambda: found,
            clock=fake_clock,
            sleep=fake_sleep,
            **options,
        )
        made.append(engine)
        return engine

    yield make
    for engine in made:
        await engine.shutdown()


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


async def started(engine: Engine) -> Engine:
    await engine.start()
    return engine


async def until(predicate, *, steps: int = 2000):
    for _ in range(steps):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("timed out")


async def finish(engine: Engine, brief_id: str) -> list:
    events = [e async for e in engine.events(brief_id)]
    await engine.result(brief_id)
    return events


def store_of(engine: Engine, chat_id: str) -> Store:
    return engine._place(chat_id).store


def states(events) -> list[str]:
    return [e.state for e in events if isinstance(e, Status)]


def tool_returns(messages) -> dict[str, str]:
    return {
        p.tool_call_id: p.content
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }


def built(messages) -> list[str]:
    return [
        json.loads(p.content)["specialist_id"]
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart) and p.tool_name == "build_specialist"
    ]


def delegate_all(task: str = "حصر - عينة"):
    """A step that delegates to every specialist built so far, in one response."""

    def step(messages, info):
        return calls(
            *(
                call("delegate", {"specialist_id": s, "task": task}, id=f"d{i}")
                for i, s in enumerate(built(messages))
            )
        )

    return step


def team_steps():
    return [
        call("plan_brief", PLAN),
        calls(call("build_specialist", TAKE_OFF), call("build_specialist", PRICING)),
        delegate_all(),
    ]


# The happy path -------------------------------------------------------------------------------


async def test_a_brief_streams_lead_text_and_progress(make_engine, project, registry):
    lead = scripted(
        call("add_source", quote_source(registry.get(project))), said("تم تسجيل المصدر - عينة")
    )
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "تم تسجيل المصدر - عينة"
    [progress] = [e for e in events if isinstance(e, Progress)]
    assert progress.agent == copy.ROLE_LEAD
    assert states(events)[:2] == ["queued", "running"] and states(events)[-1] == "done"
    store = store_of(engine, project)
    assert store.brief(brief)["status"] == "done"
    [run] = store.runs(brief)
    assert run["history"] and run["choice"] == OPUS.choice
    assert lead.calls == 2 and "You run on the model claude-opus-5-5" in str(lead.seen[0])


async def test_lead_builds_two_specialists_and_runs_them_at_once(make_engine, project):
    entered: list[str] = []
    both = asyncio.Event()

    async def specialist_step(messages, info):
        entered.append("x")
        if len(entered) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), 5)  # each waits for the other: they run at once
        return "تم الحصر - عينة"

    specialist = scripted(specialist_step, specialist_step)
    lead = scripted(*team_steps(), said("الحصر والتسعير خلصوا - عينة"))
    engine = await started(make_engine(links(lead=lead, specialist=specialist)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert states(events)[-1] == "done" and specialist.calls == 2
    store = store_of(engine, project)
    runs = store.runs(brief)
    lead_run = next(r for r in runs if r["parent_id"] is None)
    assert sorted(store.results(lead_run["id"])) == ["d0", "d1"]
    assert [r["status"] for r in runs if r["parent_id"]] == ["done", "done"]
    answers = tool_returns(lead.seen[-1])
    assert answers["d0"] == answers["d1"] == "تم الحصر - عينة"


async def test_reply_with_a_typed_number_is_marked(make_engine, project):
    lead = scripted(said("النقل 7,500 جنيه - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    [marked] = [e for e in events if isinstance(e, Unsourced)]
    assert marked.values == ("7,500",)


async def test_a_reply_number_one_ledger_number_gave_names_it(make_engine, rec_ids):
    """Decision 16.3: the reply's number opens into that ledger number's source card, also when
    the Brief is read back."""
    project, ids = rec_ids
    lead = scripted(
        call("explain_number", {"number": ids["rate"]}), said("الفئة 39,850.50 جنيه - عينة")
    )
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    named = {"39,850.50": {"id": ids["rate"], "value": "39850.50"}}
    [found] = [e for e in events if isinstance(e, Data) and e.name == "sourced"]
    assert (found.id, found.data) == (brief, {"numbers": named})
    assert not [e for e in events if isinstance(e, Unsourced)]
    store = store_of(engine, project)
    again = [e for e in _stored_events(store, store.brief(brief), engine) if isinstance(e, Data)]
    assert [e.data for e in again if e.name == "sourced"] == [{"numbers": named}]


async def test_unchecked_deliverable_with_numbers_is_checked_before_done(make_engine, rec_ids):
    project, ids = rec_ids
    rows = [{"code": "03/02", "quantity": {"number_id": ids["quantity"]}}]
    deliverable = {
        "kind": "table",
        "title": "جدول - عينة",
        "rows": rows,
        "sources": [ids["source"]],
    }
    lead = scripted(call("make_deliverable", deliverable), said("الجدول جاهز - عينة"))
    checker = scripted(call("final_result", {"code": "A", "comments": []}))
    engine = await started(make_engine(links(lead=lead, checker=checker)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    [review] = [e for e in events if isinstance(e, Reviewed)]
    assert review.review.code == "A" and review.review.checker == DEEPSEEK.choice
    assert states(events)[-1] == "done" and checker.calls == 1
    assert store_of(engine, project).unchecked(brief) == []


async def test_a_deliverable_the_brief_made_is_checked_on_its_saved_version(make_engine, registry,
                                                                           project):  # fmt: skip
    """Plan 6: a Deliverable the team made in this Brief, with numbers and no check yet, gets the
    Checking QS's check on its Saved version before the Brief is done."""
    rec = registry.get(project)
    rows = sample_boq_rows(rec, 2)
    sheet = {"kind": "sheet", "variant": "boq", "title": "جدول - عينة", "language": "ar"}
    lead = scripted(call("deliverable_create", sheet | {"rows": rows}), said("الجدول جاهز - عينة"))
    checker = scripted(call("final_result", {"code": "B", "comments": []}))
    engine = await started(make_engine(links(lead=lead, checker=checker)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    [review] = [e for e in events if isinstance(e, Reviewed)]
    assert review.review.code == "B" and checker.calls == 1 and states(events)[-1] == "done"
    [d] = [e["id"] for e in deliverables.list_deliverables(rec)]
    closeout = deliverable_review.closeout(rec, d)
    assert closeout["check"]["version_n"] == 1 and closeout["check"]["code"] == "B"


async def test_a_deliverables_card_stays_in_the_stored_chat(make_engine, registry, project):
    """The chat read again (a page reload) keeps the Deliverable card where the Brief made it."""
    rec = registry.get(project)
    sheet = {"kind": "sheet", "variant": "boq", "title": "جدول - عينة", "language": "ar"}
    rows = sample_boq_rows(rec, 2)
    lead = scripted(call("deliverable_create", sheet | {"rows": rows}), said("الجدول جاهز - عينة"))
    checker = scripted(call("final_result", {"code": "A", "comments": []}))
    engine = await started(make_engine(links(lead=lead, checker=checker)))
    brief = await engine.start_brief(project, BRIEF)
    await finish(engine, brief)
    [d] = [e["id"] for e in deliverables.list_deliverables(rec)]
    engine._briefs.pop(brief, None)  # read from the store, as after a restart
    reply = engine.chat_messages(project)[-1]
    cards = [p for p in reply["parts"] if p["type"] == "data-deliverable"]
    assert cards == [{"type": "data-deliverable", "id": d, "data": {"id": d}}]


async def test_a_deliverable_the_brief_proposed_to_is_checked_once(make_engine, registry, project):
    """A Sheet the team only proposed changes to has its Saved version checked when it has no
    check; one this Brief did not touch, or one checked already, is left as it is."""
    rec = registry.get(project)
    touched, untouched, done = sample_sheet(rec), sample_sheet(rec), sample_sheet(rec)
    check = {"version_n": 1, "code": "A", "checker": "model-sample", "same_provider": False}
    deliverable_review.record_check(rec, done, summary="", comments=[], **check)
    row = next(r for r in deliverables.view(rec, touched)["rows"] if r["kind"] == "item")["id"]
    op = {"op": "set_field", "row": row, "key": "description", "value": "خرسانة - عينة"}
    row_done = next(r for r in deliverables.view(rec, done)["rows"] if r["kind"] == "item")["id"]
    lead = scripted(
        calls(
            call("deliverable_propose", {"id": touched, "ops": [op]}),
            call("deliverable_propose", {"id": done, "ops": [op | {"row": row_done}]}),
        ),
        said("اقترحت تعديل - عينة"),
    )
    checker = scripted(call("final_result", {"code": "A", "comments": []}))
    engine = await started(make_engine(links(lead=lead, checker=checker)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert [e.deliverable_id for e in events if isinstance(e, Reviewed)] == [touched]
    assert checker.calls == 1
    assert deliverable_review.closeout(rec, touched)["check"]["version_n"] == 1
    assert deliverable_review.closeout(rec, untouched)["check"] is None


def table_brief(ids: dict) -> dict:
    rows = [{"code": "03/02", "quantity": {"number_id": ids["quantity"]}}]
    return {"kind": "table", "title": "جدول - عينة", "rows": rows, "sources": [ids["source"]]}


async def checked_on(engine: Engine, project: str) -> tuple[list, Reviewed]:
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    [review] = [e for e in events if isinstance(e, Reviewed)]
    return events, review


async def test_the_engineers_checker_choice_wins_even_on_the_leads_model(make_engine, rec_ids):
    """The live Haiku run: every role on one model; the check runs on it, blind, no card."""
    project, ids = rec_ids
    for role in roles.ROLES:
        roles.choose(role, HAIKU.choice)
    claude = links(only_anthropic=True)[0]
    model = claude.models[HAIKU.choice.model] = scripted(
        call("make_deliverable", table_brief(ids)),
        said("الجدول جاهز - عينة"),
        call("final_result", {"code": "A", "comments": []}),
    )
    events, review = await checked_on(await started(make_engine([claude])), project)
    assert review.review.checker == HAIKU.choice and review.review.same_provider is True
    assert not [e for e in events if isinstance(e, Asked)] and states(events)[-1] == "done"
    assert model.calls == 3 and len(model.seen[2]) == 1  # a fresh session: the packet only


async def test_a_default_checker_never_moves_to_a_costlier_model(make_engine, rec_ids):
    """Checking QS left at its default, on the maker's model, nothing the same price or
    cheaper: it stays there (no costlier model, no card)."""
    project, ids = rec_ids
    roles.choose("lead", HAIKU.choice)  # the default Checking QS here is HAIKU too
    claude = FakeLink("anthropic", "Claude", "anthropic", sheet=[OPUS, HAIKU])
    claude.models[HAIKU.choice.model] = scripted(
        call("make_deliverable", table_brief(ids)),
        said("الجدول جاهز - عينة"),
        call("final_result", {"code": "A", "comments": []}),
    )
    events, review = await checked_on(await started(make_engine([claude])), project)
    assert review.review.checker == HAIKU.choice
    assert not [e for e in events if isinstance(e, Asked)] and states(events)[-1] == "done"
    assert OPUS.choice.model not in claude.models


async def test_a_default_checker_moves_off_the_makers_model_to_a_cheaper_one(make_engine, rec_ids):
    project, ids = rec_ids
    roles.choose("lead", SONNET.choice)  # the default Checking QS here is SONNET too
    claude = links(only_anthropic=True)[0]
    claude.models[SONNET.choice.model] = scripted(
        call("make_deliverable", table_brief(ids)), said("الجدول جاهز - عينة")
    )
    claude.models[HAIKU.choice.model] = scripted(
        call("final_result", {"code": "A", "comments": []})
    )
    _, review = await checked_on(await started(make_engine([claude])), project)
    assert review.review.checker == HAIKU.choice and review.review.same_provider is True


@pytest.fixture
async def rec_ids(registry, project):
    """The sample ledger in the project, made by an earlier (done) Brief."""
    rec = registry.get(project)
    ctx = lead_ctx(rec, TeamFakeHost())
    ids = await sample_ledger(ctx)
    ctx.store.set_status(ctx.brief_id, "done")
    return project, ids


async def test_a_brief_in_general_runs_without_a_project(make_engine):
    lead = scripted(said("أهلاً - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(GENERAL, "سؤال - عينة")
    events = await finish(engine, brief)
    assert states(events)[-1] == "done"
    assert store_of(engine, GENERAL).brief(brief)["chat_id"] == GENERAL


async def test_the_next_brief_hears_the_earlier_one(make_engine, project):
    lead = scripted(said("الأول - عينة"), said("الثاني - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    first = await engine.start_brief(project, "أول سؤال - عينة")
    await finish(engine, first)
    second = await engine.start_brief(project, "تاني سؤال - عينة")
    await finish(engine, second)
    assert "أول سؤال - عينة" in str(lead.seen[1]) and "الأول - عينة" in str(lead.seen[1])


class Price(BaseModel):
    item: str
    note: str


async def test_a_brief_from_code_returns_its_typed_result(make_engine, project):
    def answer(messages, info):
        [tool] = info.output_tools
        return call(tool.name, {"item": "03/02", "note": "عينة"})

    lead = scripted(answer)
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(
        project, BRIEF, instruction="Answer as a Price.", output_type=Price
    )
    assert await engine.result(brief) == Price(item="03/02", note="عينة")
    assert "Answer as a Price." in str(lead.seen[0])


# Continue, crash, a fresh launch --------------------------------------------------------------


async def test_crash_and_continue(make_engine, data_dir, project, registry):
    entered = asyncio.Event()

    async def blocks(messages, info):
        entered.set()
        await asyncio.Event().wait()

    lead1 = scripted(
        call("add_source", quote_source(registry.get(project))),
        *team_steps(),
        said("لن يصل - عينة"),
    )
    e1 = await started(make_engine(links(lead=lead1, specialist=scripted(blocks, blocks))))
    brief = await e1.start_brief(project, BRIEF)
    await asyncio.wait_for(entered.wait(), 5)
    await e1.crash()
    registry.close_all()

    lead2 = scripted(said("خلصنا - عينة"))
    specialist2 = scripted(said("تم - عينة"), said("تم - عينة"))
    second = Projects(data_dir)
    try:
        e2 = await started(make_engine(links(lead=lead2, specialist=specialist2), projects=second))
        [found] = e2.unfinished()
        assert found["id"] == brief and found["step"]["en"] and found["chat_id"] == project
        for _ in range(5):
            await asyncio.sleep(0.01)
        assert lead2.calls == 0 and specialist2.calls == 0  # nothing ran on its own
        await e2.continue_brief(brief)
        events = await finish(e2, brief)
        assert states(events)[-1] == "done"
        assert lead2.calls == 1  # only the resume request
        assert specialist2.calls == 2
        for seen in specialist2.seen:  # each continued from its own Checkpoint, task once
            prompts = [
                p.content
                for m in seen
                if isinstance(m, ModelRequest)
                for p in m.parts
                if isinstance(p, UserPromptPart)
            ]
            assert prompts.count("حصر - عينة") == 1
        rec = second.get(project)
        with rec.read() as c:
            assert c.execute("SELECT count(*) FROM sources").fetchone() == (1,)  # once
    finally:
        second.close_all()


async def test_a_fresh_launch_never_continues_by_itself(make_engine, project, registry, data_dir):
    async def blocks(messages, info):
        await asyncio.Event().wait()

    e1 = await started(make_engine(links(lead=scripted(blocks))))
    brief = await e1.start_brief(project, BRIEF)
    await until(lambda: store_of(e1, project).brief(brief)["status"] == "running")
    await e1.crash()
    lead2 = scripted(said("عينة"))
    e2 = await started(make_engine(links(lead=lead2)))
    await asyncio.sleep(0.05)
    assert lead2.calls == 0 and e2.active(project) is None
    assert store_of(e2, project).brief(brief)["status"] == "running"
    assert [b["id"] for b in e2.unfinished()] == [brief]


async def test_a_waiting_approval_is_asked_again_after_restart(make_engine, project, registry):
    costs.save_caps({"budget_above": "0"})  # plan_brief asks for the budget
    e1 = await started(make_engine(links(lead=scripted(call("plan_brief", PLAN)))))
    brief = await e1.start_brief(project, BRIEF)
    store = store_of(e1, project)
    await until(lambda: store.pending(brief))
    [old] = store.pending(brief)
    await e1.crash()

    lead2 = scripted(call("plan_brief", PLAN), said("الخطة جاهزة - عينة"))
    e2 = await started(make_engine(links(lead=lead2)))
    store = store_of(e2, project)
    await e2.continue_brief(brief)
    await until(lambda: store.pending(brief))
    [new] = store.pending(brief)
    assert new.id != old.id and new.kind == "budget"
    with store.rec.read() as c:
        (status,) = c.execute("SELECT status FROM approvals WHERE id = ?", (old.id,)).fetchone()
    assert status == "withdrawn"
    await e2.answer(new.id, "yes")
    events = await finish(e2, brief)
    assert states(events)[-1] == "done"
    assert any(isinstance(e, Settled) and e.card_id == new.id for e in events)


# Stop, steer, pause ----------------------------------------------------------------------------


async def test_stop_reaches_every_agent(make_engine, project):
    entered = asyncio.Event()

    async def blocks(messages, info):
        entered.set()
        await asyncio.Event().wait()

    specialist = scripted(blocks, blocks)
    lead = scripted(*team_steps())
    engine = await started(make_engine(links(lead=lead, specialist=specialist)))
    brief = await engine.start_brief(project, BRIEF)
    await asyncio.wait_for(entered.wait(), 5)
    await engine.stop(brief)
    assert specialist.cancelled
    stored = store_of(engine, project).brief(brief)
    assert stored["status"] == "stopped" and stored["step"] == copy.STOPPED
    assert engine.active(project) is None
    with pytest.raises(LookupError):
        await engine.stop(brief)


async def test_stop_cancels_a_thinking_lead_and_withdraws_its_card(make_engine, project):
    costs.save_caps({"budget_above": "0"})
    engine = await started(make_engine(links(lead=scripted(call("plan_brief", PLAN)))))
    brief = await engine.start_brief(project, BRIEF)
    store = store_of(engine, project)
    await until(lambda: store.pending(brief))
    [card] = store.pending(brief)
    events = engine.events(brief)
    await engine.stop(brief)
    seen = [e async for e in events]
    assert states(seen)[-1] == "stopped" and store.pending(brief) == []
    withdrawn = [e for e in seen if getattr(e, "name", None) == "card" and e.id == card.id]
    assert withdrawn and withdrawn[-1].data == {"status": "withdrawn"}


async def test_steer_reaches_the_running_lead(make_engine, project, registry):
    go = asyncio.Event()
    source = quote_source(registry.get(project))

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return call("add_source", source)

    lead = scripted(waits, said("تمام - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    await until(lambda: lead.calls == 1)
    await engine.steer(brief, "ركّز على الخرسانة - عينة")
    go.set()
    events = await finish(engine, brief)
    assert states(events)[-1] == "done"
    assert "ركّز على الخرسانة - عينة" in str(lead.seen[1])


async def test_pause_all_says_how_many_and_keeps_checkpoints(make_engine, registry):
    async def blocks(messages, info):
        await asyncio.Event().wait()

    chats = [registry.create(f"مشروع {i} - عينة", "engineer")["id"] for i in range(2)]
    engine = await started(make_engine(links(lead=scripted(blocks, blocks))))
    briefs = [await engine.start_brief(chat, BRIEF) for chat in chats]
    await until(
        lambda: all(
            store_of(engine, c).brief(b)["status"] == "running"
            for c, b in zip(chats, briefs, strict=True)
        )
    )
    assert await engine.pause_all() == 2
    assert sorted(b["id"] for b in engine.unfinished()) == sorted(briefs)
    assert all(engine.active(c) is None for c in chats)


async def test_at_most_three_briefs_run_at_once(make_engine, registry):
    release = asyncio.Event()

    async def waits(messages, info):
        await release.wait()
        return "تم - عينة"

    chats = [registry.create(f"مشروع {i} - عينة", "engineer")["id"] for i in range(4)]
    lead = scripted(*[waits] * 4)
    engine = await started(make_engine(links(lead=lead)))
    briefs = [await engine.start_brief(chat, BRIEF) for chat in chats]
    await until(lambda: lead.calls == 3)
    await asyncio.sleep(0.05)
    assert lead.calls == 3
    assert store_of(engine, chats[3]).brief(briefs[3])["status"] == "queued"
    release.set()
    for brief in briefs:
        await engine.result(brief)
    assert lead.calls == 4
    assert all(
        store_of(engine, c).brief(b)["status"] == "done" for c, b in zip(chats, briefs, strict=True)
    )


async def test_a_second_brief_in_a_busy_chat_is_refused(make_engine, project):
    async def blocks(messages, info):
        await asyncio.Event().wait()

    from qsone.engine.runner import BriefBusy

    engine = await started(make_engine(links(lead=scripted(blocks))))
    brief = await engine.start_brief(project, BRIEF)
    with pytest.raises(BriefBusy) as e:
        await engine.start_brief(project, "تاني - عينة")
    assert e.value.brief_id == brief
    await engine.stop(brief)


# Failures --------------------------------------------------------------------------------------


def busy(messages, info):
    raise ModelHTTPError(529, "sample-model", {"error": "overloaded"})


def offline(messages, info):
    raise ConnectionError("no route - sample")


async def test_provider_down_moves_to_same_or_cheaper(make_engine, project, fake_sleep):
    lead = scripted(busy, busy)
    specialist_model = scripted(said("رد من نموذج تاني - عينة"))
    engine = await started(make_engine(links(lead=lead, specialist=specialist_model)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert states(events)[-1] == "done" and fake_sleep.delays == [5]
    moved = [e for e in events if isinstance(e, Progress) and e.text["en"].startswith(OPUS.name)]
    assert moved and moved[0].text == copy.fill(
        copy.FALLBACK_MOVED, old=OPUS.name, role=copy.ROLE_LEAD, new=SONNET.name
    )
    [run] = store_of(engine, project).runs(brief)
    assert run["choice"] == SONNET.choice


async def test_only_costlier_left_asks(make_engine, project):
    roles.choose("lead", HAIKU.choice)
    claude = links(only_anthropic=True)[0]
    claude.models[HAIKU.choice.model] = scripted(busy, busy)
    claude.models[SONNET.choice.model] = scripted(said("رد أغلى - عينة"))
    engine = await started(make_engine([claude]))
    brief = await engine.start_brief(project, BRIEF)
    events = engine.events(brief)
    seen = []
    async for event in events:
        seen.append(event)
        if isinstance(event, Asked):
            assert event.card.kind == "fallback" and event.card.options == ("yes", "no")
            assert SONNET.name in event.card.detail["en"]
            await engine.answer(event.card.id, "yes")
    assert states(seen)[-1] == "done"


async def test_no_to_a_costlier_model_fails_plainly(make_engine, project):
    roles.choose("lead", HAIKU.choice)
    claude = links(only_anthropic=True)[0]
    claude.models[HAIKU.choice.model] = scripted(busy, busy)
    engine = await started(make_engine([claude]))
    brief = await engine.start_brief(project, BRIEF)
    seen = []
    async for event in engine.events(brief):
        seen.append(event)
        if isinstance(event, Asked):
            await engine.answer(event.card.id, "no")
    assert states(seen)[-1] == "failed"
    assert seen[-1].step == copy.fill(copy.AI_FAILED, provider="Claude")


async def test_no_internet_waits_then_continues(make_engine, project, fake_sleep):
    lead = scripted(offline, offline, offline, offline, offline, said("رجع النت - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert fake_sleep.delays == [5, 15, 30, 60, 60]
    assert "waiting_connection" in states(events) and states(events)[-1] == "done"
    waiting = [e for e in events if isinstance(e, Status) and e.state == "waiting_connection"]
    assert waiting[0].step == copy.WAITING_INTERNET


async def test_a_refused_key_fails_with_plain_words(make_engine, project):
    from pydantic_ai.exceptions import ModelAuthenticationError

    def refused(messages, info):
        raise ModelAuthenticationError("sample-model", "invalid x-api-key")

    engine = await started(make_engine(links(lead=scripted(refused))))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert states(events)[-1] == "failed"
    assert events[-1].step == copy.KEY_REFUSED  # the Claude key: Anthropic's own words


async def test_cap_pause_then_continue(make_engine, project, fake_clock):
    lead = scripted(said("كمّلنا - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    engine.book.add(  # spent today, by an earlier Brief: 90% of the day's cap
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
    brief = await engine.start_brief(project, BRIEF)
    seen = []
    async for event in engine.events(brief):
        seen.append(event)
        if isinstance(event, Asked):
            assert event.card.kind == "cap"
            assert states(seen)[-1] == "paused_cap"
            await engine.answer(event.card.id, "continue")
    assert states(seen)[-1] == "done" and lead.calls == 1


async def test_cap_reached_stops(make_engine, project, fake_clock):
    lead = scripted(said("لن يصل - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    engine.book.add(
        brief_id="earlier",
        project_id=None,
        run_id="earlier",
        role="lead",
        choice=OPUS.choice,
        input_tokens=1,
        output_tokens=1,
        usd=costs.RECOMMENDED.day,
        equivalent=False,
        basis="sample",
        at=fake_clock(),
    )
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert states(events)[-1] == "stopped" and lead.calls == 0


async def test_cards_check_the_choice(make_engine, project):
    costs.save_caps({"budget_above": "0"})
    engine = await started(make_engine(links(lead=scripted(call("plan_brief", PLAN)))))
    brief = await engine.start_brief(project, BRIEF)
    store = store_of(engine, project)
    await until(lambda: store.pending(brief))
    [card] = store.pending(brief)
    with pytest.raises(ValueError):
        await engine.answer(card.id, "maybe")
    with pytest.raises(LookupError):
        await engine.answer("no-such-card", "yes")
    assert engine.options(card.id) == list(card.options)
    await engine.stop(brief)


# Plan 7: the team and its activity -----------------------------------------------------------


async def test_team_and_activity_follow_the_agents(make_engine, project):
    go = asyncio.Event()

    async def waits(messages, info):
        await asyncio.wait_for(go.wait(), 5)
        return "تم - عينة"

    lead = scripted(waits)
    engine = await started(make_engine(links(lead=lead)))
    got: list[dict] = []

    async def listen():
        async for event in activity.subscribe(project):
            got.append(event)

    listener = asyncio.create_task(listen())
    await asyncio.sleep(0)
    brief = await engine.start_brief(project, BRIEF)
    await until(lambda: lead.calls == 1)
    team = engine.team(project)
    [agent] = team["agents"]
    assert agent["role"] == copy.ROLE_LEAD and agent["brief_id"] == brief
    assert agent["model"] == OPUS.choice.model and agent["state"] == "thinking"
    go.set()
    await finish(engine, brief)
    await asyncio.sleep(0.01)
    listener.cancel()
    kinds = [e["type"] for e in got]
    assert "agent" in kinds and kinds[-1] == "agent-gone"
    assert got[-1]["id"] == agent["id"]
    assert engine.team(project)["agents"] == []


# Privacy --------------------------------------------------------------------------------------


async def test_nothing_readable_on_disk_after_a_brief(make_engine, project, data_dir):
    lead = scripted(said("رد سري - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    secret = "نص التكليف السري - عينة"
    brief = await engine.start_brief(project, secret)
    await finish(engine, brief)
    needles = [secret.encode(), "رد سري".encode()]
    for path in data_dir.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert not any(n in data for n in needles), path
    assert not (data_dir / WORK).exists() or not any((data_dir / WORK).iterdir())


def claude_code_link(script, log):
    from qsone.engine.connectors.claude_code import ClaudeCodeConnector
    from tests.engine_fakes import fake_claude_command

    return ClaudeCodeConnector(None, command_prefix=fake_claude_command(script=script, log=log))


async def test_the_checking_qs_on_claude_code_answers_in_json_text(make_engine, rec_ids, tmp_path):
    from qsone.engine.connectors.claude_code import ID
    from qsone.engine.runner import REVIEW_AS_JSON
    from qsone.engine.types import ModelChoice
    from tests.engine_fakes import read_fake_log

    project, ids = rec_ids
    rows = [{"code": "03/02", "quantity": {"number_id": ids["quantity"]}}]
    deliverable = {
        "kind": "table",
        "title": "جدول - عينة",
        "rows": rows,
        "sources": [ids["source"]],
    }
    lead = scripted(call("make_deliverable", deliverable), said("الجدول جاهز - عينة"))
    review = {"code": "B", "comments": [{"about": "03/02", "text": "راجع الوحدة - عينة"}]}
    answer = f"المراجعة - عينة:\n{json.dumps(review, ensure_ascii=False)}\nخلصت."
    log = tmp_path / "claude.log"
    claude = claude_code_link(["init", {"text": answer}, "result"], log)
    roles.choose("checker", ModelChoice(ID, "sonnet"))
    engine = await started(make_engine([*links(lead=lead), claude]))
    engine.base_url = "http://127.0.0.1:9/"  # never reached: the fake calls no tool
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert states(events)[-1] == "done"
    [reviewed] = [e.review for e in events if isinstance(e, Reviewed)]
    assert reviewed.code == "B" and reviewed.checker == ModelChoice(ID, "sonnet")
    assert reviewed.comments == tuple(review["comments"])
    assert reviewed.same_provider  # the Lead's Claude and Claude Code are both Anthropic
    [run] = read_fake_log(log)
    [task] = [line for line in run["stdin"] if line["type"] == "user"]
    assert REVIEW_AS_JSON in task["message"]["content"][0]["text"]
    assert store_of(engine, project).unchecked(brief) == []


async def test_steer_reaches_a_lead_on_claude_code(make_engine, project, tmp_path):
    from qsone.engine.connectors.claude_code import ID
    from qsone.engine.types import ModelChoice
    from tests.engine_fakes import read_fake_log

    log = tmp_path / "claude.log"
    script = ["init", {"await_user": 20}, {"text": "تمام، الخرسانة - عينة"}, "result"]
    roles.choose("lead", ModelChoice(ID, "sonnet"))
    engine = await started(make_engine([*links(), claude_code_link(script, log)]))
    engine.base_url = "http://127.0.0.1:9/"  # never reached: the fake calls no tool
    brief = await engine.start_brief(project, BRIEF)
    await until(lambda: log.exists() and bool(read_fake_log(log)[0]["stdin"]), steps=4000)
    await engine.steer(brief, "ركّز على الخرسانة - عينة")
    events = await finish(engine, brief)
    assert states(events)[-1] == "done"
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "تمام، الخرسانة - عينة"
    [run] = read_fake_log(log)
    users = [line["message"]["content"] for line in run["stdin"] if line["type"] == "user"]
    assert users[1] == [{"type": "text", "text": "ركّز على الخرسانة - عينة"}]


async def test_stop_ends_a_claude_code_specialist(make_engine, project, tmp_path, data_dir):
    from qsone.engine.connectors.claude_code import ID, ClaudeCodeConnector
    from qsone.engine.types import ModelChoice
    from tests.engine_fakes import fake_claude_command, read_fake_log

    log = tmp_path / "claude.log"
    command = fake_claude_command(script=["init", {"sleep": 30}], log=log)
    claude = ClaudeCodeConnector(None, command_prefix=command)
    roles.choose("specialist", ModelChoice(ID, "sonnet"))
    lead = scripted(*team_steps())
    engine = await started(make_engine([*links(lead=lead), claude]))
    engine.base_url = "http://127.0.0.1:9/"  # never reached: the fake only sleeps
    brief = await engine.start_brief(project, BRIEF)

    def both_read_their_task() -> bool:
        runs = read_fake_log(log) if log.exists() else []
        return len(runs) == 2 and all(run["stdin"] for run in runs)

    await until(both_read_their_task, steps=4000)
    await engine.stop(brief)
    assert [run["ended"] for run in read_fake_log(log)] == ["interrupted", "interrupted"]
    assert store_of(engine, project).brief(brief)["status"] == "stopped"
    assert not (data_dir / WORK).exists() or not any((data_dir / WORK).iterdir())
