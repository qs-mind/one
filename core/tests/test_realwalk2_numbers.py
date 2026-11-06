"""Real walk 2 Group N regressions, using synthetic sample workbooks only."""

import json
from decimal import Decimal

import pytest
from pydantic_ai import ModelRetry

from qsone.clientfile import imported
from qsone.engine import tools_records, truth
from qsone.engine.tools import call
from qsone.records import boq
from tests.fakes_tools import tool_ctx
from tests.test_boq_import import add_boq, book, data_of, keep_all, run_import
from tests.test_evaluate import run


@pytest.mark.parametrize(
    "fn, expected", [("sum", "0.60"), ("avg", "0.20"), ("min", "0.10"), ("max", "0.30")]
)
def test_aggregate_separate_arguments_match_list(fn, expected):
    values = [("0.1", "EGP"), ("0.2", "EGP"), ("0.3", "EGP")]
    separate = run(f"{fn}(a,b,c)", "EGP", **dict(zip("abc", values, strict=True)))
    listed = run(f"{fn}(items)", "EGP", items=values)
    assert separate.value == listed.value == Decimal(expected)


async def test_build_up_source_trimmed_sheet_keeps_real_name(rec):
    ctx = tool_ctx(rec)
    f = add_boq(rec, book([["X", "Sample build-up", "m3", 1, 27]], sheet="تسعير "))
    result = json.loads(
        await call(
            "add_source",
            {"kind": "boq", "file_id": f, "locator": {"sheet": "تسعير", "row": 4, "column": "E"}},
            ctx,
        )
    )
    with rec.read() as c:
        loc = json.loads(
            c.execute("SELECT locator FROM sources WHERE id=?", (result["source_id"],)).fetchone()[
                0
            ]
        )
        assert loc["sheet"] == "تسعير "
        assert truth.value_in(c, f, {"sheet": "تسعير", "row": 4}, "27")[0]
    resource = json.loads(
        await call(
            "add_item",
            {"kind": "resource", "fields": {"description": "Sample build-up", "unit": "m3"}},
            ctx,
        )
    )
    await call(
        "record_number",
        {
            "item": resource["item_id"],
            "name": "rate",
            "value": "27",
            "unit": "m3",
            "currency": "EGP",
            "source_id": result["source_id"],
        },
        ctx,
    )


def sample_lahun(rec):
    rows = [["A", "Sample item", "m3", None, None, 5, 10, 50]]
    rows += [[None] * 8 for _ in range(49)]
    rows += [[f"B{i}", "Sample alternative", "m3", i, None, None, 10, i * 10] for i in range(1, 12)]
    rows += [["M", "Sample missing quantity", "m3"]]
    return add_boq(
        rec,
        book(
            rows,
            header=[
                "Code",
                "Description",
                "Unit",
                "Original quantity",
                "Added",
                "Total quantity",
                "Rate",
                "Amount",
            ],
        ),
    )


async def test_lahun_quantity_block_uses_own_cells_and_reports_rows(rec):
    ctx = tool_ctx(rec, answers={"rows": keep_all()})
    f = sample_lahun(rec)
    columns = {
        "code": "A",
        "description": "B",
        "unit": "C",
        "quantity": "F",
        "rate": "G",
        "amount": "H",
    }
    p = boq.plan(rec, f, sheet="BOQ", header_row=3, columns=columns)
    from qsone.tools.boq import _card

    card = _card(ctx, p)
    assert "54–64" in card.detail["en"] and "D" in card.detail["ar"]
    out = data_of(await run_import(ctx, f, columns=columns, currency="EGP"))
    assert out["quantity_fallbacks"] == {"D": list(range(54, 65))}
    assert out["no_quantity"] == [65]
    with rec.read() as c:
        rows = c.execute(
            "SELECT n.value, s.locator FROM numbers n JOIN items i ON i.id=n.item_id "
            "JOIN sources s ON s.id=n.source_id WHERE n.name='quantity' "
            "AND json_extract(i.fields,'$.row') BETWEEN 54 AND 64 ORDER BY i.rowid"
        ).fetchall()
    assert [Decimal(v) for v, _ in rows] == list(range(1, 12))
    assert [json.loads(loc)["column"] for _, loc in rows] == ["D"] * 11


