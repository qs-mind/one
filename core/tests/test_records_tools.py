"""The records tools (Plan 5, Task 7): every source points at real evidence, Engineer Records
writes ask first, personal data is kept only when the engineer said so, and lessons.

Scripted hosts only; synthetic «عينة» data only; no test reaches the web or a real AI."""

import json
from datetime import datetime
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry

from qsone import copy
from qsone.engine import agents, tools_records
from qsone.engine.general import open_engineer_records
from qsone.engine.tools import REGISTRY, call
from qsone.engine.types import Card, answer_value
from qsone.records import keep
from qsone.records.files import add_file
from qsone.tools import engineer, lessons  # noqa: F401 - registers ask_engineer and note_lesson
from tests.fakes_tools import fake_services, tool_ctx
from tests.samples import sample_pdf, sample_xlsx

DATED = "2026-11-02"


@pytest.fixture
def eng(data_dir):
    records = open_engineer_records(data_dir)
    yield records
    records.close()


@pytest.fixture
def ctx(rec, eng):
    return tool_ctx(rec, services=fake_services(engineer=lambda: eng))


def ids(out: str) -> dict:
    return json.loads(out)


def sources(records) -> list[dict]:
    with records.read() as c:
        rows = c.execute(
            "SELECT kind, title, file_id, locator, url, dated FROM sources ORDER BY rowid"
        ).fetchall()
    return [
        {"kind": k, "title": t, "file_id": f, "locator": json.loads(lc), "url": u, "dated": d}
        for k, t, f, lc, u, d in rows
    ]


def items(records, kind: str | None = None) -> list[dict]:
    with records.read() as c:
        rows = c.execute("SELECT kind, code, fields FROM items ORDER BY rowid").fetchall()
    found = [{"kind": k, "code": code, "fields": json.loads(f)} for k, code, f in rows]
    return [i for i in found if kind is None or i["kind"] == kind]


def local_day(stamp: str) -> str:
    return datetime.fromisoformat(stamp).astimezone().date().isoformat()


def spec_file(records) -> str:
    pdf = sample_pdf([["concrete C30 - sample"], ["rebar B500 - sample"]])  # 2 pages
    return add_file(records, "مواصفات - عينة.pdf", pdf, actor="engineer").id


def boq_file(records) -> str:
    rows = [["03/02", "خرسانة مسلحة للأسقف - عينة", "م3", 120]]
    return add_file(records, "مقايسة - عينة.xlsx", sample_xlsx({"BOQ": rows}), actor="engineer").id


def settled_question(ctx, *, settle: bool = True) -> str:
    card = Card(
        id=uuid4().hex,
        kind="question",
        title=copy.fill(copy.QUESTION_TITLE, agent=copy.ROLE_LEAD),
        detail=copy.QUESTION_DETAIL,
        options=("sent",),
        payload={
            "questions": [{"id": "q1", "text": "سعر طن الأسمنت كام؟ - عينة", "free_text": True}]
        },
    )
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    if settle:
        ctx.store.settle(card.id, answer_value(card, "sent", answers={"q1": "3950"}))
    return card.id


def log_page(records, *, dated: str | None = "2026-10-30", action: str = "read") -> str:
    log_id = uuid4().hex
    with records.write("Lead QS") as c:
        c.execute(
            "INSERT INTO web_log(id, at, actor, action, url, final_url, status, title, dated,"
            " dated_how) VALUES (?, ?, 'Lead QS', ?, ?, ?, 200, ?, ?, ?)",
            (
                log_id,
                "2026-11-05T08:42:00+00:00",
                action,
                "https://steel-sample.example/p",
                "https://steel-sample.example/p?final",
                "أسعار الحديد - عينة",
                dated,
                "page" if dated else None,
            ),
        )
    return log_id


# Every number needs real evidence -------------------------------------------------------------


