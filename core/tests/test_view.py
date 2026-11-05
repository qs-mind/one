"""Generative UI, first step (decision 16.1): the Lead QS shows a `View` built only from ONE's
blocks, through the `show` tool. Each number is a reference the core resolves to its value,
source and date; words go through the numbers guard; a bad view gets one retry, then the reply
stays plain text; a reload shows the same view.

Scripted models only; no real AI. Synthetic «عينة» data only."""

import json
import re

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
    for kind in ("heading", "prose", "figures", "table"):
        assert f'"{kind}"' in schema
    for kind in ("group", "chart", "ask", "open"):
        assert f'"{kind}"' not in schema
    recipe, example = tool.description.rsplit("\nExample:\n", 1)
    assert tool.example == json.loads(example) and len(tool.description.split()) <= 120
    view.View.model_validate(tool.example)


def test_a_table_row_has_one_fixed_shape_a_small_model_can_fill():
    """The first bake-off (5 Nov 2026): free-form row keys and text-or-reference cells broke
    Gemini's function calls. A row is now {label, texts, numbers}: no free key, no cell that may
    be words or a reference, no column type; a value's place decides what it is."""
    defs = view.View.model_json_schema()["$defs"]
    row = defs["Row"]
    assert set(row["properties"]) == {"label", "texts", "numbers"}
    assert row["additionalProperties"] is False and "propertyNames" not in json.dumps(defs)
    texts = row["properties"]["texts"]["items"]
    assert texts["type"] == "string" and "anyOf" not in texts
    refs = [r["$ref"] for r in row["properties"]["numbers"]["items"]["anyOf"]]
    assert refs == ["#/$defs/NumberRef", "#/$defs/CellRef"]  # objects only, as a figure's value
    assert set(defs["Column"]["properties"]) == {"label"}
    for block in ("Heading", "Prose", "Figures", "Table"):  # one level: a section title, no group
        assert "section" in defs[block]["properties"]


def test_the_tool_text_and_the_leads_name_no_language():
    """The bake-off: a language named in the instructions pulled English requests into Arabic.
    The words follow the engineer's language, whatever it is."""
    recipe = REGISTRY["show"].description.rsplit("\nExample:\n", 1)[0]
    lead, general_lead = agents.lead_spec().instructions, general.lead_spec().instructions
    for text in (recipe, lead, general_lead):
        assert not re.search(r"arabic|english|egyptian|عربي|إنجليزي", text, re.IGNORECASE)
    assert "engineer's language" in recipe and "engineer's language" in lead


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


def table(*rows: dict, columns=("الوصف", "الفئة"), label_header="البند") -> dict:
    return {
        "kind": "table",
        "label_header": label_header,
        "columns": [{"label": c} for c in columns],
        "rows": list(rows),
    }


async def test_a_table_row_is_its_label_then_its_texts_then_its_numbers(ledger):
    ctx, host, ids = ledger
    row = {"label": "03/02 - عينة", "texts": ["خرسانة مسلحة"], "numbers": [{"number": ids["rate"]}]}
    await show(ctx, blocks=[table(row)])
    [shown] = views(host)
    [out] = shown.data["blocks"][0]["rows"]
    assert out["label"] == "03/02 - عينة" and out["texts"] == ["خرسانة مسلحة"]
    assert out["numbers"][0]["value"] == "39850.50" and out["numbers"][0]["currency"] == "EGP"
    assert shown.data["blocks"][0]["label_header"] == "البند"
    assert [c["label"] for c in shown.data["blocks"][0]["columns"]] == ["الوصف", "الفئة"]

    host.events.clear()  # texts and numbers may be left out: a table of labels only
    await show(ctx, blocks=[table({"label": "بند - عينة"}, columns=())])
    [labels] = views(host)
    assert labels.data["blocks"][0]["rows"] == [{"label": "بند - عينة", "texts": [], "numbers": []}]


async def test_a_typed_number_in_a_table_is_refused_with_its_place(ledger):
    ctx, host, _ = ledger
    row = {"label": "03/02", "texts": ["خرسانة"], "numbers": ["12"]}
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "heading", "text": "عنوان"}, table(row)])
    assert "blocks[1].rows[0].numbers[0]" in str(refused.value)
    assert '{"number": "<number id>"}' in str(refused.value) and views(host) == []


async def test_every_row_fits_the_columns(ledger):
    ctx, host, ids = ledger
    ref = {"number": ids["rate"]}
    good = {"label": "03/01", "texts": ["خرسانة"], "numbers": [ref]}
    short = {"label": "03/02", "texts": [], "numbers": [ref]}  # one cell short of the columns
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[table(good, short)])
    message = str(refused.value)
    assert "blocks[0].rows[1]" in message and "2 columns" in message and views(host) == []
    # rows that agree with each other but not with the columns; the one retry is used, so words
    out = await show(ctx, blocks=[table(good, good, columns=("الفئة",))])
    assert out["shown"] is None and "1 column" in out["note"] and "label_header" in out["note"]


