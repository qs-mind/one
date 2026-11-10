"""The team as the screen sees it now (Phase 1, C5): each member's state and doing, its `member`
events, the member each cost and check is booked to, and the sheet that names its model.

Scripted models and the fake `claude` only; no test calls a real AI. Synthetic «عينة» data only."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qsone import activity, copy
from qsone import phase1_contract as c
from qsone.engine import costs, identity, identity_live, identity_routes, oneshot, roles
from qsone.engine.agents import lead_spec
from qsone.engine.connectors.claude_code import ID as CLAUDE_CODE
from qsone.engine.connectors.claude_code import ClaudeCodeConnector
from qsone.engine.costs import Spending
from qsone.engine.routes import settings_router
from qsone.engine.runner import Engine
from qsone.engine.store import CostBook, Store
from qsone.engine.tools import call
from qsone.engine.types import ModelChoice, Review
from qsone.projects import Projects
from tests.engine_fakes import OPUS, SONNET, FakeHost, fake_claude_command, scripted, text
from tests.fakes_tools import tool_ctx
from tests.samples import sample_sheet
from tests.test_engine_runner import finish, links, started

DOING = c.Text(en="Measuring the slabs - sample", ar="بيحصر البلاطات - عينة")
MEMBER = "5a" + "3" * 30
PNG = b"\x89PNG\r\n\x1a\n" + b"page-image-sample" * 8


@pytest.fixture(autouse=True)
def no_sheet():
    identity.forget_sheet()
    costs.save_caps({"budget_above": "100"})  # no budget card in a Brief here
    yield
    identity.forget_sheet()


@pytest.fixture
def registry(data_dir):
    found = Projects(data_dir)
    yield found
    found.close_all()


def member_ids(engine, rec, general) -> dict[str, tuple[str, c.Text | None]]:
    return {m.id: (m.state, m.doing) for m in identity_live.team_members(engine, rec, general)}


def a_brief(*, agents=(), cards=(), finished=False):
    agents = {
        f"run-{n}": SimpleNamespace(spec=SimpleNamespace(id=who), state=state, line=line)
        for n, (who, state, line) in enumerate(agents)
    }
    waiting = {card.title["en"]: (card, None) for card in cards}
    return SimpleNamespace(finished=finished, agents=agents, waiting=waiting)


def engine_with(*briefs):
    return SimpleNamespace(_in=lambda project_id: list(briefs))


# State and doing ------------------------------------------------------------------------------


def test_working_waiting_and_failed_come_from_the_running_brief(rec, general):
    working = engine_with(a_brief(agents=[(identity.LEAD, "working", DOING)]))
    assert member_ids(working, rec, general)[identity.LEAD] == ("working", DOING)
    thinking = engine_with(a_brief(agents=[(identity.CHECKER, "thinking", None)]))
    assert member_ids(thinking, rec, general)[identity.CHECKER] == ("working", None)

    card = SimpleNamespace(title={"en": "Spend $2.00 - sample", "ar": "صرف ٢ دولار - عينة"})
    asking = engine_with(a_brief(agents=[(identity.LEAD, "working", DOING)], cards=[card]))
    assert member_ids(asking, rec, general)[identity.LEAD] == (
        "waiting",
        c.Text(**copy.fill(copy.MEMBER_WAITING_FOR, what=card.title)),
    )
    waits = engine_with(a_brief(agents=[(identity.LEAD, "waiting", None)]))
    assert member_ids(waits, rec, general)[identity.LEAD] == (
        "waiting",
        c.Text(**copy.MEMBER_WAITING),
    )

    failed = engine_with(a_brief(agents=[(identity.CHECKER, "failed", DOING)]))
    assert member_ids(failed, rec, general)[identity.CHECKER] == ("failed", None)
    done = engine_with(a_brief(agents=[(identity.LEAD, "working", DOING)], finished=True))
    assert member_ids(done, rec, general)[identity.LEAD] == ("idle", None)


def test_a_last_run_that_failed_shows_until_the_next_one(rec, general):
    store = Store(rec, project_id=rec.id)
    brief = store.new_brief(rec.id, "سؤال - عينة")
    first = store.new_run(brief, lead_spec(), OPUS.choice, None)
    store.set_run(first, status="failed")
    assert member_ids(None, rec, general)[identity.LEAD] == ("failed", None)
    assert member_ids(None, rec, general)[identity.CHECKER] == ("idle", None)
    later = store.new_run(brief, lead_spec(), OPUS.choice, None)
    store.set_run(later, status="done")
    assert member_ids(None, rec, general)[identity.LEAD] == ("idle", None)


# Member events and the Brief's costs ----------------------------------------------------------


async def test_a_brief_publishes_member_events_on_the_tenders_channel(
    data_dir, registry, monkeypatch
):
    sent: list[tuple[str, dict]] = []
    publish = activity.publish
    monkeypatch.setattr(
        activity,
        "publish",
        lambda channel, event: (sent.append((channel, event)), publish(channel, event)),
    )
    project = registry.create("مشروع - عينة", "engineer")["id"]
    engine = await started(
        Engine(
            projects=registry,
            data_dir=data_dir,
            connectors=lambda: links(lead=scripted(text("تمام - عينة"))),
        )
    )
    try:
        await finish(engine, await engine.start_brief(project, "سؤال - عينة"))
    finally:
        await engine.shutdown()
    events = [(ch, e) for ch, e in sent if e.get("type") == "member"]
    assert events and all(ch == project for ch, _ in events)
    first = c.MemberEvent.model_validate(events[0][1])
    assert (first.member.id, first.member.role, first.member.state) == (
        identity.LEAD,
        "lead",
        "working",
    )
    assert first.member.name == c.Text(**copy.LEAD_NAME)


async def test_a_lead_on_claude_code_books_its_cost_to_the_lead(data_dir, registry, tmp_path):
    script = ["init", {"usage": [10, 5]}, {"text": "تمام - عينة"}, {"result": {"cost": "0.02"}}]
    claude = ClaudeCodeConnector(
        None, command_prefix=fake_claude_command(script=script, log=tmp_path / "claude.log")
    )
    roles.choose("lead", ModelChoice(CLAUDE_CODE, "sonnet"))
    project = registry.create("مشروع - عينة", "engineer")["id"]
    engine = await started(
        Engine(projects=registry, data_dir=data_dir, connectors=lambda: [*links(), claude])
    )
    engine.base_url = "http://127.0.0.1:9/"  # never reached: the fake calls no tool
    try:
        await finish(engine, await engine.start_brief(project, "سؤال - عينة"))
        with engine.engineer_records().read() as conn:
            found = conn.execute("SELECT connector, member_id FROM ai_costs").fetchall()
        assert found == [(CLAUDE_CODE, identity.LEAD)]
    finally:
        await engine.shutdown()


async def test_a_one_shot_on_the_subscription_books_its_cost_to_the_member(
    general, data_dir, fake_clock, tmp_path
):
    script = [
        "init",
        {"usage": [1500, 30]},
        {"text": "خرسانة - عينة"},
        {"result": {"cost": "0.02"}},
    ]
    code = ClaudeCodeConnector(
        None, command_prefix=fake_claude_command(script=script, log=tmp_path / "claude.log")
    )
    subscription = replace(
        SONNET, choice=ModelChoice(CLAUDE_CODE, "sonnet"), images=False, subscription=True
    )
    host = FakeHost(brief_id="b-sample")
    models = oneshot.Models(
        sheet=(replace(OPUS, images=False), subscription),
        roles={"lead": OPUS.choice, "specialist": OPUS.choice},
        connectors={code.id: code},
        spending=Spending(CostBook(general), clock=fake_clock),
        host=host,
        brief_id=host.brief_id,
        project_id="p-sample",
        run_id="r-sample",
        work=data_dir / "claude-work",
        member_id=MEMBER,
    )
    await oneshot.transcribe(PNG, page=1, models=models)
    with general.read() as conn:
        assert conn.execute("SELECT connector, member_id, usd FROM ai_costs").fetchall() == [
            (CLAUDE_CODE, MEMBER, "0.02")
        ]
    assert identity.record(general, MEMBER).cost_usd == "0.00"  # a subscription: no paid cost


# Checks on a versioned output -----------------------------------------------------------------


async def test_a_check_of_a_saved_version_counts_in_its_makers_record(rec, general):
    d = sample_sheet(rec)
    ctx = tool_ctx(rec)
    ctx.host.engine = SimpleNamespace(engineer_records=lambda: general)

    async def checker(packet, maker):
        return Review("B", (), SONNET.choice, False, 1)

    ctx.host.checker = checker
    await call("submit_for_check", {"deliverable_id": d}, ctx)
    found = identity.record(general, ctx.agent.id)
    assert (found.checks_passed, found.checks_total) == (1, 1)


# The sheet that names each member's model -----------------------------------------------------


def test_the_ai_settings_listing_names_the_members_models():
    app = FastAPI()
    app.include_router(settings_router(claude_command=fake_claude_command()))
    http = TestClient(app)
    assert http.put("/settings/ai/claude-code", json={"path": None, "on": True}).status_code == 200
    assert identity._model("lead") is None
    assert http.get("/settings/ai").status_code == 200
    model = identity._model("lead")
    assert model is not None and model.provider == "anthropic"


async def test_the_listing_at_app_start_names_the_members_models(data_dir, registry):
    engine = Engine(projects=registry, data_dir=data_dir, connectors=lambda: links())
    await identity_routes.list_models(engine)
    assert identity._model("lead").name == OPUS.name


async def test_no_listing_at_app_start_before_the_ai_consent(data_dir, registry, no_consent):
    engine = Engine(projects=registry, data_dir=data_dir, connectors=lambda: links())
    await identity_routes.list_models(engine)
    assert identity._model("lead") is None