async def test_number_from_a_file_needs_a_real_page(ctx):
    spec = spec_file(ctx.rec)
    with pytest.raises(ModelRetry, match="not in the file. It has 2"):
        await call("add_source", {"kind": "file", "file_id": spec, "locator": {"page": 9}}, ctx)
    out = ids(
        await call(
            "add_source",
            {"kind": "specification", "file_id": spec, "locator": {"page": 2}, "dated": DATED},
            ctx,
        )
    )
    [src] = sources(ctx.rec)
    assert out["source_id"] and src["kind"] == "specification" and src["file_id"] == spec
    assert src["locator"] == {"page": 2, "dated_how": "document"} and src["dated"] == DATED
    assert src["title"] == "مواصفات - عينة.pdf"  # the file's own name when no title is given


async def test_an_unknown_file_is_refused(ctx):
    with pytest.raises(ModelRetry, match="no file with this id"):
        await call("add_source", {"kind": "file", "file_id": "nope", "locator": {"page": 1}}, ctx)


async def test_a_file_source_needs_a_place_in_it(ctx):
    spec = spec_file(ctx.rec)
    with pytest.raises(ModelRetry, match="real evidence.*locator"):
        await call("add_source", {"kind": "quote", "file_id": spec}, ctx)
    with pytest.raises(ModelRetry, match="real evidence.*file_id"):
        await call("add_source", {"kind": "quote", "title": "عرض سعر - عينة"}, ctx)


async def test_row_must_exist(ctx):
    boq = boq_file(ctx.rec)
    with pytest.raises(ModelRetry, match="real evidence.*locator"):
        await call(
            "add_source",
            {"kind": "boq", "file_id": boq, "locator": {"sheet": "BOQ", "row": 9999}},
            ctx,
        )
    with pytest.raises(ModelRetry, match="real evidence"):
        await call(
            "add_source", {"kind": "boq", "file_id": boq, "locator": {"sheet": "X", "row": 1}}, ctx
        )
    await call(
        "add_source",
        {"kind": "boq", "file_id": boq, "locator": {"sheet": "BOQ", "row": "1", "column": "D"}},
        ctx,
    )
    assert sources(ctx.rec)[-1]["locator"]["row"] == 1  # "1" read as the row number


async def test_an_undated_file_is_dated_the_day_it_was_received(ctx):
    boq = boq_file(ctx.rec)
    out = ids(
        await call(
            "add_source",
            {"kind": "boq", "file_id": boq, "locator": {"sheet": "BOQ", "row": 1}},
            ctx,
        )
    )
    with ctx.rec.read() as c:
        (added_at,) = c.execute("SELECT added_at FROM files WHERE id = ?", (boq,)).fetchone()
    src = sources(ctx.rec)[-1]
    assert src["dated"] == local_day(added_at) and src["locator"]["dated_how"] == "received"
    assert out["dated"] == src["dated"] and out["dated_how"] == "received"
    assert copy.DATED_RECEIVED == {"en": "date received", "ar": "تاريخ الاستلام"}
    # a number from it takes that date, and its source says how it was dated
    await call("add_item", {"kind": "boq_item", "code": "03/02"}, ctx)
    number = {"item": "03/02", "name": "quantity", "value": "120", "unit": "م3"}
    await call("record_number", number | {"source_id": out["source_id"]}, ctx)
    shown = json.loads(await call("ledger_numbers", {"item": "03/02"}, ctx))
    [n] = shown["numbers"]
    assert n["dated"] == src["dated"] and n["source"]["dated_how"] == "received"


async def test_undated_files_can_be_refused_by_one_switch(ctx, monkeypatch):
    monkeypatch.setattr(tools_records, "UNDATED_FILES", "refuse")
    boq = boq_file(ctx.rec)
    with pytest.raises(ModelRetry, match="needs the date"):
        await call(
            "add_source",
            {"kind": "boq", "file_id": boq, "locator": {"sheet": "BOQ", "row": 1}},
            ctx,
        )


async def test_calculation_and_sandbox_sources_are_refused(ctx):
    for kind in ("calculation", "sandbox"):
        with pytest.raises(ModelRetry, match="QS Calc Engine"):
            await call("add_source", {"kind": kind, "title": "x - عينة"}, ctx)


async def test_unsettled_card_is_no_evidence(ctx):
    card = settled_question(ctx, settle=False)
    with pytest.raises(ModelRetry, match="real evidence.*card_id"):
        await call("add_source", {"kind": "engineer", "card_id": card}, ctx)
    with pytest.raises(ModelRetry, match="real evidence.*card_id"):
        await call("add_source", {"kind": "engineer", "card_id": "no-such-card"}, ctx)


