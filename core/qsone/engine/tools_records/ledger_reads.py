"""Reading the Source Ledger: `find_items`, `ledger_numbers` and `rank_items`."""

import asyncio
import json
from decimal import Decimal
from typing import Literal

from pydantic import Field

from qsone.calc import resolve
from qsone.engine.tools import ToolContext
from qsone.engine.tools_records.shared import _Args, _json, _project
from qsone.records.project import Records

_ITEMS_PER_PAGE = 50


# Reading the Source Ledger ---------------------------------------------------------------------


class FindArgs(_Args):
    code: str | None = Field(None, min_length=1, max_length=100)
    code_prefix: str | None = Field(None, min_length=1, max_length=100)
    kind: str | None = Field(None, min_length=1, max_length=64)
    page: int = Field(1, ge=1)


_FIND_EXAMPLE = {"code_prefix": "03/", "kind": "boq_item"}

_FIND_DOC = f"""Find ledger items by exact code, code_prefix or kind (boq_item/resource/section,
or project kind); omit filters for all. Returns id/kind/code/fields, count and {_ITEMS_PER_PAGE}
items per page in code order. ledger_numbers reads their numbers."""


def _find(rec: Records, args: FindArgs) -> str:
    where, values = ["kind != ?"], [resolve.UNIT_KIND]
    if args.code is not None:
        where.append("code = ?")
        values.append(args.code)
    if args.code_prefix is not None:
        where.append("substr(code, 1, ?) = ?")
        values += [len(args.code_prefix), args.code_prefix]
    if args.kind is not None:
        where.append("kind = ?")
        values.append(args.kind)
    sql = " AND ".join(where)
    with rec.read() as conn:
        (count,) = conn.execute(f"SELECT count(*) FROM items WHERE {sql}", values).fetchone()
        rows = conn.execute(
            f"SELECT id, kind, code, fields FROM items WHERE {sql}"
            " ORDER BY code, created_at, id LIMIT ? OFFSET ?",
            [*values, _ITEMS_PER_PAGE, (args.page - 1) * _ITEMS_PER_PAGE],
        ).fetchall()
    items = [{"id": i, "kind": k, "code": c, "fields": json.loads(f)} for i, k, c, f in rows]
    return _json({"items": items, "count": count, "page": args.page})


async def _find_items(ctx: ToolContext, args: FindArgs) -> str:
    return await asyncio.to_thread(_find, _project(ctx), args)


class ItemArgs(_Args):
    item: str = Field(min_length=1, max_length=100)


_NUMBERS_EXAMPLE = {"item": "03/02"}

_NUMBERS_DOC = """Read current numbers for item id/code: id, name, exact value, unit, currency,
date and source (id/title/kind/file_id/locator). Includes corrections instead of replaced values.
Use number ids in calculate/Deliverables, never retype values."""


def _numbers(rec: Records, ref: str) -> str:
    with rec.read() as conn:
        item = resolve.find_item(conn, ref, field="item")
        rows = conn.execute(
            "SELECT n.id, n.name, n.value, n.unit, n.currency, n.dated, n.replaces,"
            " s.id, s.kind, s.title, s.file_id, s.locator"
            " FROM numbers n JOIN sources s ON s.id = n.source_id"
            " WHERE n.item_id = ? AND n.valid_until IS NULL ORDER BY n.recorded_at, n.rowid",
            (item["id"],),
        ).fetchall()
    numbers = [
        {
            "id": n_id,
            "name": name,
            "value": value,
            "unit": unit,
            "currency": currency,
            "dated": dated,
            "replaces": replaces,
            "source": {
                "id": s_id,
                "kind": kind,
                "title": title,
                "file_id": f_id,
                "locator": json.loads(loc),
                "dated_how": json.loads(loc).get("dated_how"),
            },
        }
        for n_id, name, value, unit, currency, dated, replaces, s_id, kind, title, f_id, loc in rows
    ]
    return _json({"item": {"id": item["id"], "code": item["code"]}, "numbers": numbers})


async def _ledger_numbers(ctx: ToolContext, args: ItemArgs) -> str:
    return await asyncio.to_thread(_numbers, _project(ctx), args.item)


class RankArgs(_Args):
    name: str = Field("amount", min_length=1, max_length=64)
    top: int = Field(10, ge=1, le=50)
    order: Literal["highest", "lowest"] = "highest"
    kind: str = Field("boq_item", min_length=1, max_length=64)
    code_prefix: str | None = Field(None, min_length=1, max_length=100)


_RANK_EXAMPLE = {"name": "amount", "top": 5}

_RANK_DOC = """Rank current item numbers. name: amount (default), rate, quantity or another;
top: 1–50; order: highest/lowest; kind: boq_item (default); code_prefix: optional section.
Returns code, description, number_id, exact value, unit, currency, source, plus missing-number
count/first codes. Totals use calculate with number_ids."""

_MISSING_SHOWN = 10


def _rank(rec: Records, args: RankArgs) -> str:
    where, values = ["i.kind = ?"], [args.kind]
    if args.code_prefix is not None:
        where.append("substr(i.code, 1, ?) = ?")
        values += [len(args.code_prefix), args.code_prefix]
    sql = " AND ".join(where)
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT i.id, i.code, i.fields, n.id, n.value, n.unit, n.currency, n.dated,"
            " s.id, s.kind, s.title, s.file_id, s.locator FROM items i"
            " JOIN numbers n ON n.item_id = i.id AND n.name = ? AND n.valid_until IS NULL"
            f" JOIN sources s ON s.id = n.source_id WHERE {sql}",
            (args.name, *values),
        ).fetchall()
        missing = conn.execute(
            f"SELECT i.code FROM items i WHERE {sql} AND NOT EXISTS (SELECT 1 FROM numbers n"
            " WHERE n.item_id = i.id AND n.name = ? AND n.valid_until IS NULL)"
            " ORDER BY i.code COLLATE NOCASE, i.rowid",
            (*values, args.name),
        ).fetchall()

    def size(row) -> Decimal:
        try:
            return Decimal(str(row[4]))
        except ArithmeticError:
            return Decimal("-Infinity") if args.order == "highest" else Decimal("Infinity")

    rows.sort(key=size, reverse=args.order == "highest")
    found = []
    for item_id, code, fields, n_id, value, unit, currency, dated, *source in rows[: args.top]:
        s_id, kind, title, f_id, loc = source
        found.append(
            {
                "item_id": item_id,
                "code": code,
                "description": json.loads(fields).get("description"),
                "number_id": n_id,
                "value": value,
                "unit": unit,
                "currency": currency,
                "dated": dated,
                "source": {
                    "id": s_id,
                    "kind": kind,
                    "title": title,
                    "file_id": f_id,
                    "locator": json.loads(loc),
                },
            }
        )
    gaps = {"count": len(missing), "codes": [c for (c,) in missing[:_MISSING_SHOWN]]}
    return _json({"items": found, "with_number": len(rows), "missing": gaps})


async def _rank_items(ctx: ToolContext, args: RankArgs) -> str:
    return await asyncio.to_thread(_rank, _project(ctx), args)