async def test_client_boq_keeps_file_totals_and_discount(rec):
    ctx = tool_ctx(rec, answers={"rows": keep_all()})
    rows = [["1", "Sample work", "m3", 1, 100, 100]]
    rows += [[None] * 6 for _ in range(45)]
    rows += [["", "إجمالي القسم - عينة", "", "", "", 100]]  # row 50
    rows += [["", "خصم 13% - عينة", "", "", "", 13]]  # row 51
    rows += [[None] * 6 for _ in range(14)]
    rows += [["", "الإجمالي بعد الخصم - عينة", "", "", "", 87]]  # row 66
    f = add_boq(rec, book(rows))
    out = data_of(
        await run_import(
            ctx,
            f,
            columns={
                "code": "A",
                "description": "B",
                "unit": "C",
                "quantity": "D",
                "rate": "E",
                "amount": "F",
            },
            currency="EGP",
        )
    )
    assert out["items"] == 1 and out["headings"] == 3
    view = imported.sheet(rec, f)
    assert len(view["rows"]) == 4
    assert boq.preview(rec, f, "BOQ")["overview"]["total"]["value"] == "87"
    for row, value, source_row in zip(
        view["rows"][1:], ["100", "13", "87"], [50, 51, 66], strict=True
    ):
        cell = row["cells"]["amount"]
        assert cell["value"] == value
        assert view["sources"][cell["source"]]["locator"]["row"] == source_row


async def test_test_price_cannot_attach_to_unnamed_boq_item(rec):
    ctx = tool_ctx(rec)
    ctx.brief_id = ctx.store.new_brief(
        rec.id, "Record sample price 27 from sheet Quote row 8 column C."
    )
    item = json.loads(
        await call(
            "add_item",
            {
                "kind": "boq_item",
                "code": "1",
                "fields": {"description": "Sample work", "unit": "m3", "row": 8},
            },
            ctx,
        )
    )
    f = add_boq(rec, book([["X", "Sample price", "m3", 1, 27]]))
    source = json.loads(
        await call(
            "add_source", {"kind": "boq", "file_id": f, "locator": {"sheet": "BOQ", "row": 4}}, ctx
        )
    )
    args = {
        "item": item["item_id"],
        "name": "rate",
        "value": "27",
        "unit": "m3",
        "currency": "EGP",
        "source_id": source["source_id"],
    }
    with pytest.raises(ModelRetry, match="(?i)name.*item|item.*name"):
        await call("record_number", args, ctx)
    with rec.read() as c:
        assert c.execute("SELECT count(*) FROM numbers").fetchone()[0] == 0
    ctx.brief_id = ctx.store.new_brief(rec.id, "Use this price for BOQ item 1.")
    assert "number_id" in json.loads(await call("record_number", args, ctx))


@pytest.mark.parametrize(
    "asked, real", [(" تسـعير\u200f", "تسعير "), (" quote ", "Quote "), ("A B", "A\u00a0B ")]
)
def test_source_name_normalisation_matches_boq(rec, asked, real):
    f = add_boq(rec, book([["X", "Sample", "m3", 1, 27]], sheet=real))
    ctx = tool_ctx(rec)
    result = tools_records.evidence(
        ctx,
        rec,
        tools_records.SourceArgs(kind="boq", file_id=f, locator={"sheet": asked, "row": 4}),
    )
    assert result["locator"]["sheet"] == real


