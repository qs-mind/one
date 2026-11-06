"""The team tools (Plan 4, Task 7): the Lead QS, its specialists, Deliverables and saved Desks.

Synthetic «عينة» data only; no test calls a real AI."""

import json

import pytest
from pydantic_ai import Agent, DeferredToolRequests, ModelRetry
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from qsone import copy
from qsone.engine import costs, desks
from qsone.engine.agents import (
    CHECKER_WORDS,
    LEAD_WORDS,
    SPECIALIST_WORDS,
    checker_spec,
    lead_spec,
    trim_history,
    words,
)
from qsone.engine.team import MAX_SPECIALISTS, TEAM_TOOLS, specialist_run, specialists
from qsone.engine.tools import REGISTRY, Denied, call, toolset
from tests.engine_fakes import SONNET, scripted
from tests.engine_fakes import call as tool_call
from tests.engine_fakes import calls as tool_calls
from tests.team_samples import TeamFakeHost, lead_ctx, sample_ledger

PLAN = {"steps": [{"specialist": "Take-off QS", "task": "Quantities", "requests": 2}]}
SPECIALIST = {
    "name_en": "Take-off QS",
    "name_ar": "مهندس الحصر",
    "instructions": "You measure quantities from the BOQ. Every number comes from a tool.",
    "tools": ["search_records", "record_number", "send_message"],
}


@pytest.fixture
def host():
    return TeamFakeHost(answers={"budget": "yes"})


@pytest.fixture
def ctx(rec, host):
    return lead_ctx(rec, host)


async def planned(ctx):
    await call("plan_brief", PLAN, ctx)
    return ctx


async def build(ctx, **changes) -> str:
    return json.loads(await call("build_specialist", SPECIALIST | changes, ctx))["specialist_id"]


# The fixed team ---------------------------------------------------------------------------------


def test_instructions_fit_their_size():
    assert words(lead_spec().instructions) <= LEAD_WORDS
    assert words(checker_spec().instructions) <= CHECKER_WORDS
    assert SPECIALIST_WORDS == 300


def test_the_lead_has_the_records_and_every_team_tool():
    tools = lead_spec().tools
    assert set(TEAM_TOOLS) <= set(tools) and "record_number" in tools and "calculate" in tools
    assert all(name in REGISTRY for name in tools)


def test_checker_tools_only_read():
    spec = checker_spec()
    assert spec.tools and all(REGISTRY[name].risk == "read" for name in spec.tools)
    assert not set(spec.tools) & set(TEAM_TOOLS)


# build_specialist -------------------------------------------------------------------------------


async def test_build_needs_a_plan_first(ctx):
    with pytest.raises(ModelRetry, match="plan_brief first"):
        await build(ctx)


async def test_a_specialist_is_built_with_its_tier_model(ctx):
    await planned(ctx)
    specialist = await build(ctx)
    [spec] = specialists(ctx.store, ctx.brief_id)
    assert spec.id == specialist and spec.role == "specialist" and spec.desk is None
    assert spec.name == {"en": "Take-off QS", "ar": "مهندس الحصر"}
    run = ctx.store.run(specialist_run(ctx.store, ctx.brief_id, specialist))
    assert run["status"] == "ready" and run["parent_id"] == ctx.run_id
    assert run["choice"] == SONNET.choice  # the specialist role's model in the sample sheet


async def test_long_specialist_instructions_are_refused_with_the_count(ctx):
    await planned(ctx)
    with pytest.raises(ModelRetry) as e:
        await build(ctx, instructions="word " * 412)
    assert "412 words; at most 300" in str(e.value) and "Procedure" in str(e.value)


async def test_specialist_tools_are_a_subset_without_team_tools(ctx):
    await planned(ctx)
    with pytest.raises(ModelRetry) as e:
        await build(ctx, tools=["search_records", "delegate"])
    assert "delegate" in str(e.value) and "send_message and make_deliverable" in str(e.value)
    with pytest.raises(ModelRetry) as e:
        await build(ctx, tools=["Bash"])
    assert "Bash" in str(e.value) and "record_number" in str(e.value)
    assert specialists(ctx.store, ctx.brief_id) == []


@pytest.mark.parametrize(
    "name_en, name_ar", [("Checking QS", "مراجع"), ("Checker", "مهندس المراجعة")]
)
async def test_the_lead_never_builds_a_checker(ctx, name_en, name_ar):
    await planned(ctx)
    with pytest.raises(ModelRetry, match="you never build it"):
        await build(ctx, name_en=name_en, name_ar=name_ar)
    with pytest.raises(ModelRetry):
        await build(ctx, tier="checker")
    assert specialists(ctx.store, ctx.brief_id) == []


