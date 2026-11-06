"""What ONE's AI staff claim, against what their tool calls did (the real walk, 6 Nov 2026,
gemini-3.1-flash-lite on real tenders): «استوردت البنود» with 0 items (the import was refused),
«أضفت البنود» after a refused deliverable_propose, 5 priced items claimed on an empty Sheet, and a
reply that ends on «بدأت … هل حابب أبعتلك الجدول» with no work done.

Scripted models make exactly those mistakes; synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the engine fixtures, imported)

import json

from qsone.engine import truth
from qsone.engine.truth import Brief, Coverage
from tests.engine_fakes import call, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import (  # noqa: F401 - the runner's fixtures
    finish,
    links,
    make_engine,
    no_budget_card,
    project,
    registry,
    started,
)
from tests.test_truth_runner import boq, datas

WHY = {"en": "The Sheet's columns are not valid.", "ar": "أعمدة الجدول مش صح."}


# The checks, on the walk's own words ------------------------------------------------------------


def test_a_claim_after_a_refusal_is_flagged_with_the_reason():
    did = Brief(refused={"boq_import": WHY})
    [found] = truth.undone("استوردت البنود دلوقتي.", Coverage(0, 0, 0), did)
    assert found.kind == "refused" and "boq_import" in found.fix
    assert "أعمدة الجدول مش صح" in found.flag["ar"] and "ONE رفضه" in found.flag["ar"]
    did = Brief(refused={"deliverable_propose": WHY})
    [found] = truth.undone("أضفت البنود للمستند.", None, did)
    assert found.kind == "refused"
    # once a later call went through, or when the reply says it was not done, there is no claim
    assert truth.undone("أضفت البنود.", None, Brief(done={"deliverable_propose"})) == []
    assert truth.undone("ماقدرتش أضيف البنود، ONE رفض الأعمدة.", None, did) == []
    assert truth.undone("I could not import the BOQ: no currency.", None, did) == []


def test_an_import_claim_with_nothing_imported():
    [found] = truth.undone("Imported the BOQ: 54 items.", Coverage(0, 0, 0), Brief())
    assert found.kind == "undone" and "استيراد المقايسة" in found.flag["ar"]
    # an earlier Brief's import is no claim of this one
    assert truth.undone("The BOQ was imported: 54 items.", Coverage(54, 0, 0), Brief()) == []


def test_priced_items_on_a_sheet_with_no_items():
    text = "تسعير بند 16 (سيراميك أرضيات): تم وضع سعر 27 جنيه للمتر المسطح."
    did = Brief(done={"deliverable_create"}, deliverables=1, item_rows=0, writes=1)
    [found] = truth.undone(text, Coverage(54, 54, 1), did)
    assert found.kind == "empty"
    assert (
        truth.undone(text, Coverage(54, 54, 1), Brief(done={"deliverable_create"}, item_rows=3))
        == []
    )


def test_work_said_to_be_under_way_is_a_promise_even_with_a_question_after():
    lahun = (
        "بناءً على طلبك، بدأت في العمل على نسخة جديدة من المقايسة بدون أسعار.\n"
        "1. هطابق بنود المقايسة مع التحليل.\n"
        "دلوقتي، أنا بجهز المسودة الأولى للمقايسة بدون أسعار. هل حابب أبعتلك الجدول ده الأول؟"
    )
    assert truth.promise(lahun, Brief()) is not None
    assert truth.promise(lahun) is None  # without the Brief's facts, a question still ends it
    assert truth.promise(lahun, Brief(writes=2)) is None  # work was done: it may say so
    assert truth.promise("لو بعتلي العرض هسعّر البنود.", Brief()) is None
    assert truth.promise("The top 5 items by amount are in the view.", Brief()) is None


# The Brief Runner ---------------------------------------------------------------------------------


async def test_a_reply_that_claims_a_refused_step_goes_back_then_is_flagged(
    make_engine, project, registry
):
    rec = registry.get(project)
    boq(rec, 3)
    bad = {"id": "0" * 32, "ops": [{"op": "set_columns", "columns": "x"}]}
    claim = "أضفت البنود للمستند."
    lead = scripted(call("deliverable_propose", bad), said(claim), said(claim))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "ضيف البنود للمستند"))
    assert lead.calls == 3
    fix = str(lead.seen[2])
    assert "ONE refused deliverable_propose" in fix and "Nothing was done by it" in fix
    [facts] = datas(events, "facts")
    flags = [f["ar"] for f in facts.data["flags"]]
    assert any("ONE رفضه فماتعملش" in f for f in flags)
    assert not any("{" in f or "0000000000" in f for f in flags)  # plain words, no ids


async def test_a_promise_of_work_with_no_work_goes_back(make_engine, project):
    promised = "بدأت في العمل على نسخة جديدة. دلوقتي أنا بجهز المسودة. هل حابب أبعتلك الجدول؟"
    lead = scripted(said(promised), said("لسه ماعملتش حاجة: قولي أبدأ بأنهي قسم."))
    engine = await started(make_engine(links(lead=lead)))
    events = await finish(engine, await engine.start_brief(project, "سعّر المقايسة"))
    assert lead.calls == 2 and "ends on a promise" in str(lead.seen[1])
    assert not datas(events, "facts")


async def test_a_currency_the_file_does_not_state_is_asked(registry, project):
    from qsone.engine.tools import call as call_tool
    from qsone.records import ledger
    from qsone.records.files import add_file
    from qsone.tools import boq as boq_tools  # noqa: F401 - registers boq_import
    from tests.fakes_tools import tool_ctx
    from tests.samples import sample_boq_xlsx

    rec = registry.get(project)
    data = sample_boq_xlsx([["03/02", "خرسانة - عينة", "م3", 120, 10, 1200]])
    file_id = add_file(rec, "مقايسة - عينة.xlsx", data, actor="engineer").id
    keep = json.dumps({"choice": "keep", "answers": {}, "rows_ok": []})
    sent = json.dumps({"choice": "sent", "answers": {"currency": "egp"}})
    ctx = tool_ctx(rec, answers={"rows": keep, "question": sent})
    columns = {"code": "A", "description": "B", "unit": "C", "quantity": "D", "rate": "E"}
    args = {"file_id": file_id, "sheet": "BOQ", "header_row": 3, "columns": columns}
    out = await call_tool("boq_import", args, ctx)
    assert "Imported the BOQ" in out
    [asked] = [c for c in ctx.host.cards if c.kind == "question"]
    assert asked.payload["questions"][0]["options"] == ["EGP", "SAR", "AED", "USD"]
    with rec.read() as c:
        (currency,) = c.execute("SELECT currency FROM numbers WHERE name = 'rate'").fetchone()
    assert currency == "EGP"
    assert ledger  # imported for its numbers
