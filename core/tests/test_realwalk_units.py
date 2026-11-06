"""A number keeps its unit (the real walk, 6 Nov 2026): the delay damages «0.2 %» lost "per day",
which is the whole of their meaning. Synthetic «عينة» files only; no real AI."""

# ruff: noqa: F811 (the fixtures, imported)

import json

import pytest
from pydantic_ai import ModelRetry

from qsone.engine import truth
from qsone.engine.tools import call
from qsone.records.files import add_file
from tests.samples import sample_pdf
from tests.test_records_tools import ctx, eng  # noqa: F401 - the tools' fixtures

TERMS = sample_pdf(
    [
        ["Bid security: USD 350,000 - SAMPLE"],
        ["Delay damages: 0.2% of the Contract Price per day, up to 10% - SAMPLE"],
    ]
)


@pytest.fixture
async def page(ctx):
    file_id = add_file(ctx.rec, "terms - sample.pdf", TERMS, actor="engineer").id
    source = {"kind": "contract", "file_id": file_id, "locator": {"page": 2}}
    out = json.loads(await call("add_source", source, ctx))
    await call("add_item", {"kind": "condition", "code": "delay"}, ctx)
    return out["source_id"]


async def test_a_rate_per_day_keeps_its_day(ctx, page):
    number = {"item": "delay", "name": "delay_damages", "value": "0.2", "source_id": page}
    with pytest.raises(ModelRetry) as refused:
        await call("record_number", number | {"unit": "%"}, ctx)
    assert "per day" in refused.value.message
    await call("record_number", number | {"unit": "% per day"}, ctx)
    # the cap beside it is no rate per day
    await call("record_number", number | {"name": "cap", "value": "10", "unit": "%"}, ctx)


async def test_a_reply_keeps_the_day(ctx, page):
    with ctx.rec.read() as c:
        [found] = truth.miscited(c, "غرامة التأخير 0.2% من قيمة العقد (صفحة 2).")
        assert "per day" in found.fix and "كل يوم" in found.flag["ar"]
        assert truth.miscited(c, "غرامة التأخير 0.2% عن كل يوم تأخير (صفحة 2).") == []
        assert truth.miscited(c, "Delay damages 0.2% per day (page 2).") == []