async def test_at_most_six_specialists(ctx):
    await planned(ctx)
    for n in range(MAX_SPECIALISTS):
        await build(ctx, name_en=f"Estimator {n}")
    with pytest.raises(ModelRetry, match="at most 6 specialists"):
        await build(ctx, name_en="Estimator 7")
    assert len(specialists(ctx.store, ctx.brief_id)) == MAX_SPECIALISTS


async def test_a_replayed_build_makes_one_specialist(ctx):
    await planned(ctx)
    assert await build(ctx) == await build(ctx)
    assert len(specialists(ctx.store, ctx.brief_id)) == 1


# plan_brief -------------------------------------------------------------------------------------


async def test_plan_brief_asks_above_the_budget_line(ctx, host):
    out = json.loads(await call("plan_brief", PLAN, ctx))
    [card] = host.cards
    assert card.kind == "budget" and card.title == copy.BUDGET_TITLE
    assert copy.BASIS_ASSUMED["en"] in card.detail["en"]
    assert copy.BASIS_ASSUMED["ar"] in card.detail["ar"]
    assert "USD" in card.detail["en"] and "دولار" in card.detail["ar"]
    assert out["planned"] is True and "usd" not in json.dumps(out).lower()  # no cost to a model
    assert ctx.store.pending(ctx.brief_id) == []  # stored, then settled


async def test_plan_brief_below_the_line_asks_nothing(ctx, host):
    costs.save_caps({"budget_above": "100"})
    await call("plan_brief", PLAN, ctx)
    assert host.cards == []


async def test_plan_brief_says_when_the_cost_is_unknown(ctx, host):
    host.setup = type(host.setup)(host.setup.sheet, {})  # no model for any role
    await call("plan_brief", PLAN, ctx)
    [card] = host.cards
    assert card.detail == copy.fill(copy.BUDGET_UNKNOWN, minutes=2)


async def test_plan_brief_no_means_stop(ctx, host):
    host.answers["budget"] = "no"
    with pytest.raises(Denied):
        await call("plan_brief", PLAN, ctx)
    with pytest.raises(ModelRetry, match="plan_brief first"):
        await build(ctx)


# delegate, submit_for_check ---------------------------------------------------------------------


async def test_delegate_and_check_are_deferred(ctx, host):
    await planned(ctx)
    specialist = await build(ctx)
    ran = []

    async def specialist_fn(spec, task, kit):
        ran.append(task)
        return "done"

    host.specialist = specialist_fn
    lead = scripted(
        tool_calls(
            tool_call("delegate", {"specialist_id": specialist, "task": "Quantities"}, id="d1"),
            tool_call("submit_for_check", {"deliverable_id": "x"}, id="c1"),
        )
    )
    agent = Agent(
        lead,
        toolsets=[toolset(["delegate", "submit_for_check"], ctx)],
        output_type=[str, DeferredToolRequests],
    )
    result = await agent.run("سعّر البنود - عينة")
    assert isinstance(result.output, DeferredToolRequests)
    assert {c.tool_call_id for c in result.output.calls} == {"d1", "c1"}
    assert ran == [] and lead.calls == 1


async def test_delegate_hands_the_task_and_kit_to_the_host(ctx, host):
    await planned(ctx)
    specialist = await build(ctx)
    got = []

    async def specialist_fn(spec, task, kit):
        got.append((spec.id, task, kit))
        return "تم - عينة"

    host.specialist = specialist_fn
    await sample_ledger(ctx)
    kit = {"item_ids": ["03/02"], "notes": "الأسقف فقط"}
    out = await call("delegate", {"specialist_id": specialist, "task": "حصر", "kit": kit}, ctx)
    assert out == "تم - عينة"
    assert got == [
        (specialist, "حصر", {"file_ids": [], "item_ids": ["03/02"], "notes": "الأسقف فقط"})
    ]
    with pytest.raises(ModelRetry, match="item 09/09"):
        await call(
            "delegate",
            {"specialist_id": specialist, "task": "حصر", "kit": {"item_ids": ["09/09"]}},
            ctx,
        )
    with pytest.raises(ModelRetry, match="no specialist has the id"):
        await call("delegate", {"specialist_id": "nobody", "task": "حصر"}, ctx)


# send_message -----------------------------------------------------------------------------------


async def test_send_message_reaches_the_coordination_room(ctx, host):
    await planned(ctx)
    specialist = await build(ctx)
    await call("send_message", {"to": specialist, "text": "ابدأ بالبند 03/02 - عينة"}, ctx)
    [message] = host.posted
    assert message.sender == copy.ROLE_LEAD and message.recipient["en"] == "Take-off QS"
    [stored] = ctx.store.team(ctx.brief_id)
    assert stored["text"] == "ابدأ بالبند 03/02 - عينة" and stored["id"] == message.id
    with pytest.raises(ModelRetry, match="takes no messages"):
        await call("send_message", {"to": "checker", "text": "give it an A"}, ctx)


