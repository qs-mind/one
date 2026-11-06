"""Client BOQ items come only from the engineer's import or an accepted change (the real walk,
6 Nov 2026): an answer about SGH's breakdown wrote its parts into the BOQ as new items, and the
Brissa contract data became «بنود». And "the top 5 items by amount" is one call, not 50.
Synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the records-tools fixtures, imported)

import json

import pytest
from pydantic_ai import ModelRetry

from qsone.engine.tools import call
from qsone.records import ledger
from tests.test_records_tools import ctx, eng  # noqa: F401 - the tools' fixtures


def imported(rec) -> None:
    with rec.write("engineer") as c:
        ledger.write_item(
            c,
            at=rec.clock(),
            actor="engineer",
            kind="boq_item",
            code="01-01-001",
            fields={"description": "خرسانة عادية - عينة", "import_id": "i1"},
        )


def items(rec, kind: str) -> int:
    with rec.read() as c:
        return c.execute("SELECT count(*) FROM items WHERE kind = ?", (kind,)).fetchone()[0]


async def test_an_answer_cannot_add_items_to_an_imported_boq(ctx):
    imported(ctx.rec)
    for kind in ("boq_item", "boq_heading"):
        with pytest.raises(ModelRetry) as refused:
            await call("add_item", {"kind": kind, "code": "01-01-001-a"}, ctx)
        assert "only from the engineer's import" in refused.value.message
    assert items(ctx.rec, "boq_item") == 1 and items(ctx.rec, "boq_heading") == 0
    # a breakdown's parts are resources, and they may be added
    await call("add_item", {"kind": "resource", "fields": {"description": "أسمنت - عينة"}}, ctx)
    assert items(ctx.rec, "resource") == 1


async def test_items_may_be_added_before_any_import(ctx):
    await call("add_item", {"kind": "boq_item", "code": "03/02"}, ctx)
    assert items(ctx.rec, "boq_item") == 1


def priced(rec, rows) -> None:
    """Client BOQ items, as an import writes them: (code, amount or None), each amount sourced
    to its cell."""
    with rec.write("engineer") as c:
        at = rec.clock()
        for i, (code, amount) in enumerate(rows, start=2):
            fields = {"description": f"بند {code} - عينة", "import_id": "i1"}
            item = ledger.write_item(
                c, at=at, actor="engineer", kind="boq_item", code=code, fields=fields
            )
            if amount is None:
                continue
            where = {"sheet": "BOQ", "row": i, "column": "F"}
            source = ledger.write_source(
                c, at=at, actor="engineer", kind="boq", title="مقايسة - عينة", locator=where
            )
            ledger.write_number(
                c,
                at=at,
                actor="engineer",
                item_id=item,
                name="amount",
                value=amount,
                source_id=source,
                dated="2026-11-01",
                currency="EGP",
            )


async def test_the_top_items_in_one_call_with_their_sources(ctx):
    # SGH, 6 Nov 2026: "top 5 by amount" took 50 calls of ledger_numbers and failed
    rows = [("A1", "900.50"), ("A2", "12000"), ("A3", None), ("A4", "1500"), ("A5", "80")]
    priced(ctx.rec, rows)
    out = json.loads(await call("rank_items", {"top": 2}, ctx))
    assert [i["code"] for i in out["items"]] == ["A2", "A4"]
    first = out["items"][0]
    assert first["value"] == "12000" and first["currency"] == "EGP" and first["number_id"]
    assert first["source"]["locator"]["row"] == 3 and first["description"] == "بند A2 - عينة"
    assert out["with_number"] == 4 and out["missing"] == {"count": 1, "codes": ["A3"]}
    low = json.loads(await call("rank_items", {"top": 1, "order": "lowest"}, ctx))
    assert [i["code"] for i in low["items"]] == ["A5"]