async def test_price_item_answer_and_correction_guard(rec):
    from uuid import uuid4

    from qsone.engine.types import Card, answer_value

    ctx = tool_ctx(rec)
    item = json.loads(
        await call(
            "add_item",
            {"kind": "boq_item", "code": "15", "fields": {"description": "Sample", "unit": "m3"}},
            ctx,
        )
    )
    f = add_boq(rec, book([["X", "Sample price", "m3", 1, 27, 28]]))
    src = json.loads(
        await call(
            "add_source", {"kind": "boq", "file_id": f, "locator": {"sheet": "BOQ", "row": 4}}, ctx
        )
    )
    card = Card(
        id=uuid4().hex,
        kind="question",
        title={"en": "Item?", "ar": "أنهي بند؟"},
        detail={"en": "Sample", "ar": "عينة"},
        options=("sent",),
        payload={"questions": [{"id": "item", "text": "Which BOQ item code?", "free_text": True}]},
    )
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    ctx.store.settle(card.id, answer_value(card, "sent", answers={"item": "١٥"}))
    recorded = json.loads(
        await call(
            "record_number",
            {
                "item": item["item_id"],
                "name": "rate",
                "value": "27",
                "unit": "m3",
                "currency": "EGP",
                "source_id": src["source_id"],
            },
            ctx,
        )
    )
    ctx.brief_id = ctx.store.new_brief(rec.id, "Record sample price 28.")
    args = {
        "number_id": recorded["number_id"],
        "value": "28",
        "reason": "Sample correction",
        "source_id": src["source_id"],
        "dated": "2026-11-06",
    }
    with pytest.raises(ModelRetry, match="engineer did not name"):
        await call("correct_number", args, ctx)
    ctx.brief_id = ctx.store.new_brief(rec.id, "صحح سعر البند ١٥")
    assert "number_id" in json.loads(await call("correct_number", args, ctx))


def test_flags_and_imported_rows_match_trimmed_sheet(rec):
    f = add_boq(rec, book([["X", "Sample", "m3", 1]], sheet="تسعير ", white=("B4",)))
    assert boq._flagged(rec, f, "تسعير") == {4}


async def test_discount_fraction_is_sourced_without_item_unit(rec):
    ctx = tool_ctx(rec, answers={"rows": keep_all()})
    f = add_boq(
        rec,
        book(
            [["1", "Sample work", "m3", 1, 100, 100], ["", "خصم 13% - عينة", "", 0.13, "", 13]],
            formats={"D5": "0%"},
        ),
    )
    await run_import(
        ctx,
        f,
        columns={
            "code": "A",
            "description": "B",
            "unit": "C",
            "quantity": "D",
            "rate": "E",
            "amount": "F",
        },
        currency="EGP",
    )
    view = imported.sheet(rec, f)
    discount = view["rows"][1]
    assert discount["cells"]["quantity"]["value"] == "0.13"
    assert "unit" not in discount["cells"]["quantity"]
    loc = view["sources"][discount["cells"]["quantity"]["source"]]["locator"]
    assert (loc["row"], loc["column"]) == (5, "D")


def test_exact_sheet_is_not_confused_with_trimmed_sibling(rec):
    from qsone.records import ledger
    from tests.samples import sample_xlsx

    f = add_boq(rec, sample_xlsx({"Quote ": [["Sample", 27]], "Quote": [["Sample", 28]]}))
    with rec.write("engineer") as c:
        ledger.write_item(
            c,
            at=rec.clock(),
            actor="engineer",
            kind=boq.ITEM,
            code="A",
            fields={"file_id": f, "sheet": "Quote ", "row": 1},
        )
    assert boq._imported_rows(rec, f, "Quote") == set()
    assert boq._imported_rows(rec, f, "Quote ") == {1}
    assert boq._imported_rows(rec, f, " quote ") == set()