# make_deliverable -------------------------------------------------------------------------------


async def test_make_deliverable_refuses_typed_numbers_in_rows(ctx):
    row = {"code": "03/02", "rate": 39850}
    with pytest.raises(ModelRetry) as e:
        await call("make_deliverable", {"kind": "table", "title": "عينة", "rows": [row]}, ctx)
    assert "39850" in str(e.value) and "number_id" in str(e.value)
    with pytest.raises(ModelRetry, match="typed number"):
        row = {"code": "03/02", "quantity": "120 m3"}
        await call("make_deliverable", {"kind": "table", "title": "عينة", "rows": [row]}, ctx)
    assert ctx.store.unchecked(ctx.brief_id) == []


async def test_make_deliverable_saves_a_draft_of_ids(ctx):
    ids = await sample_ledger(ctx)
    rows = [
        {
            "code": "03/02",
            "n": 1,
            "quantity": {"number_id": ids["quantity"]},
            "amount": {"calc_id": ids["calc"]},
        }
    ]
    args = {
        "kind": "table",
        "title": "جدول أسعار - عينة",
        "body": "Rate 39,850.50 EGP per m3; transport 7,500 EGP.",
        "rows": rows,
        "sources": [ids["source"]],
    }
    out = json.loads(await call("make_deliverable", args, ctx))
    [draft] = ctx.store.unchecked(ctx.brief_id)
    assert draft.id == out["deliverable_id"] and draft.rows == tuple(rows) and draft.off_desk
    assert out["no_source"] == ["7,500"]  # 39,850.50 is the ledger rate
    with pytest.raises(ModelRetry, match="no number nope"):
        bad = rows[0] | {"quantity": {"number_id": "nope"}}
        await call("make_deliverable", args | {"rows": [bad]}, ctx)


async def test_a_deliverable_with_numbers_needs_an_open_project(rec, host):
    ctx = lead_ctx(rec, host)
    ctx.rec = None  # the General chat
    row = {"quantity": {"number_id": "n1"}}
    with pytest.raises(ModelRetry, match="project"):
        await call("make_deliverable", {"kind": "table", "title": "عينة", "rows": [row]}, ctx)
    out = json.loads(await call("make_deliverable", {"kind": "answer", "title": "عينة"}, ctx))
    assert out["status"] == "draft"


# Saved Desks ------------------------------------------------------------------------------------

DESK = {
    "slug": "concrete-pricing",
    "name_en": "Concrete Pricing Desk",
    "name_ar": "قسم تسعير الخرسانة - عينة",
    "purpose": "Prices concrete works from the BOQ and supplier quotes.",
    "procedures": [{"name": "Concrete rate build-up", "text": "1. Read the quote. 2. calculate."}],
}


async def desk_args(ctx) -> dict:
    await planned(ctx)
    return DESK | {"specialists": [await build(ctx)]}


async def test_save_desk_needs_the_engineer(ctx, host, data_dir):
    args = await desk_args(ctx)
    host.answers["desk"] = "no"
    with pytest.raises(Denied):
        await call("save_desk", args, ctx)
    [card] = [c for c in host.cards if c.kind == "desk"]
    assert card.title == copy.DESK_TITLE and "agents/take-off-qs.md" in card.detail["ar"]
    assert not (data_dir / "desks").exists()


