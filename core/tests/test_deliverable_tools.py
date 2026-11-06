"""The outputs tools the agents use on Deliverables, and the Checking QS's check of one (Plan 6
Task 7). Agents only propose; scripted models only, synthetic «عينة» data."""

import json

import pytest
from pydantic_ai import ModelRetry

from qsone import copy
from qsone.deliverables import changes, comments, review, store
from qsone.deliverables import tools as outputs
from qsone.engine.agents import checker_spec, lead_spec, words
from qsone.engine.team import specialist_tools
from qsone.engine.tools import REGISTRY, call
from qsone.engine.types import AgentSpec, Data, Review, Reviewed
from qsone.records import files
from tests.engine_fakes import SONNET
from tests.fakes_tools import tool_ctx
from tests.samples import (
    CLIENT_FIRST_ROW,
    sample_boq_rows,
    sample_client_xlsx,
    sample_document,
    sample_sheet,
    sample_source,
)

SPECIALIST = AgentSpec(
    id="takeoff",
    name={"en": "Take-off QS", "ar": "مهندس الحصر"},
    role="specialist",
    instructions="عينة",
    tools=outputs.OUTPUTS_TOOLS,
    tier="specialist",
)


def item(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


async def run(ctx, name: str, args: dict) -> dict:
    return json.loads(await call(name, args, ctx))


# Registration --------------------------------------------------------------------------------


def test_the_team_has_the_outputs_tools_and_the_checker_has_none():
    for name in outputs.OUTPUTS_TOOLS:
        tool = REGISTRY[name]
        roles = {"lead"} if name == "pack_propose" else {"lead", "specialist"}
        assert tool.group == "outputs" and tool.roles == roles, name
    assert {REGISTRY[n].risk for n in ("deliverable_read", "client_file_read")} == {"read"}
    assert REGISTRY["client_file_read"].untrusted  # the client's cells are file text
    assert set(outputs.OUTPUTS_TOOLS) <= set(lead_spec().tools)
    assert set(outputs.OUTPUTS_TOOLS) - {"pack_propose"} <= set(specialist_tools())
    assert "pack_propose" not in specialist_tools()
    assert not set(outputs.OUTPUTS_TOOLS) & set(checker_spec().tools)
    assert "deliverable_create" in lead_spec().instructions
    assert words(lead_spec().instructions) <= 600


# deliverable_create --------------------------------------------------------------------------


async def test_create_is_draft_version_one_and_shows_a_card(rec):
    ctx = tool_ctx(rec)
    rows = sample_boq_rows(rec)
    out = await run(ctx, "deliverable_create", {"kind": "sheet", "variant": "boq",
                    "title": "جدول الكميات - عينة", "language": "ar", "rows": rows})  # fmt: skip
    d = out["id"]
    assert out == {"id": d, "version": 1}
    v = store.view(rec, d)
    assert v["status"] == "draft" and v["version"] == 1 and v["pending"] == 0
    assert item(v, "03/02")["cells"]["amount"]["value"] == "4782060.00"
    assert v["off_desk"] is True
    assert [e for e in ctx.host.events if isinstance(e, Data)] == [
        Data(ctx.brief_id, "deliverable", d, {"id": d})
    ]
    with rec.read() as c:
        (by,) = c.execute("SELECT created_by FROM deliverables WHERE id = ?", (d,)).fetchone()
    assert by == "lead_qs"


async def test_create_refusals_name_the_field(rec):
    ctx = tool_ctx(rec)
    with pytest.raises(ModelRetry) as e:
        await call("deliverable_create", {"kind": "sheet", "variant": "boq", "title": "x - عينة",
                   "language": "ar", "rows": [{"item_id": "f" * 32}]}, ctx)  # fmt: skip
    assert copy.ROW_NOT_FOUND["en"] in str(e.value) and "rows[0]" in str(e.value)
    with pytest.raises(ModelRetry) as e:
        await call("deliverable_create", {"kind": "sheet", "variant": "boq", "title": "  ",
                   "language": "ar"}, ctx)  # fmt: skip
    assert "title" in str(e.value)


# deliverable_read ----------------------------------------------------------------------------


async def test_read_is_paged_and_fits_one_result(rec):
    d = sample_sheet(rec, rows=120)
    ctx = tool_ctx(rec)
    first = await run(ctx, "deliverable_read", {"id": d})  # json.loads: never cut at 8 KB
    assert 0 < len(first["rows"]) <= 50 and first["next"] == len(first["rows"])
    shown = {c["source"] for r in first["rows"] for c in r["cells"].values() if c.get("source")}
    assert set(first["sources"]) <= shown | {first["total"]["source"]}
    seen, at = [], 0
    while at is not None:
        page = await run(ctx, "deliverable_read", {"id": d, "offset": at})
        seen += [r["id"] for r in page["rows"]]
        at = page["next"]
    assert seen == [r["id"] for r in store.view(rec, d)["rows"]]
    with pytest.raises(ModelRetry):
        await call("deliverable_read", {"id": d, "limit": 51}, ctx)


async def test_read_a_document_pages_its_blocks(rec):
    d = sample_document(rec, sample_sheet(rec))
    out = await run(tool_ctx(rec), "deliverable_read", {"id": d, "limit": 3})
    assert len(out["blocks"]) == 3 and out["next"] == 3
    assert len(out["refs"]) == 1 and out["untraced"] == []  # «٣٠» is in the fourth block
    rest = await run(tool_ctx(rec), "deliverable_read", {"id": d, "offset": 3})
    assert rest["refs"] == {} and rest["untraced"][0]["text"] == "٣٠"


# deliverable_propose -------------------------------------------------------------------------


async def test_propose_holds_a_pending_change_and_leaves_the_ledger(rec):
    d = sample_sheet(rec)
    row = item(store.view(rec, d), "03/02")
    op = {"op": "set_number", "row": row["id"], "name": "rate", "value": "40000.00",
          "source_id": sample_source(rec)}  # fmt: skip
    out = await run(tool_ctx(rec), "deliverable_propose", {"id": d, "ops": [op], "reason": "عرض"})
    [change] = changes.pending(rec, d)
    assert out == {"change_ids": [change.id]} and change.author == "lead_qs"
    assert item(store.view(rec, d), "03/02")["cells"]["rate"]["value"] == "39850.50"


async def test_propose_refusal_says_what_to_send(rec):
    d = sample_sheet(rec)
    row = item(store.view(rec, d), "03/02")
    op = {"op": "set_number", "row": row["id"], "name": "rate", "value": "40000.00"}
    with pytest.raises(ModelRetry) as e:
        await call("deliverable_propose", {"id": d, "ops": [op], "reason": None}, tool_ctx(rec))
    assert copy.NUMBER_NEEDS_SOURCE["en"] in str(e.value)
    assert "Field: ops[0].source_id" in str(e.value)
    assert changes.pending(rec, d) == []


async def test_a_specialist_proposes_under_its_own_name(rec):
    d = sample_sheet(rec)
    row = item(store.view(rec, d), "1-1")
    op = {"op": "set_field", "row": row["id"], "key": "description", "value": "حفر - عينة"}
    await run(tool_ctx(rec, agent=SPECIALIST), "deliverable_propose", {"id": d, "ops": [op]})
    assert [c.author for c in changes.pending(rec, d)] == ["Take-off QS"]


# deliverable_comment -------------------------------------------------------------------------


async def test_comment_is_ones_note(rec):
    d = sample_sheet(rec)
    row = item(store.view(rec, d), "03/02")
    anchor = {"type": "cell", "row": row["id"], "column": "rate"}
    out = await run(tool_ctx(rec), "deliverable_comment",
                    {"id": d, "anchor": anchor, "body": "السعر من عرض المورّد - عينة"})  # fmt: skip
    [thread] = comments.list_comments(rec, d)
    assert out == {"comment_id": thread["id"]}
    assert (thread["kind"], thread["author"], thread["code"]) == ("note", "lead_qs", None)


# The client's file ---------------------------------------------------------------------------


async def test_client_file_read_is_paged_and_fenced(rec):
    f = files.add_file(rec, "مقايسة - عينة.xlsx", sample_client_xlsx(), actor="engineer").id
    ctx = tool_ctx(rec)
    text = await call("client_file_read", {"file_id": f, "sheet": "BOQ", "limit": 5}, ctx)
    assert ctx.fence in text and "BOQ" in text
    assert ctx.store.brief(ctx.brief_id)["read_untrusted"]
    with pytest.raises(ModelRetry) as e:
        await call("client_file_read", {"file_id": "f" * 32}, ctx)
    assert copy.FILE_NOT_IN_PROJECT["en"] in str(e.value)


async def test_client_file_plan_gives_its_id_and_preview(rec):
    d = sample_sheet(rec)
    f = files.add_file(rec, "مقايسة - عينة.xlsx", sample_client_xlsx(), actor="engineer").id
    rows = [r for r in store.view(rec, d)["rows"] if r["kind"] == "item"]
    plan = {
        "sheet": "BOQ", "header_row": 11, "write": ["rate"],
        "columns": {"code": "A", "rate": "E"},
        "rows": [{"row": CLIENT_FIRST_ROW + i, "part": r["id"]} for i, r in enumerate(rows)],
    }  # fmt: skip
    ctx = tool_ctx(rec)
    out = await run(ctx, "client_file_plan", {"deliverable_id": d, "file_id": f, "plan": plan})
    assert out["plan_id"] and out["preview"] is None
    assert out["note"] == copy.FILL_NEEDS_SIGNOFF["en"]
    review.record_check(rec, d, version_n=1, code="A", checker="model-sample",
                        same_provider=False, summary="", comments=[])  # fmt: skip
    review.sign_off(rec, d, actor="engineer")
    again = tool_ctx(rec)  # a new Brief: the same call in one Brief answers what it did before
    out = await run(again, "client_file_plan", {"deliverable_id": d, "file_id": f, "plan": plan})
    assert out["preview"]["writes"] == 6 and out["preview"]["mismatches"] == []
    assert out["preview"]["revision"] == 1


# The Checking QS checks a Deliverable --------------------------------------------------------


def scripted_checker(code: str, comments_: tuple = ()):
    seen = []

    async def checker(packet, maker):
        seen.append((packet, maker))
        return Review(code=code, comments=comments_, checker=SONNET.choice, same_provider=False,
                      round=1)  # fmt: skip

    return checker, seen


async def test_the_checking_qs_records_its_review_on_the_version_it_read(rec):
    d = sample_sheet(rec)
    ctx = tool_ctx(rec)
    finding = ({"about": "03/02", "text": "الفئة أعلى من السوق - عينة"},)
    ctx.host.checker, seen = scripted_checker("C", finding)
    out = await run(ctx, "submit_for_check", {"deliverable_id": d})
    assert out["deliverable_id"] == d and out["version"] == 1 and out["code"] == "C"
    [(packet, maker)] = seen
    rate = item(store.view(rec, d), "03/02")["cells"]["rate"]
    assert rate["number_id"] in {n["id"] for n in packet.numbers}
    assert any(f["formula"] == "quantity * rate" for f in packet.formulas)
    assert maker == ctx.store.run(ctx.run_id)["choice"]
    closeout = review.closeout(rec, d)
    assert closeout["check"]["version_n"] == 1 and closeout["check"]["code"] == "C"
    assert closeout["check"]["checker"] == SONNET.choice.model
    assert [t["body"] for t in closeout["blocking"]] == ["03/02: الفئة أعلى من السوق - عينة"]
    assert [e.review.code for e in ctx.host.events if isinstance(e, Reviewed)] == ["C"]
    with pytest.raises(ModelRetry) as e:  # the same version is not checked twice
        await call("submit_for_check", {"deliverable_id": d}, ctx)
    assert "deliverable_propose" in str(e.value)


async def test_the_checking_qs_reads_a_document_with_its_untraced_digits(rec):
    d = sample_document(rec, sample_sheet(rec))
    ctx = tool_ctx(rec)
    ctx.host.checker, seen = scripted_checker("A")
    await run(ctx, "submit_for_check", {"deliverable_id": d})
    [(packet, _)] = seen
    assert packet.deliverable.kind == "document" and "حالياً" in packet.deliverable.body
    assert "٣٠" in packet.unsourced and packet.numbers
    assert store.view(rec, d)["status"] == "checked" and store.view(rec, d)["code"] == "A"


async def test_an_unknown_id_is_still_refused(rec):
    with pytest.raises(ModelRetry) as e:
        await call("submit_for_check", {"deliverable_id": "f" * 32}, tool_ctx(rec))
    assert "make_deliverable" in str(e.value)