async def test_an_answered_card_is_evidence_with_its_own_date(ctx):
    card = settled_question(ctx)
    found = engineer.answered(ctx.store, card)
    with pytest.raises(ModelRetry, match="real evidence.*question"):
        await call("add_source", {"kind": "engineer", "card_id": card, "question": "q9"}, ctx)
    await call(
        "add_source",
        {"kind": "engineer", "card_id": card, "question": "q1", "dated": "1999-01-01"},
        ctx,
    )
    src = sources(ctx.rec)[-1]
    assert src["dated"] == found["dated"]  # the day it was answered, never the model's date
    assert src["locator"] == {"card_id": card, "question": "q1", "answer": "3950"}
    assert src["title"] == "سعر طن الأسمنت كام؟ - عينة"


async def test_web_source_takes_link_and_dates_from_the_log(ctx):
    logged = log_page(ctx.rec)
    await call("add_source", {"kind": "web", "log_id": logged, "title": "made up"}, ctx)
    src = sources(ctx.rec)[-1]
    assert src["url"] == "https://steel-sample.example/p?final" and src["dated"] == "2026-10-30"
    assert src["title"] == "أسعار الحديد - عينة" and src["locator"]["dated_how"] == "page"
    undated = log_page(ctx.rec, dated=None)
    await call("add_source", {"kind": "web", "log_id": undated}, ctx)
    src = sources(ctx.rec)[-1]
    assert src["dated"] == local_day("2026-11-05T08:42:00+00:00")
    assert src["locator"]["dated_how"] == "read"
    for bad in ("no-such-log", log_page(ctx.rec, action="search")):
        with pytest.raises(ModelRetry, match="real evidence.*log_id"):
            await call("add_source", {"kind": "web", "log_id": bad}, ctx)


async def test_a_qsmind_price_in_the_cache_is_evidence(ctx, eng):
    payload = {
        "name": {"en": "Rebar 16 mm - sample", "ar": "حديد تسليح 16 مم - عينة"},
        "sources": [{"url": "https://prices.example/rebar", "title": "t", "quote": "q"}],
    }
    with eng.write("engine") as c:
        c.execute(
            "INSERT INTO price_cache(country, item_id, day, payload) VALUES (?, ?, ?, ?)",
            ("egypt", "rebar-16", "2026-11-04", json.dumps(payload)),
        )
    await call("add_source", {"kind": "prices", "ref": "prices:EG/rebar-16@2026-11-04"}, ctx)
    src = sources(ctx.rec)[-1]
    assert (src["dated"], src["url"]) == ("2026-11-04", "https://prices.example/rebar")
    assert src["title"] == "حديد تسليح 16 مم - عينة" and "quote" not in json.dumps(src)
    for bad in ("prices:EG/rebar-16@2026-10-01", "prices:EG/nothing@2026-11-04", "rebar"):
        with pytest.raises(ModelRetry, match="real evidence.*ref"):
            await call("add_source", {"kind": "prices", "ref": bad}, ctx)


async def test_a_connector_call_is_evidence_when_it_answered(ctx):
    with ctx.rec.write("Lead QS") as c:
        for call_id, ok in (("call-ok", 1), ("call-failed", 0)):
            c.execute(
                "INSERT INTO connector_calls(id, at, actor, connector, tool, args, ok)"
                " VALUES (?, '2026-11-05T08:00:00+00:00', 'Lead QS', 'qiyas', 'take_off', '{}', ?)",
                (call_id, ok),
            )
    await call("add_source", {"kind": "connector", "call_id": "call-ok"}, ctx)
    assert sources(ctx.rec)[-1]["title"] == "qiyas: take_off"
    with pytest.raises(ModelRetry, match="real evidence.*call_id"):
        await call("add_source", {"kind": "connector", "call_id": "call-failed"}, ctx)


# Engineer Records ------------------------------------------------------------------------------