def test_card_answer_can_name_the_boq_row(rec):
    from uuid import uuid4

    from qsone.engine.types import Card, answer_value
    from qsone.records import ledger

    ctx = tool_ctx(rec)
    with rec.write("engineer") as c:
        item = ledger.write_item(
            c, at=rec.clock(), actor="engineer", kind=boq.ITEM, code="X", fields={"row": 54}
        )
    card = Card(
        id=uuid4().hex,
        kind="question",
        title={"en": "Sample", "ar": "عينة"},
        detail={"en": "Sample", "ar": "عينة"},
        options=("sent",),
        payload={"questions": [{"id": "row", "text": "Which BOQ row?", "free_text": True}]},
    )
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    ctx.store.settle(card.id, answer_value(card, "sent", answers={"row": "٥٤"}))
    tools_records._price_item_named(ctx, rec, item, "rate")


def test_a_word_is_not_an_item_code_in_a_standalone_price_request(rec):
    from qsone.records import ledger
    from qsone.records.project import RecordsError

    ctx = tool_ctx(rec)
    ctx.brief_id = ctx.store.new_brief(rec.id, "Record a standalone sample price.")
    with rec.write("engineer") as c:
        item = ledger.write_item(
            c, at=rec.clock(), actor="engineer", kind=boq.ITEM, code="A", fields={"row": 54}
        )
    with pytest.raises(RecordsError, match="engineer did not name"):
        tools_records._price_item_named(ctx, rec, item, "rate")


async def scoped_pricing_sample(rec, brief):
    from tests.samples import sample_xlsx

    ctx = tool_ctx(rec)
    f = add_boq(
        rec,
        book(
            [
                ["1-1", "Sample concrete slab C30", "m3", 2],
                ["2-1", "Sample concrete columns C40", "m3", 3],
                ["2-2", "Sample concrete foundation C25", "m3", 4],
            ]
        ),
    )
    ctx.host.answers["rows"] = keep_all()
    await run_import(ctx, f)
    ctx.brief_id = ctx.store.new_brief(rec.id, brief)
    source_file = add_boq(
        rec,
        sample_xlsx(
            {
                "تسعير ": [
                    ["Code", "Description", "Rate"],
                    ["1-1", "Sample concrete slab C30", 27],
                    ["2-1", "Sample concrete columns C40", 28],
                    ["2-2", "Sample concrete foundation C25", 29],
                    ["other", "Unrelated sample paint finish", 30],
                ]
            }
        ),
        name="build-up-sample.xlsx",
    )
    args = []
    for row, code, value in [(2, "1-1", "27"), (3, "2-1", "28"), (4, "2-2", "29")]:
        src = json.loads(
            await call(
                "add_source",
                {
                    "kind": "boq",
                    "file_id": source_file,
                    "locator": {"sheet": "تسعير", "row": row, "column": "C"},
                },
                ctx,
            )
        )
        args.append(
            {
                "item": code,
                "name": "rate",
                "value": value,
                "unit": "m3",
                "currency": "EGP",
                "source_id": src["source_id"],
            }
        )
    return ctx, args


@pytest.mark.parametrize(
    "brief",
    [
        "سعّر المقايسة كلها من شيت التحليل",
        "يرجى تسعير بنود المقايسة من شيت التحليل",
        "price the BOQ from the build-up",
        "rate all items from the build-up",
        "price the items",
        "سعّر البنود",
        "سعّر البنود - عينة",
        "يرجى تسعير الأعمال",
        "عايز الخرسانة اتسعّر من عرض المورد",
        "سعّر بنود الدهانات",
        "price the rebar items",
        "cost the concrete",
        "Please RATE the paint",
        "price section 2",
        "سعّر القسم ٢",
        "price items 2-1, 2-2 from the build-up",
    ],
)
async def test_any_pricing_request_authorises_boq_rates(rec, brief):
    ctx, args = await scoped_pricing_sample(rec, brief)
    for a in args:
        assert "number_id" in json.loads(await call("record_number", a, ctx))


async def test_scope_allows_a_rate_without_matching_source_code(rec):
    ctx, args = await scoped_pricing_sample(rec, "price the BOQ from the build-up")
    wrong = args[0] | {"source_id": args[1]["source_id"], "value": args[1]["value"]}
    assert "number_id" in json.loads(await call("record_number", wrong, ctx))


