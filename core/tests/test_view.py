"""Generative UI, first step (decision 16.1): the Lead QS shows a `View` built only from ONE's
blocks, through the `show` tool. Each number is a reference the core resolves to its value,
source and date; words go through the numbers guard; a bad view gets one retry, then the reply
stays plain text; a reload shows the same view.

Scripted models only; no real AI. Synthetic «عينة» data only."""

import json

import pytest
from pydantic_ai import ModelRetry

from qsone import view
from qsone.engine import agents, general
from qsone.engine.tools import REGISTRY, call
from qsone.engine.types import Data
from tests.engine_fakes import call as step
from tests.engine_fakes import calls, scripted
from tests.engine_fakes import text as said
from tests.samples import sample_sheet
from tests.team_samples import BRIEF, DATED, TeamFakeHost, lead_ctx, quote_source, sample_ledger
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)

MISSING = "0" * 32


@pytest.fixture
async def ledger(rec):
    host = TeamFakeHost()
    ctx = lead_ctx(rec, host)
    ids = await sample_ledger(ctx)
    return ctx, host, ids


def views(host) -> list[Data]:
    return [e for e in host.events if isinstance(e, Data) and e.name == "view"]


def figures(*refs: dict) -> dict:
    return {
        "kind": "figures",
        "items": [{"label": f"رقم {i} - عينة", "value": r} for i, r in enumerate(refs, 1)],
    }


async def show(ctx, **args) -> dict:
    return json.loads(await call("show", {"title": "ملخص - عينة", **args}, ctx))


# The schema -----------------------------------------------------------------------------------


def test_the_tool_schema_comes_from_the_view_model():
    tool = REGISTRY["show"]
    assert tool.args.model_json_schema() == view.View.model_json_schema()
    assert tool.roles == frozenset({"lead"}) and tool.risk == "read"
    schema = json.dumps(view.View.model_json_schema())
    for kind in ("heading", "prose", "figures", "table", "group"):
        assert f'"{kind}"' in schema
    assert '"chart"' not in schema and '"ask"' not in schema and '"open"' not in schema
    recipe, example = tool.description.rsplit("\nExample:\n", 1)
    assert tool.example == json.loads(example) and len(tool.description.split()) <= 120
    view.View.model_validate(tool.example)


def test_the_project_lead_has_show_and_the_general_chat_lead_has_not():
    assert "show" in agents.lead_spec().tools
    assert "show" not in general.lead_spec().tools


# References -----------------------------------------------------------------------------------


async def test_each_number_is_resolved_to_its_value_source_and_date(ledger):
    ctx, host, ids = ledger
    out = await show(ctx, blocks=[figures({"number": ids["rate"]}, {"number": ids["amount"]})])
    [shown] = views(host)
    assert out["shown"] == shown.id and shown.brief_id == ctx.brief_id
    data = shown.data
    [rate, amount] = [i["value"] for i in data["blocks"][0]["items"]]
    assert rate["value"] == "39850.50" and rate["currency"] == "EGP" and rate["dated"] == DATED
    assert rate["number_id"] == ids["rate"] and data["sources"][rate["source"]]["kind"] == "quote"
    assert amount["value"] == ids["amount_value"] and amount["calculated"] is True
    assert data["sample"] is False and data["unsourced"] == []


async def test_an_unknown_number_is_refused_with_its_place(ledger):
    ctx, host, _ = ledger
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "heading", "text": "عنوان"}, figures({"number": MISSING})])
    assert MISSING in str(refused.value) and "blocks[1].items[0].value" in str(refused.value)
    assert views(host) == []


async def test_a_typed_number_in_a_figure_is_refused(ledger):
    ctx, host, _ = ledger
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "figures", "items": [{"label": "سعر", "value": "39850"}]}])
    assert "number" in str(refused.value) and views(host) == []