async def test_engineer_wide_write_asks_first(ctx, eng):
    ctx.host.answers = {"keep": "no"}
    out = await call(
        "add_item",
        {"kind": "price", "fields": {"description": "أسمنت - عينة"}, "where": "engineer"},
        ctx,
    )
    [card] = ctx.host.cards
    assert card.kind == "keep" and card.options == ("yes", "no")
    assert card.title == copy.KEEP_ENGINEER_ASK and out.startswith("not done:")
    assert items(eng) == []
    ctx.host.answers = {"keep": "yes"}
    item = ids(await call("add_item", {"kind": "price", "code": "P1", "where": "engineer"}, ctx))
    await call("add_item", {"kind": "price", "code": "P2", "where": "engineer"}, ctx)
    assert len(ctx.host.cards) == 2  # asked once more, then not again in this Brief
    assert [i["code"] for i in items(eng)] == ["P1", "P2"] and items(ctx.rec) == []
    assert item["where"] == "engineer"


async def test_an_engineer_wide_number_needs_engineer_evidence(ctx, eng):
    ctx.host.answers = {"keep": "yes"}
    project_file = spec_file(ctx.rec)
    with pytest.raises(ModelRetry, match="no file with this id"):
        await call(
            "add_source",
            {"kind": "file", "file_id": project_file, "locator": {"page": 1}, "where": "engineer"},
            ctx,
        )
    own = spec_file(eng)
    source = ids(
        await call(
            "add_source",
            {"kind": "file", "file_id": own, "locator": {"page": 1}, "where": "engineer"},
            ctx,
        )
    )["source_id"]
    await call("add_item", {"kind": "price", "code": "P1", "where": "engineer"}, ctx)
    number = {"item": "P1", "name": "price", "value": "3950", "currency": "EGP"}
    await call("record_number", number | {"source_id": source, "where": "engineer"}, ctx)
    with eng.read() as c:
        assert c.execute("SELECT value FROM numbers").fetchall() == [("3950",)]


async def test_an_engineer_answer_can_be_an_engineer_wide_source(ctx, eng):
    ctx.host.answers = {"keep": "yes"}
    card = settled_question(ctx)  # asked in this project's Brief
    await call(
        "add_source",
        {"kind": "engineer", "card_id": card, "question": "q1", "where": "engineer"},
        ctx,
    )
    [src] = sources(eng)
    assert src["locator"]["answer"] == "3950"  # the answer travels with it


async def test_search_both_fuses_project_and_engineer(ctx, eng):
    add_file(
        ctx.rec, "مواصفات - عينة.txt", "عزل الرطوبة للأساسات - عينة".encode(), actor="engineer"
    )
    add_file(eng, "ملاحظاتي - عينة.txt", "عزل الرطوبة بالبيتومين - عينة".encode(), actor="engineer")
    out = await call("search_records", {"query": "عزل الرطوبة", "where": "both"}, ctx)
    head = json.loads(next(line for line in out.splitlines() if line.startswith("{")))
    assert {h["where"] for h in head["hits"]} == {"project", "engineer"}
    mine = next(h for h in head["hits"] if h["where"] == "engineer")
    chunk = await call("read_chunk", {"chunk_id": mine["chunk_id"], "where": "engineer"}, ctx)
    assert "بالبيتومين" in chunk
    only = await call("search_records", {"query": "عزل الرطوبة", "where": "engineer"}, ctx)
    assert "بالبيتومين" in only and "للأساسات" not in only


def test_search_says_how_to_search_in_both_languages():
    assert "other language" in REGISTRY["search_records"].description


# What to keep ----------------------------------------------------------------------------------


def test_personal_data_is_found_by_name_and_by_value():
    found = keep.personal(
        {
            "name": "مصنع الحديد - عينة",  # a company's name is not a person's
            "phone": "01001234567",
            "تليفون المورد": "٠١٢٣٤٥٦٧٨٩٠",
            "contact": "م. أحمد - عينة",
            "notes": "اتصل على +966 50 123 4567",
            "mail": "sales@sample.example",
            "العنوان": "شارع التحرير - عينة",
            "national_id": "29001011234567",
            "whatsapp": "01001234567",
            "description": "خرسانة مسلحة 120.5 م3 - عينة",
            "code": "03/02",
        }
    )
    assert found == {
        "phone": "phone",
        "تليفون المورد": "phone",
        "contact": "person_name",
        "notes": "phone",
        "mail": "email",
        "العنوان": "address",
        "national_id": "national_id",
        "whatsapp": "whatsapp",
    }
    assert keep.KINDS == tuple(copy.KEEP_KINDS)


