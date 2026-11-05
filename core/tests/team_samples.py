"""Helpers for the team tests (Plan 4, Task 7). Synthetic «عينة» data only; no real AI.

- `TeamFakeHost`: `FakeHost` with the `setup` the Brief Runner gives the team tools.
- `lead_ctx(rec, host)`: a Brief in the sample project, with the Lead QS's run and context.
- `sample_ledger(ctx)`: a source, item 03/02, its quantity and rate, and their calculated amount.
- `quote_source(rec)`: add_source's arguments for a sample supplier quote file in `rec` (Plan 5:
  a source points at real evidence).
"""

import json
from dataclasses import dataclass, field

from qsone.engine import roles
from qsone.engine.agents import lead_spec
from qsone.engine.data_text import new_fence
from qsone.engine.store import Store
from qsone.engine.team import TeamSetup
from qsone.engine.tools import ToolContext, call
from qsone.records.files import add_file
from tests.engine_fakes import OPUS, SAMPLE_SHEET, FakeHost
from tests.samples import sample_xlsx

BRIEF = "سعّر البنود - عينة"
DATED = "2026-11-02"
QUOTE = "عرض سعر - عينة.xlsx"


def quote_source(rec) -> dict:
    """add_source's arguments for row 1 of a sample supplier quote in `rec`, added once."""
    with rec.read() as c:
        found = c.execute("SELECT id FROM files WHERE name = ?", (QUOTE,)).fetchone()
    if found is None:
        rows = [["حديد تسليح - عينة", "طن", "39850.50"]]
        found = (add_file(rec, QUOTE, sample_xlsx({"Quote": rows}), actor="engineer").id,)
    locator = {"sheet": "Quote", "row": 1}
    source = {"kind": "quote", "title": "عرض سعر - عينة", "file_id": found[0]}
    return source | {"locator": locator, "dated": DATED}


@dataclass
class TeamFakeHost(FakeHost):
    setup: TeamSetup = field(
        default_factory=lambda: TeamSetup(tuple(SAMPLE_SHEET), roles.defaults(SAMPLE_SHEET))
    )


def lead_ctx(rec, host: FakeHost, *, brief_text: str = BRIEF) -> ToolContext:
    store = Store(rec, project_id=rec.id)
    brief = store.new_brief(rec.id, brief_text)
    host.brief_id = brief
    spec = lead_spec()
    run = store.new_run(brief, spec, OPUS.choice, None)
    return ToolContext(
        brief_id=brief, run_id=run, agent=spec, rec=rec, store=store, host=host, fence=new_fence()
    )


async def sample_ledger(ctx: ToolContext) -> dict:
    """Ids of a sample source, item 03/02, its quantity (120 m3), rate (39850.50 EGP per m3)
    and their amount, calculated and saved."""

    async def ids(tool: str, args: dict) -> dict:
        return json.loads(await call(tool, args, ctx))

    source = (await ids("add_source", quote_source(ctx.rec)))["source_id"]
    item = (await ids("add_item", {"kind": "boq_item", "code": "03/02"}))["item_id"]
    number = {"item": "03/02", "source_id": source, "dated": DATED}
    quantity = (
        await ids("record_number", number | {"name": "quantity", "value": "120", "unit": "m3"})
    )["number_id"]
    rate = (
        await ids(
            "record_number",
            number | {"name": "rate", "value": "39850.50", "unit": "m3", "currency": "EGP"},
        )
    )["number_id"]
    calc = await ids(
        "calculate",
        {
            "formula": "quantity * rate",
            "item": "03/02",
            "result": {"unit": "EGP"},
            "save": {"name": "amount"},
        },
    )
    [result] = calc["results"]
    return {
        "source": source,
        "item": item,
        "quantity": quantity,
        "rate": rate,
        "amount": result["number"],
        "calc": result["calculation"],
        "amount_value": result["value"],
    }