async def test_a_sheet_cell_resolves_and_a_cell_with_no_number_is_refused(rec):
    host = TeamFakeHost()
    ctx = lead_ctx(rec, host)
    sheet = sample_sheet(rec)
    total = {"deliverable": sheet, "row": "total", "column": "amount"}
    await show(ctx, blocks=[figures(total)])
    [shown] = views(host)
    cell = shown.data["blocks"][0]["items"][0]["value"]
    assert cell["number_id"] and cell["source"] in shown.data["sources"]
    assert shown.data["sample"] is True  # the sample sheet's numbers come from a sample source

    host.events.clear()
    text_cell = {"deliverable": sheet, "row": "total", "column": "description"}
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[figures(text_cell)])
    assert "no number" in str(refused.value) and views(host) == []


async def test_a_table_takes_references_in_number_columns_and_words_in_text_columns(ledger):
    ctx, host, ids = ledger
    columns = [
        {"key": "item", "label": "البند", "type": "text"},
        {"key": "rate", "label": "الفئة", "type": "number"},
    ]
    rows = [{"item": "03/02 - عينة", "rate": {"number": ids["rate"]}}]
    await show(ctx, blocks=[{"kind": "table", "columns": columns, "rows": rows}])
    [shown] = views(host)
    [row] = shown.data["blocks"][0]["rows"]
    assert row["item"] == "03/02 - عينة" and row["rate"]["value"] == "39850.50"

    with pytest.raises(ModelRetry) as refused:  # a typed number in a number column
        await show(ctx, blocks=[{"kind": "table", "columns": columns, "rows": [{"rate": "12"}]}])
    assert "blocks[0].rows[0].rate" in str(refused.value)
    # a column it does not have; the Brief's one retry is used, so it answers in words
    out = await show(ctx, blocks=[{"kind": "table", "columns": columns, "rows": [{"qty": "1"}]}])
    assert out["shown"] is None and "qty" in out["note"]


# Words ----------------------------------------------------------------------------------------


async def test_prose_goes_through_the_numbers_guard(ledger):
    ctx, host, ids = ledger
    prose = "الفئة 39,850.50 جنيه من عرض السعر، والكمية 777 م3 من غير مصدر."
    blocks = [figures({"number": ids["rate"]}), {"kind": "prose", "text": prose}]
    out = await show(ctx, blocks=blocks, title="ملخص 2026 - عينة")
    [shown] = views(host)
    assert shown.data["unsourced"] == ["777"] and out["unsourced"] == ["777"]
    assert shown.data["blocks"][1]["text"] == prose  # marked on screen, never removed


async def test_html_from_the_model_is_refused(ledger):
    ctx, host, _ = ledger
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "prose", "text": "<script>alert(1)</script>"}])
    assert "HTML" in str(refused.value) and views(host) == []


# The sample label -----------------------------------------------------------------------------


async def test_the_sample_label_is_kept_and_never_dropped_for_sample_numbers(ledger, rec):
    ctx, host, ids = ledger
    await show(ctx, sample=True, blocks=[{"kind": "prose", "text": "نص تجريبي"}])
    await show(ctx, sample=False, blocks=[figures({"number": ids["rate"]})])
    sheet = sample_sheet(rec)
    total = {"deliverable": sheet, "row": "total", "column": "amount"}
    await show(ctx, sample=False, blocks=[figures(total)])
    assert [v.data["sample"] for v in views(host)] == [True, False, True]


# Failing safely -------------------------------------------------------------------------------


async def test_a_bad_view_gets_one_retry_then_the_reply_stays_plain_text(ledger):
    ctx, host, _ = ledger
    with pytest.raises(ModelRetry) as first:
        await call("show", {"blocks": []}, ctx)  # no title, no blocks
    assert "title" in str(first.value)
    for _ in range(3):  # never another retry in this Brief, so the Brief never fails on show
        out = json.loads(await call("show", {"blocks": []}, ctx))
        assert out["shown"] is None and "words" in out["note"]
    assert views(host) == []