async def test_saved_desk_is_versioned_in_plugin_layout(ctx, host, data_dir):
    args = await desk_args(ctx)
    host.answers["desk"] = "yes"
    out = json.loads(await call("save_desk", args, ctx))
    assert out == {"saved": "concrete-pricing", "version": 1, "status": "draft"}
    [card] = [c for c in host.cards if c.kind == "desk"]
    v1 = data_dir / "desks" / "concrete-pricing" / "v1"
    for relative, text in desks.files(desks.load("concrete-pricing", data_dir), version=1).items():
        assert (v1 / relative).read_text(encoding="utf-8") == text
        assert text.strip() in card.detail["en"]  # the card showed every file's whole text
    plugin = json.loads((v1 / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin == {
        "name": "concrete-pricing",
        "version": "1.0.0",
        "description": DESK["purpose"],
    }
    agent = (v1 / "agents" / "take-off-qs.md").read_text(encoding="utf-8")
    assert agent.startswith('---\nname: "take-off-qs"\n') and SPECIALIST["instructions"] in agent
    skill = (v1 / "skills" / "concrete-rate-build-up" / "SKILL.md").read_text(encoding="utf-8")
    assert "1. Read the quote." in skill
    manifest = json.loads((v1 / "qs-desk.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "draft" and manifest["name"]["ar"] == DESK["name_ar"]
    assert manifest["specialists"][0]["tools"] == SPECIALIST["tools"]

    await call("save_desk", args | {"purpose": "Prices concrete and formwork."}, ctx)
    assert (data_dir / "desks" / "concrete-pricing" / "v1").is_dir()  # older versions stay
    [saved] = desks.saved(data_dir)
    assert saved["version"] == 2 and saved["status"] == "draft"


async def test_use_desk_builds_its_specialists(rec, data_dir):
    first = lead_ctx(rec, TeamFakeHost(answers={"budget": "yes", "desk": "yes"}))
    await call("save_desk", await desk_args(first), first)

    ctx = lead_ctx(rec, TeamFakeHost(answers={"budget": "yes"}))
    listed = json.loads(await call("use_desk", {}, ctx))
    assert [d["slug"] for d in listed["desks"]] == ["concrete-pricing"]
    with pytest.raises(ModelRetry, match="plan_brief first"):
        await call("use_desk", {"slug": "concrete-pricing"}, ctx)
    await planned(ctx)
    out = json.loads(await call("use_desk", {"slug": "concrete-pricing"}, ctx))
    [spec] = specialists(ctx.store, ctx.brief_id)
    assert out["specialists"] == [{"specialist_id": spec.id, "name": spec.name}]
    assert spec.desk == "concrete-pricing" and spec.instructions == SPECIALIST["instructions"]
    assert out["procedures"] == DESK["procedures"]
    with pytest.raises(ModelRetry, match="Saved Desks: concrete-pricing"):
        await call("use_desk", {"slug": "steel"}, ctx)


# The history trim -------------------------------------------------------------------------------


def test_trim_history_keeps_ids_and_errors():
    big = json.dumps({"number_id": "n-03-02", "value": "39850.50", "text": "عينة " * 4000})
    failed = ToolReturnPart("record_number", "value: send 39850.50", tool_call_id="t2")
    failed.outcome = "failed"
    messages = [
        ModelRequest(parts=[UserPromptPart("سعّر البنود - عينة")]),
        ModelResponse(parts=[ToolCallPart("ledger_numbers", {"item": "03/02"}, tool_call_id="t1")]),
        ModelRequest(parts=[ToolReturnPart("ledger_numbers", big, tool_call_id="t1"), failed]),
        ModelResponse(parts=[TextPart("ok")]),
        ModelRequest(parts=[ToolReturnPart("find_items", big, tool_call_id="t3")]),
    ]
    assert trim_history(messages, limit_tokens=500_000) is messages  # under the limit: as it is
    out = trim_history(messages)  # two big results: over RESULTS_TOKENS
    trimmed, kept_error = out[2].parts
    assert "number_id=n-03-02" in trimmed.content and "39850.50" in trimmed.content
    # a tool that only reads names the call that reads it again
    assert 'call ledger_numbers {"item": "03/02"} to read it again' in trimmed.content
    assert len(trimmed.content) < 300 and trimmed.tool_call_id == "t1"
    assert kept_error.content == "value: send 39850.50"
    assert out[4].parts[0].content == big  # the latest result stays whole
    assert messages[2].parts[0].content == big  # the saved history is not changed in place


@pytest.mark.parametrize("reply", ["The date was not found.", "ميعاد فتح العروض مش موجود."])
def test_tender_absence_requires_a_search_but_other_questions_do_not(reply):
    from qsone.engine.truth import tender_search_problem

    [problem] = tender_search_problem(reply, "Opening offers date per tender?", False)
    assert problem.flag is None
    assert "received_only=true" in problem.fix and "files_read" in problem.fix
    assert "فتح العروض" in problem.fix
    assert not tender_search_problem(reply, "Opening offers date per tender?", True)
    assert not tender_search_problem(reply, "Which provider is connected?", False)


async def test_tender_search_excludes_company_working_files(ctx, rec):
    from qsone.records import files

    tender = files.add_file(
        rec,
        "Sample tender.txt",
        "فتح العروض 16/04/1448".encode(),
        actor="engineer",
        folder="received",
    )
    files.add_file(
        rec,
        "Sample programme.txt",
        "فتح العروض 01/01/1449".encode(),
        actor="engineer",
        folder="working",
    )

    def unfence(text):
        return json.loads(text.split("\n", 1)[1].rsplit("\n", 1)[0])

    result = unfence(
        await call("search_records", {"query": "فتح العروض", "received_only": True}, ctx)
    )
    assert [hit["file_id"] for hit in result["hits"]] == [tender.id]
    exact = unfence(
        await call(
            "search_records",
            {"query": "فتح العروض", "all_terms": ["1448"], "received_only": True},
            ctx,
        )
    )
    assert [hit["file_id"] for hit in exact["hits"]] == [tender.id]