async def test_the_label_columns_header_is_its_own_field(ledger):
    """Round 2 of the bake-off: 4 of 20 views counted the label's header among the columns.
    The label's header is `label_header`; the columns head only the texts and the numbers."""
    defs = view.View.model_json_schema()["$defs"]
    # both required: round 3's function calls left out columns that had a default
    assert {"label_header", "columns"} <= set(defs["Table"]["required"])
    ctx, host, ids = ledger
    row = {"label": "03/02", "texts": ["خرسانة"], "numbers": [{"number": ids["rate"]}]}
    with pytest.raises(ModelRetry) as refused:  # the label's header among the columns, as before
        await show(ctx, blocks=[table(row, columns=("البند", "الوصف", "الفئة"))])
    message = str(refused.value)
    assert "1 text and 1 number" in message and "3 columns" in message
    assert "label_header" in message


async def test_an_id_in_words_is_refused(ledger):
    """An id in a text shows as hex on screen (bake-off 1, p20): a number goes by reference."""
    ctx, host, ids = ledger
    prose = f"الفئة هي {ids['rate']} من عرض السعر."
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "prose", "text": prose}])
    assert "blocks[0].text" in str(refused.value) and "id" in str(refused.value)
    assert views(host) == []


@pytest.mark.parametrize(
    "words",
    [
        "The difference is one hundred and forty EGP per ton.",
        "زيادة الكمية بنسبة عشرة بالمئة",
        "حوالي ألفين جنيه للطن",
        "about two thousand tonnes",
    ],
)
async def test_a_number_written_in_words_is_refused(ledger, words):
    """Round 3: told never to type a number, the model wrote a computed one in words (p11:
    "one hundred and forty EGP"), which the numbers guard cannot see."""
    ctx, host, _ = ledger
    with pytest.raises(ModelRetry) as refused:
        await show(ctx, blocks=[{"kind": "prose", "text": words}])
    assert "blocks[0].text" in str(refused.value) and "in words" in str(refused.value)
    assert views(host) == []


async def test_a_count_in_words_is_not_a_number_in_words(ledger):
    ctx, host, _ = ledger
    words = "The three quotes, and the two cheapest of them. أعلى خمسة بنود والعروض الثلاثة."
    await show(ctx, blocks=[{"kind": "prose", "text": words}])
    assert len(views(host)) == 1


def test_the_tool_text_says_no_number_in_words_and_no_id_in_text():
    recipe = REGISTRY["show"].description.rsplit("\nExample:\n", 1)[0]
    assert "never written in words" in recipe and "never put an id in" in recipe
    assert "label_header" in recipe


def test_the_example_is_in_no_language():
    """Round 2: the example's Arabic words pulled 7 of 10 English requests into Arabic."""
    words = json.dumps(REGISTRY["show"].example, ensure_ascii=False)
    assert not re.search(r"[؀-ۿ]", words)
    assert not re.search(r'"(?:title|label|label_header|section|text)": "[A-Za-z]', words)


async def test_a_view_stored_before_label_header_still_shows(rec):
    """A table stored before round 3 has the label's header as its first column."""
    data = {
        "title": "ملخص - عينة",
        "blocks": [
            {
                "kind": "table",
                "columns": [{"label": "البند"}, {"label": "الوصف"}],
                "rows": [{"label": "03/02", "texts": ["خرسانة"], "numbers": []}],
            }
        ],
    }
    built, _, _ = view._build(rec, data, rec.clock(), stored=True)
    assert built["blocks"][0]["label_header"] == "البند"
    assert built["blocks"][0]["columns"] == [{"label": "الوصف"}]


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
        {"kind": "group", "title": "مجموعة", "blocks": [{"kind": "prose", "text": "x"}]},
    ]
    out = await show(ctx, blocks=blocks)
    [shown] = views(host)
    assert [b["kind"] for b in shown.data["blocks"]] == ["prose"]
    assert len(out["dropped"]) == 2
    assert "chart" in out["dropped"][0] and "blocks[0]" in out["dropped"][0]
    assert "group" in out["dropped"][1] and "section" in out["dropped"][1]  # a group is a section


async def test_a_section_title_puts_blocks_together_and_goes_through_the_guard(ledger):
    ctx, host, ids = ledger
    section = "الفئة 777 - عينة"
    blocks = [
        {"kind": "heading", "text": "عنوان - عينة"},
        figures({"number": ids["rate"]}) | {"section": section},
        {"kind": "prose", "text": "نص - عينة", "section": section},
    ]
    out = await show(ctx, blocks=blocks)
    [shown] = views(host)
    assert [b["section"] for b in shown.data["blocks"]] == [None, section, section]
    assert out["unsourced"] == ["777"]


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