async def test_record_two_prices_does_not_authorise_scoped_pricing(rec):
    ctx, args = await scoped_pricing_sample(rec, "سجّل السعرين دول")
    for a in args[:2]:
        with pytest.raises(ModelRetry):
            await call("record_number", a, ctx)


@pytest.mark.parametrize("source_code", ["1-1", "own-1"])
async def test_priced_copy_and_description_sources(rec, source_code):
    from tests.samples import sample_xlsx

    ctx, args = await scoped_pricing_sample(rec, "Use my priced copy own-sample.xlsx")
    f = add_boq(
        rec, book([[source_code, "Sample concrete slab C30", "m3", 2, 27]]), name="own-sample.xlsx"
    )
    src = json.loads(
        await call(
            "add_source",
            {"kind": "boq", "file_id": f, "locator": {"sheet": "BOQ", "row": 4, "column": "E"}},
            ctx,
        )
    )
    assert "number_id" in json.loads(
        await call("record_number", args[0] | {"source_id": src["source_id"]}, ctx)
    )
    ctx.brief_id = ctx.store.new_brief(rec.id, "price the BOQ from the build-up")
    f = add_boq(
        rec,
        sample_xlsx(
            {
                "Quote": [
                    ["Supplier code", "Description", "Rate"],
                    ["supplier-X", "Sample concrete columns C40", 28],
                    ["supplier-Y", "Sample concrete foundation C30", 29],
                ]
            }
        ),
        name="quote-sample.xlsx",
    )
    for idx, row in [(1, 2), (2, 3)]:
        src = json.loads(
            await call(
                "add_source",
                {
                    "kind": "boq",
                    "file_id": f,
                    "locator": {"sheet": "Quote", "row": row, "column": "C"},
                },
                ctx,
            )
        )
        a = args[idx] | {"source_id": src["source_id"]}
        assert "number_id" in json.loads(await call("record_number", a, ctx))


async def test_arabic_description_match_in_pricing_scope(rec):
    from qsone.records import ledger
    from tests.samples import sample_xlsx

    ctx = tool_ctx(rec)
    ctx.brief_id = ctx.store.new_brief(rec.id, "يرجى تسعير المقايسة")
    with rec.write("engineer") as c:
        item = ledger.write_item(
            c,
            at=rec.clock(),
            actor="engineer",
            kind=boq.ITEM,
            code="15",
            fields={"description": "خرسانة مسلحة للأسقف", "unit": "m3"},
        )
    f = add_boq(
        rec,
        sample_xlsx(
            {"تسعير ": [["Code", "Description", "Rate"], ["supplier-X", "خرسانه مسلّحه للاسقف", 27]]}
        ),
    )
    src = json.loads(
        await call(
            "add_source",
            {"kind": "boq", "file_id": f, "locator": {"sheet": "تسعير", "row": 2, "column": "C"}},
            ctx,
        )
    )
    assert "number_id" in json.loads(
        await call(
            "record_number",
            {
                "item": item,
                "name": "rate",
                "unit": "m3",
                "currency": "EGP",
                "value": "27",
                "source_id": src["source_id"],
            },
            ctx,
        )
    )


@pytest.mark.parametrize(
    "brief",
    [
        "Record two prices from the BOQ as test prices only",
        "record these two test prices",
        "سجّل السعرين دول من المقايسة",
    ],
)
async def test_recording_prices_mentions_boq_without_requesting_pricing(rec, brief):
    ctx, args = await scoped_pricing_sample(rec, brief)
    with pytest.raises(ModelRetry):
        await call("record_number", args[0], ctx)


def test_record_number_instructions_include_all_pricing_authorisations():
    from qsone.engine.tools import REGISTRY

    instructions = REGISTRY["record_number"].description
    assert "engineer-named item" in instructions
    assert "any pricing request" in instructions
    assert "engineer's own priced copy" in instructions
