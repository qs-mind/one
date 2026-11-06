"""Client BOQ items come only from the engineer's import or an accepted change (the real walk,
6 Nov 2026): an answer about SGH's breakdown wrote its parts into the BOQ as new items, and the
Brissa contract data became «بنود». Synthetic «عينة» data only; no real AI."""

# ruff: noqa: F811 (the records-tools fixtures, imported)

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
