"""Sample build-up cells price existing imported items, without re-importing a BOQ."""

import json

import pytest
from pydantic_ai import ModelRetry

from qsone.engine.tools import call
from qsone.records import ledger
from qsone.records.files import add_file
from tests.fakes_tools import tool_ctx
from tests.samples import sample_xlsx

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "columns,rate_value,total_value,source_kind",
    [
        (["B", "C"], "120.00", "240.00", "calculation"),
        (["B"], "100", "200.00", "quote"),
    ],
)
async def test_build_up_to_priced_deliverable(rec, columns, rate_value, total_value, source_kind):
    import qsone.tools  # noqa: F401
    from qsone.deliverables.api import current_view

    file = add_file(
        rec,
        "sample.xlsx",
        sample_xlsx(
            {
                "Build-up ": [
                    ["Description", "Material", "Labour"],
                    ["Sample concrete", 100, 20],
                ]
            }
        ),
        actor="t",
    ).id
    with rec.write("t") as conn:
        item = ledger.write_item(
            conn,
            at=rec.clock(),
            actor="t",
            kind="boq_item",
            code="01",
            fields={"description": "Sample concrete", "unit": "m3", "import_id": "sample"},
        )
        source = ledger.write_source(
            conn,
            at=rec.clock(),
            actor="t",
            kind="boq",
            title="Sample quantity",
            locator={},
            dated="2026-11-06",
        )
        ledger.write_number(
            conn,
            at=rec.clock(),
            actor="t",
            item_id=item,
            name="quantity",
            value="2",
            unit="m3",
            source_id=source,
            dated="2026-11-06",
        )
    ctx = tool_ctx(rec)
    payload = {
        "file_id": file,
        "sheet": "Build-up",
        "currency": "EGP",
        "title": "Sample priced BOQ",
        "rows": [{"item": item, "row": 2, "columns": columns}],
    }
    out = json.loads(await call("boq_price_from_sheet", payload, ctx))
    view = current_view(rec, out["id"])
    assert view["total"]["value"] == total_value
    rate = next(r for r in view["rows"] if r["kind"] == "item")["cells"]["rate"]
    assert rate["value"] == rate_value
    assert view["sources"][rate["source"]]["kind"] == source_kind
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM items WHERE kind='boq_item'").fetchone()[0] == 1
        locs = [
            json.loads(r[0]) for r in conn.execute("SELECT locator FROM sources WHERE kind='quote'")
        ]
    assert {loc["column"] for loc in locs} == set(columns)
    assert all(loc["sheet"] == "Build-up " and loc["row"] == 2 for loc in locs)


async def test_missing_sheet_lists_actual_names_and_writes_nothing(rec):
    import qsone.tools  # noqa: F401

    file = add_file(rec, "sample.xlsx", sample_xlsx({"Build-up ": [["Sample", 100]]}), actor="t").id
    ctx = tool_ctx(rec)
    with pytest.raises(ModelRetry, match="Build-up"):
        await call(
            "boq_price_from_sheet",
            {
                "file_id": file,
                "sheet": "invented",
                "currency": "EGP",
                "title": "Sample",
                "rows": [{"item": "missing", "row": 1, "columns": ["B"]}],
            },
            ctx,
        )
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM numbers").fetchone()[0] == 0
