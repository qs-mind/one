"""`add_item`: a new item in the Source Ledger."""

import asyncio

from pydantic import Field

from qsone import copy
from qsone.calc import resolve
from qsone.engine.tools import ModelRetry, ToolContext
from qsone.engine.tools_records.shared import (
    _ENGINEER_REFUSED,
    Where,
    _actor,
    _Args,
    _engineer_ok,
    _json,
    _target,
)
from qsone.records import keep, ledger
from qsone.records.project import Records, RecordsError

_CLIENT_KINDS = ("boq_item", "boq_heading")  # the client's BOQ: from an import or a change


class NewItemArgs(_Args):
    kind: str = Field(min_length=1, max_length=64)
    code: str | None = Field(None, min_length=1, max_length=100)
    fields: dict = Field(default_factory=dict)
    where: Where = "project"


_ITEM_EXAMPLE = {
    "kind": "boq_item",
    "code": "03/02",
    "fields": {"description": "Reinforced concrete for slabs", "unit": "m3"},
}

_ITEM_DOC = f"""Add an item to the Source Ledger: a BOQ item, a resource (a material, labour, \
plant) or a section. Look for it first with find_items: an item is added once.
- kind: resource, section, extra_item (not in the client's BOQ), or another; boq_item \
only before an import. Units: define_unit.
- code: its code as written in the BOQ. fields: its description and other words, never its \
numbers: those go in record_number, each with its source.
- where: engineer to keep it for every project (asks the engineer once).
Personal data (phones, emails, names, addresses, ID numbers) is kept only if the engineer says \
so. Returns item_id.
Example:
{_json(_ITEM_EXAMPLE)}"""


def _add_item(rec: Records, args: NewItemArgs, fields: dict, actor: str) -> str:
    values = args.model_dump(exclude={"where"}) | {"fields": fields}
    with rec.write(actor) as conn:
        return ledger.write_item(conn, at=rec.clock(), actor=actor, **values)


def _imported(rec: Records) -> bool:
    """Whether the project has a client BOQ from the engineer's import."""
    with rec.read() as c:
        found = c.execute(
            "SELECT 1 FROM items WHERE kind IN ('boq_item', 'boq_heading')"
            " AND json_extract(fields, '$.import_id') IS NOT NULL LIMIT 1"
        ).fetchone()
    return found is not None


async def _add_item_tool(ctx: ToolContext, args: NewItemArgs) -> str:
    if args.kind == resolve.UNIT_KIND:
        raise ModelRetry("add_item: a unit is defined with define_unit, not as an item.")
    target = _target(ctx, args.where)
    if args.kind in _CLIENT_KINDS and await asyncio.to_thread(_imported, target):
        # an answer wrote a breakdown's parts and a contract's data as client items (6 Nov 2026)
        raise RecordsError(copy.CLIENT_ITEMS_IMPORTED, status=422, field="kind")
    if args.where == "engineer" and not await _engineer_ok(ctx, copy.TOOL_ADD_ITEM):
        return _ENGINEER_REFUSED
    fields, dropped = await keep.apply(ctx, args.fields)
    item_id = await asyncio.to_thread(_add_item, target, args, fields, _actor(ctx))
    out: dict = {"item_id": item_id, "where": args.where}
    if dropped:
        out |= {"not_kept": list(dropped), "note": " ".join(keep.dropped_note(dropped))}
    return _json(out)