async def test_an_unknown_block_kind_is_dropped_with_a_note(ledger):
    ctx, host, _ = ledger
    blocks = [
        {"kind": "chart", "type": "bar"},
        {"kind": "prose", "text": "نص - عينة"},
        {"kind": "group", "title": "مجموعة", "blocks": [{"kind": "ask", "label": "x"}]},
    ]
    out = await show(ctx, blocks=blocks)
    [shown] = views(host)
    assert [b["kind"] for b in shown.data["blocks"]] == ["prose"]  # an emptied group goes too
    assert len(out["dropped"]) == 2
    assert "chart" in out["dropped"][0] and "blocks[0]" in out["dropped"][0]
    assert "ask" in out["dropped"][1] and "blocks[2].blocks[0]" in out["dropped"][1]


async def test_a_group_holds_one_level_only(ledger):
    ctx, host, _ = ledger
    inner = {"kind": "group", "title": None, "blocks": [{"kind": "prose", "text": "نص"}]}
    outer = {"kind": "group", "title": "خارج", "blocks": [inner, {"kind": "prose", "text": "نص"}]}
    blocks = [outer]
    out = await show(ctx, blocks=blocks)
    [shown] = views(host)
    assert [b["kind"] for b in shown.data["blocks"][0]["blocks"]] == ["prose"]
    assert "group" in out["dropped"][0]


# In a Brief, and after a reload ---------------------------------------------------------------


def _number_id(messages) -> str:
    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, ToolReturnPart) and p.tool_name == "record_number":
                    return json.loads(p.content)["number_id"]
    raise AssertionError("no number recorded")


def _ledger_steps(registry, project):  # noqa: F811
    source = quote_source(registry.get(project))
    number = {"item": "03/02", "dated": DATED, "name": "rate", "value": "39850.50"}

    def record(messages, info):
        from pydantic_ai.messages import ModelRequest, ToolReturnPart

        source_id = next(
            json.loads(p.content)["source_id"]
            for m in messages
            if isinstance(m, ModelRequest)
            for p in m.parts
            if isinstance(p, ToolReturnPart) and p.tool_name == "add_source"
        )
        args = number | {"source_id": source_id, "unit": "m3", "currency": "EGP"}
        return step("record_number", args)

    return [
        calls(step("add_source", source), step("add_item", {"kind": "boq_item", "code": "03/02"})),
        record,
    ]


def _show_step(messages, info):
    blocks = [
        {"kind": "heading", "text": "الفئة - عينة"},
        figures({"number": _number_id(messages)}),
        {"kind": "prose", "text": "فئة الخرسانة من عرض السعر، والكمية 777 م3."},
    ]
    return step("show", {"title": "ملخص - عينة", "blocks": blocks})


async def test_a_view_streams_and_a_reload_shows_the_same_view(make_engine, registry, project):  # noqa: F811, E501
    lead = scripted(*_ledger_steps(registry, project), _show_step, said("دي الفئة - عينة"))
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    [live] = [e for e in events if isinstance(e, Data) and e.name == "view"]
    assert live.data["unsourced"] == ["777"]
    engine._briefs.pop(brief, None)  # read from the store, as after a restart
    reply = engine.chat_messages(project)[-1]
    stored = [p for p in reply["parts"] if p["type"] == "data-view"]
    assert stored == [{"type": "data-view", "id": live.id, "data": live.data}]


async def test_a_brief_whose_view_fails_twice_ends_in_plain_words(make_engine, project):  # noqa: F811
    lead = scripted(
        step("show", {"blocks": []}), step("show", {"title": "x"}), said("الرد بالكلام - عينة")
    )
    engine = await started(make_engine(links(lead=lead)))
    brief = await engine.start_brief(project, BRIEF)
    events = await finish(engine, brief)
    assert not [e for e in events if isinstance(e, Data) and e.name == "view"]
    assert engine.chat_messages(project)[-1]["parts"][0]["text"] == "الرد بالكلام - عينة"
    engine._briefs.pop(brief, None)
    parts = engine.chat_messages(project)[-1]["parts"]
    assert not [p for p in parts if p["type"] == "data-view"]
