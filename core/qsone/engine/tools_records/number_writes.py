"""`record_number` and `correct_number`: a sourced number in the Source Ledger, and its
correction."""

import asyncio

from pydantic import Field

from qsone import copy
from qsone.calc import resolve
from qsone.calc.errors import CalcError
from qsone.engine.tools import ToolContext
from qsone.engine.tools_records.number_checks import _check_number
from qsone.engine.tools_records.pricing_intent import _price_item_named
from qsone.engine.tools_records.shared import (
    _DATE,
    _ENGINEER_REFUSED,
    Where,
    _actor,
    _Args,
    _engineer_ok,
    _field,
    _json,
    _project,
    _target,
)
from qsone.records import ledger
from qsone.records.project import Records, RecordsError


class NumberArgs(_Args):
    item: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(None, max_length=64)
    currency: str | None = Field(None, max_length=3)
    source_id: str = Field(min_length=1, max_length=64)
    dated: str | None = Field(None, pattern=_DATE)
    where: Where = "project"


_NUMBER_EXAMPLE = {
    "item": "03/02",
    "name": "rate",
    "value": "39850.50",
    "unit": "m3",
    "currency": "EGP",
    "source_id": "<source id>",
}

_NUMBER_DOC = f"""Record sourced numbers; calculations use calculate. item: id/code; name:
quantity/rate/amount/price/other. value: exact decimal source text, no thousands separators.
unit required for quantities/rates (m3 for EGP/m3); currency: three letters for rates/amounts.
source_id: add_source; dated: YYYY-MM-DD, defaults to source date; where=engineer: Engineer Records.
BOQ rates need an engineer-named item/code/row/card, any pricing request or
engineer's own priced copy; otherwise prices_propose/resource. Returns number_id; no duplicates.
Example:
{_json(_NUMBER_EXAMPLE)}"""


def _record(rec: Records, args: NumberArgs, actor: str) -> str:
    with rec.write(actor) as conn:
        item = resolve.find_item(conn, args.item, field="item")
        dated = args.dated
        if dated is None:
            source = conn.execute(
                "SELECT dated FROM sources WHERE id = ?", (args.source_id,)
            ).fetchone()
            if source is None:
                raise RecordsError(copy.NUMBER_NEEDS_SOURCE, status=422, field="source_id")
            dated = source[0]
        number_id = ledger.write_number(
            conn,
            at=rec.clock(),
            actor=actor,
            item_id=item["id"],
            name=args.name,
            value=args.value,
            source_id=args.source_id,
            dated=dated,
            unit=args.unit,
            currency=args.currency,
        )  # its own checks first (the value's form, the source), then what the source says
        _check_number(conn, item, args.name, args.value, args.unit, args.source_id)
    return _json({"number_id": number_id})


async def _record_number(ctx: ToolContext, args: NumberArgs) -> str:
    target = _target(ctx, args.where)
    await asyncio.to_thread(_price_item_named, ctx, target, args.item, args.name, args.source_id)
    if args.where == "engineer":
        action = copy.fill(copy.TOOL_RECORD_NUMBER, name=_field(args.name), item=args.item)
        if not await _engineer_ok(ctx, action):
            return _ENGINEER_REFUSED
    return await asyncio.to_thread(_record, target, args, _actor(ctx))


class CorrectionArgs(_Args):
    number_id: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=300)
    source_id: str = Field(min_length=1, max_length=64)
    dated: str = Field(pattern=_DATE)
    unit: str | None = Field(None, max_length=64)
    currency: str | None = Field(None, max_length=3)


_CORRECTION_EXAMPLE = {
    "number_id": "<number id>",
    "value": "41200.00",
    "reason": "the supplier's new quote",
    "source_id": "<source id>",
    "dated": "2026-11-04",
}

_CORRECTION_DOC = f"""Correct a number in the Source Ledger. Numbers are never changed or \
deleted: the correction is a new entry with its reason and source, and the old one is kept, \
marked as replaced. Calculations that used it then show as out of date (recalculate).
- number_id: the current entry. value: exact text, as in record_number. reason: why.
- unit, currency: only when they change; they default to the old entry's.
Returns the new number_id.
Example:
{_json(_CORRECTION_EXAMPLE)}"""


def _correct(rec: Records, args: CorrectionArgs, actor: str) -> str:
    with rec.write(actor) as conn:
        old = conn.execute(
            "SELECT item_id, name, unit FROM numbers WHERE id = ?", (args.number_id,)
        ).fetchone()
        if old is None:
            raise CalcError("CALC_NUMBER_NOT_FOUND", field="number_id", ref=args.number_id)
        new_id = ledger.write_correction(
            conn,
            args.number_id,
            at=rec.clock(),
            actor=actor,
            value=args.value,
            reason=args.reason,
            source_id=args.source_id,
            dated=args.dated,
            unit=args.unit,
            currency=args.currency,
        )
        item = resolve.find_item(conn, old[0], field="number_id")
        _check_number(conn, item, old[1], args.value, args.unit or old[2], args.source_id)
    return _json({"number_id": new_id, "replaces": args.number_id})


async def _correct_number(ctx: ToolContext, args: CorrectionArgs) -> str:
    target = _project(ctx)
    with target.read() as conn:
        old = conn.execute(
            "SELECT item_id, name FROM numbers WHERE id = ?", (args.number_id,)
        ).fetchone()
    if old:
        await asyncio.to_thread(_price_item_named, ctx, target, old[0], old[1], args.source_id)
    return await asyncio.to_thread(_correct, target, args, _actor(ctx))
