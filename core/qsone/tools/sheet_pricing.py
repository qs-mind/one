"""Price existing BOQ items from explicit build-up cells; no AI arithmetic or item creation."""

import asyncio
import json
import re

from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.calc import engine, resolve
from qsone.calc.spec import CalcRequest
from qsone.deliverables import store
from qsone.engine.tools import ModelRetry, Tool, ToolContext, register
from qsone.engine.tools_records import SourceArgs, _pricing_requested, evidence
from qsone.engine.types import Data
from qsone.records import boq, ledger


class PricingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str = Field(min_length=1, max_length=100)
    row: int = Field(ge=1, le=1_048_576)
    columns: list[str] = Field(min_length=1, max_length=64)


class PricingArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1, max_length=64)
    sheet: str = Field(min_length=1, max_length=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    title: str = Field(min_length=1, max_length=300)
    rows: list[PricingRow] = Field(min_length=1, max_length=1000)
    language: str = Field(default="ar", pattern=r"^(ar|en)$")
    reason: str = Field(
        default="Price from the mapped build-up cells", min_length=1, max_length=300
    )


EXAMPLE = {
    "file_id": "<file id>",
    "sheet": "Build-up",
    "currency": "EGP",
    "title": "Priced BOQ",
    "language": "en",
    "rows": [{"item": "03/02", "row": 18, "columns": ["C", "D", "O"]}],
}

DOC = """Price existing client BOQ items from a workbook's explicit per-unit cost cells.
Read files_list and files_read first: sheet names, descriptions, units and components. Map each
item id/code to its actual build-up row; do not match by row number or assume codes align.
rows: [{item, row, columns}]. columns contains either ONE quoted unit-rate column, or ALL
per-unit cost components to sum. Never include a total AND its components. Do not pass raw
resource prices/quantities here: record those and use calculate for their products first.
No typed numeric values are accepted: ONE reads the cells and keeps each source. Missing,
hidden, nonnumeric or duplicate cells/items refuse the entire call with no writes.
ONE sums components with calculate, saves rates, then creates a priced Sheet Deliverable from
the existing items in the supplied order; its amounts and total use the Calc Engine. It does
not import or add client items. Map all items for whole-BOQ pricing. Existing rates are replaced
with reason, preserving history. Incomplete mapping produces a partial Deliverable; report how
many items remain. Every later edit to a Deliverable uses deliverable_propose.
Example: """ + json.dumps(EXAMPLE)


def price(ctx: ToolContext, args: PricingArgs) -> dict:
    rec = ctx.rec
    if rec is None:
        raise ModelRetry("Open a project first.")
    said = ctx.store.brief(ctx.brief_id)["text"]
    if not _pricing_requested(said):
        raise ModelRetry("The engineer must request pricing before BOQ rates are changed.")
    book = boq.workbook(rec, args.file_id)
    _, sheet = boq.read(book, args.sheet)  # refusal lists actual names
    actor = ctx.agent.name["en"]
    mapped, seen = [], set()
    # Validate every mapping before writing anything, including explicit units and quantities.
    with rec.read() as conn:
        for entry in args.rows:
            item = resolve.find_item(conn, entry.item)
            if item["kind"] != "boq_item" or not item["fields"].get("import_id"):
                raise ModelRetry(
                    "Use existing imported client BOQ items; do not create replacements."
                )
            if item["id"] in seen:
                raise ModelRetry("An item may appear only once in this pricing call.")
            seen.add(item["id"])
            qty = resolve.current_number(conn, item["id"], "quantity")
            unit = qty.get("unit")
            if not unit:
                raise ModelRetry("The existing BOQ quantity needs its unit before pricing.")
            columns = [c.strip().upper() for c in entry.columns]
            if len(columns) != len(set(columns)) or any(
                not re.fullmatch(r"[A-Z]{1,3}", c) for c in columns
            ):
                raise ModelRetry("Give distinct column letters, for example C, D, O.")
            cells = []
            for col in columns:
                index = boq.column(col)
                cell = sheet.cells.get(entry.row, {}).get(index)
                if entry.row in sheet.hidden_rows or index in sheet.hidden_columns or cell is None:
                    raise ModelRetry(
                        f"Cell {col}{entry.row} is missing or hidden; "
                        "read the sheet and map it again."
                    )
                value, why = boq.exact(cell.value, cell.fmt)
                if value is None:
                    raise ModelRetry(
                        f"Cell {col}{entry.row} is not an exact numeric cost ({why}); "
                        "map the actual per-unit cost cells."
                    )
                loc = {"sheet": sheet.name, "row": entry.row, "column": col}
                source = evidence(
                    ctx, rec, SourceArgs(kind="quote", file_id=args.file_id, locator=loc)
                )
                cells.append((col, value, source))
            mapped.append((item, unit, cells))
    outputs = []
    with rec.write(actor) as conn:
        for item, unit, cells in mapped:
            ids = []
            for col, value, source in cells:
                source_id = ledger.write_source(conn, at=rec.clock(), actor=actor, **source)
                ids.append(
                    ledger.write_number(
                        conn,
                        at=rec.clock(),
                        actor=actor,
                        item_id=item["id"],
                        name=f"build_up_{col}",
                        value=value,
                        unit=unit,
                        currency=args.currency,
                        source_id=source_id,
                        dated=source["dated"],
                    )
                )
            if len(ids) == 1:
                _, value, source = cells[0]
                outputs.append(
                    ledger.write_number(
                        conn,
                        at=rec.clock(),
                        actor=actor,
                        item_id=item["id"],
                        name="rate",
                        value=value,
                        unit=unit,
                        currency=args.currency,
                        source_id=source_id,
                        dated=source["dated"],
                    )
                )
                continue
            request = CalcRequest.model_validate(
                {
                    "formula": "sum(parts)",
                    "inputs": {"parts": {"numbers": ids}},
                    "item": item["id"],
                    "result": {"unit": f"{args.currency}/{unit}"},
                    "save": {"name": "rate", "reason": args.reason},
                }
            )
            result = engine.calculate(rec, request, actor=actor)
            outputs.append(result.results[0].number)
        deliverable = store.create(
            rec,
            kind="sheet",
            variant="boq",
            title=args.title,
            language=args.language,
            actor=actor,
            rows=[{"item_id": item["id"]} for item, _, _ in mapped],
            off_desk=True,
        )
        total = conn.execute("SELECT count(*) FROM items WHERE kind='boq_item'").fetchone()[0]
    return {
        "id": deliverable,
        "priced": len(mapped),
        "remaining": total - len(mapped),
        "rates": outputs,
    }


async def run(ctx: ToolContext, args: PricingArgs) -> str:
    out = await asyncio.to_thread(price, ctx, args)
    ctx.host.emit(Data(ctx.brief_id, "deliverable", out["id"], {"id": out["id"]}))
    return json.dumps(out)


register(
    Tool(
        name="boq_price_from_sheet",
        description=DOC,
        args=PricingArgs,
        risk="write",
        run=run,
        activity=lambda a: copy.TOOL_PRICE_FROM_SHEET,
        writes=True,
        example=EXAMPLE,
        roles=frozenset({"lead", "specialist"}),
        group="boq",
    )
)