async def test_phone_number_asks_once_per_kind_and_never_drops(ctx, eng):
    ctx.host.answers = {"question": json.dumps({"choice": "sent", "answers": {"keep": "never"}})}
    out = await call(
        "add_item",
        {"kind": "supplier", "fields": {"name": "مصنع - عينة", "phone": "01001234567"}},
        ctx,
    )
    assert items(ctx.rec)[-1]["fields"] == {"name": "مصنع - عينة"}
    assert copy.fill(copy.KEEP_NEVER, kind=copy.KEEP_KINDS["phone"])["en"] in out
    await call("add_item", {"kind": "supplier", "fields": {"mobile": "+966501234567"}}, ctx)
    assert len(ctx.host.cards) == 1  # asked once for "phone"
    [card] = ctx.host.cards
    assert card.kind == "question" and card.payload["questions"][0]["id"] == "keep"
    assert "phone" not in json.dumps(items(ctx.rec)[-1]["fields"]) and "+966" not in out
    with eng.read() as c:
        assert c.execute("SELECT kind, decision, card_id FROM keep_policy").fetchall() == [
            ("phone", "never", card.id)
        ]


async def test_keep_is_remembered_for_every_project(ctx, eng, data_dir):
    ctx.host.answers = {"question": json.dumps({"choice": "sent", "answers": {"keep": "keep"}})}
    await call("add_item", {"kind": "supplier", "fields": {"email": "a@sample.example"}}, ctx)
    other = tool_ctx(ctx.rec, services=fake_services(engineer=lambda: eng))  # another Brief
    await call("add_item", {"kind": "supplier", "fields": {"بريد": "b@sample.example"}}, other)
    assert other.host.cards == [] and items(ctx.rec)[-1]["fields"] == {"بريد": "b@sample.example"}


async def test_the_keep_question_is_in_the_engineers_language(ctx):
    ctx.host.answers = {"question": "sent"}  # no answer given: nothing is kept, nothing saved
    await call("add_item", {"kind": "supplier", "fields": {"phone": "01001234567"}}, ctx)
    [card] = ctx.host.cards
    [question] = card.payload["questions"]
    assert question["text"] == copy.fill(copy.KEEP_ASK, kind=copy.KEEP_KINDS["phone"])["ar"]
    assert question["options"] == [copy.KEEP_OPTION_KEEP["ar"], copy.KEEP_OPTION_NEVER["ar"]]
    assert items(ctx.rec)[-1]["fields"] == {}


# Lessons and the rest -------------------------------------------------------------------------


async def test_note_lesson_writes_a_lesson_item(ctx):
    out = ids(
        await call(
            "note_lesson",
            {
                "text": "راجع وحدة البند قبل التسعير - عينة",
                "kind": "correction",
                "source_ref": "file:abc#page=3",
            },
            ctx,
        )
    )
    [lesson] = items(ctx.rec, "lesson")
    assert out["lesson_id"] and lesson["fields"] == {
        "text": "راجع وحدة البند قبل التسعير - عينة",
        "kind": "correction",
        "source_ref": "file:abc#page=3",
    }
    with pytest.raises(ModelRetry, match="kind"):
        await call("note_lesson", {"text": "x - عينة", "kind": "gossip"}, ctx)
    assert "note_lesson" in agents.lead_spec().tools
    assert "note_lesson" not in agents.checker_spec().tools


async def test_replayed_write_adds_nothing(ctx):
    first = await call("add_item", {"kind": "boq_item", "code": "03/02"}, ctx)
    again = await call("add_item", {"kind": "boq_item", "code": "03/02"}, ctx)
    assert first == again and len(items(ctx.rec)) == 1


def test_descriptions_are_short_recipes_with_an_example():
    for name in ("add_source", "add_item", "record_number", "search_records", "note_lesson"):
        doc = REGISTRY[name].description
        assert len(doc.split()) <= 120, (name, len(doc.split()))
        assert "\nExample:\n" in doc and doc.rstrip().endswith("}"), name
