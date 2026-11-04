"""The ledger side of the engine: project units, items, selectors and the inputs a formula reads.

Project units are Source Ledger items of kind `unit`: the code is the symbol, and its one current
number `equals` holds the size (50 with unit `kg`), with a source and a date. Every input becomes
exact `Quantity` values, and every ledger number read is listed in `used` for `calc_inputs`.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from qsone.calc.errors import CalcError
from qsone.calc.spec import (
    CalcRequest,
    Constant,
    EachRef,
    ListRef,
    NumberRef,
    Selector,
    SlotRef,
    UnitRequest,
)
from qsone.calc.units import Unit, UnitTable
from qsone.records import ledger
from qsone.records.project import Records, RecordsError

UNIT_KIND = "unit"  # items of this kind are unit definitions; code = symbol, number "equals"
EQUALS = "equals"
_CHOICES = 10  # ids listed in an ambiguity refusal
_CODES = 20  # item codes listed in a missing-number refusal

_ITEM_COLUMNS = "id, kind, code, fields"
_NUMBER_COLUMNS = "id, item_id, name, value, unit, currency, source_id, dated, valid_until"


# The shapes evaluate() reads (Task 4 defines them in evaluate.py with the same fields; when it
# merges, these two become `from qsone.calc.evaluate import Input, Quantity`).
@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: Unit


@dataclass(frozen=True)
class Input:
    name: str
    values: tuple[Quantity, ...]  # one, or many for a list
    is_list: bool
    origin: Literal["ledger", "constant"]


@dataclass(frozen=True)
class Resolved:
    inputs: dict[str, Input]  # for evaluate()
    used: list[tuple[str, int, str]]  # (name, seq, number id) for calc_inputs
    request: dict  # the resolved request: item ids, every name explicit
    dated: str | None  # newest input date
    skipped: list[str]  # item codes skipped (skip_missing)
    from_item: list[str]  # bare names read from the item


# Project units.


def unit_table(conn) -> UnitTable:
    """The built-ins, the project's current unit definitions and the ledger's currencies."""
    return UnitTable(_definitions(conn), currencies=_currencies(conn))


def define_unit(rec: Records, req: UnitRequest, *, actor: str) -> str:
    """Writes `symbol` = `equals` as a Source Ledger number and returns its id.

    A second definition of the same symbol needs `req.reason` and corrects the first, so the old
    size still answers `as_of`."""
    value, text = _equals(req.equals)
    symbol = req.symbol
    with rec.write(actor) as conn:
        defined, currencies = _definitions(conn), _currencies(conn)
        same = [s for s in defined if s != symbol and s.casefold() == symbol.casefold()]
        if same:
            raise CalcError("CALC_UNIT_CASE", field="symbol", symbol=symbol, existing=same[0])
        _check(lambda: UnitTable({symbol: (Decimal(1), "kg", "")}, currencies=currencies), "symbol")
        if UnitTable(currencies=currencies).is_currency(symbol.upper()):
            raise CalcError("CALC_UNIT_CURRENCY", field="symbol", symbol=symbol)
        defined[symbol] = (Decimal(value), text, "")
        _check(lambda: UnitTable(defined, currencies=currencies), "equals")

        at = rec.clock()
        found = conn.execute(
            "SELECT id FROM items WHERE kind = ? AND code = ? ORDER BY created_at, id",
            (UNIT_KIND, symbol),
        ).fetchone()
        if found is None:
            item_id = ledger.write_item(conn, at=at, actor=actor, kind=UNIT_KIND, code=symbol)
        else:
            item_id = found[0]
            current = _current(conn, item_id, EQUALS)
            if current:
                return ledger.write_correction(
                    conn,
                    current[-1]["id"],
                    at=at,
                    actor=actor,
                    value=value,
                    reason=req.reason,
                    source_id=req.source_id,
                    dated=req.dated,
                    unit=text,
                )
        return ledger.write_number(
            conn,
            at=at,
            actor=actor,
            item_id=item_id,
            name=EQUALS,
            value=value,
            unit=text,
            source_id=req.source_id,
            dated=req.dated,
        )


def _equals(equals: str) -> tuple[str, str]:
    """`<positive exact decimal> <unit text>` as (value text, unit text)."""
    written = re.fullmatch(r"(\S+)\s+(.+)", equals.strip())
    if written is None:
        raise CalcError("CALC_UNIT_FACTOR", field="equals")
    try:
        return ledger._exact(written[1]), written[2]
    except RecordsError:
        raise CalcError("CALC_UNIT_FACTOR", field="equals") from None


def _check(build, field: str) -> None:
    """Builds a table to check a definition; its refusal names `field`."""
    try:
        build()
    except CalcError as e:
        raise CalcError(e.key, field=field, status=e.status, **e.values) from None


def _definitions(conn) -> dict[str, tuple[Decimal, str, str]]:
    rows = conn.execute(
        "SELECT i.code, n.value, n.unit, n.id FROM items i JOIN numbers n ON n.item_id = i.id"
        " WHERE i.kind = ? AND n.name = ? AND n.valid_until IS NULL"
        " ORDER BY n.recorded_at, n.id",
        (UNIT_KIND, EQUALS),
    ).fetchall()
    return {code: (Decimal(value), unit, number_id) for code, value, unit, number_id in rows}


def _currencies(conn) -> list[str]:
    rows = conn.execute("SELECT DISTINCT currency FROM numbers WHERE currency IS NOT NULL")
    return [currency for (currency,) in rows]


# How a ledger number's unit and currency are read and saved (Decision 9).


def ledger_unit(name: str, unit: str | None, currency: str | None) -> str:
    """The unit the engine reads for a ledger number: an `amount` is its currency; with unit and
    currency both set it is currency per unit (`EGP/m3`); otherwise whichever is set."""
    table = UnitTable(currencies=[currency] if currency else ())
    return table.format(_read(table, name, unit, currency))


def _read(table: UnitTable, name: str, unit: str | None, currency: str | None) -> Unit:
    if name == "amount":
        return table.parse(currency)  # its unit, if any, is the item's label
    if unit and currency:
        return table.parse(currency) / table.parse(unit)  # per the whole unit: EGP/(m3·day)
    return table.parse(unit or currency)


def ledger_columns(name: str, unit: Unit, table: UnitTable) -> tuple[str | None, str | None]:
    """(unit, currency) to save a result as: a `rate` is one currency per unit, an `amount` one
    currency, a `quantity` no currency. Any other name splits off one currency when it can."""
    money = [(symbol, power) for symbol, power in unit.terms if symbol.kind == "currency"]
    rest = Unit(tuple(term for term in unit.terms if term[0].kind != "currency"))
    one = len(money) == 1 and money[0][1] == 1
    text = table.format(unit)
    if name == "rate" and not (one and rest.terms):
        raise CalcError("CALC_SAVE_RATE", field="result.unit", unit=text)
    if name == "amount" and not (one and not rest.terms):
        raise CalcError("CALC_SAVE_AMOUNT", field="result.unit", unit=text)
    if name == "quantity" and money:
        raise CalcError("CALC_SAVE_QUANTITY", field="result.unit", unit=text)
    if one:
        return table.format(rest.power(-1)) or None, money[0][0].spelling
    return text or None, None


# Items and numbers.


def find_item(conn, ref: str, *, field: str | None = None) -> dict:
    """The item with id `ref`, else the one item with code `ref`. Unit definitions are not
    items here: they are read and changed only as units."""
    found = _items(conn, "id = ?", ref)
    if not found:
        found = _items(conn, "code = ?", ref)
    if not found:
        raise CalcError("CALC_ITEM_NOT_FOUND", field=field, ref=ref)
    if len(found) > 1:
        choices = ", ".join(item["id"] for item in found[:_CHOICES])
        raise CalcError("CALC_ITEM_AMBIGUOUS", field=field, ref=ref, n=len(found), choices=choices)
    return found[0]


def _items(conn, where: str, value: str) -> list[dict]:
    rows = conn.execute(
        f"SELECT {_ITEM_COLUMNS} FROM items WHERE {where} AND kind != ? ORDER BY created_at, id",
        (value, UNIT_KIND),
    ).fetchall()
    return [_item(row) for row in rows]


def _item(row) -> dict:
    item_id, kind, code, fields = row
    return {"id": item_id, "kind": kind, "code": code, "fields": json.loads(fields)}


def current_number(conn, item_id: str, name: str, *, field: str | None = None) -> dict:
    """The item's one current number of that name."""
    found = _current(conn, item_id, name)
    if not found:
        raise CalcError("CALC_NUMBER_MISSING", field=field, item=_code(conn, item_id), name=name)
    if len(found) > 1:
        raise _ambiguous(conn, item_id, name, found, field)
    return found[0]


def _current(conn, item_id: str, name: str) -> list[dict]:
    cursor = conn.execute(
        f"SELECT {_NUMBER_COLUMNS} FROM numbers WHERE item_id = ? AND name = ?"
        " AND valid_until IS NULL ORDER BY recorded_at, id",
        (item_id, name),
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _ambiguous(conn, item_id: str, name: str, found: list[dict], field) -> CalcError:
    choices = ", ".join(n["id"] for n in found[:_CHOICES])
    return CalcError(
        "CALC_NUMBER_AMBIGUOUS",
        field=field,
        item=_code(conn, item_id),
        n=len(found),
        name=name,
        choices=choices,
    )


def _code(conn, item_id: str) -> str:
    row = conn.execute("SELECT code FROM items WHERE id = ?", (item_id,)).fetchone()
    return row[0] if row and row[0] else item_id


def current_of(conn, number_id: str) -> str:
    """Follows `replaces` forward from `number_id` to the current entry."""
    while True:
        row = conn.execute("SELECT id FROM numbers WHERE replaces = ?", (number_id,)).fetchone()
        if row is None:
            return number_id
        number_id = row[0]


def _number(conn, number_id: str, field: str) -> dict:
    cursor = conn.execute(f"SELECT {_NUMBER_COLUMNS} FROM numbers WHERE id = ?", (number_id,))
    row = cursor.fetchone()
    if row is None:
        raise CalcError("CALC_NUMBER_NOT_FOUND", field=field, ref=number_id)
    number = dict(zip([d[0] for d in cursor.description], row, strict=True))
    if number["valid_until"] is not None:
        now = current_of(conn, number_id)
        raise CalcError("CALC_NUMBER_OLD", field=field, ref=number_id, now=now)
    return number


# Selectors.


def select(conn, sel: Selector, *, field: str = "where") -> list[dict]:
    """The items `sel` matches, by code then creation; never unit definitions. May be empty."""
    sql, args = [f"SELECT {_ITEM_COLUMNS} FROM items WHERE kind != ?"], [UNIT_KIND]
    if sel.kind is not None:
        sql.append("AND kind = ?")
        args.append(sel.kind)
    if sel.code_prefix is not None:
        sql.append("AND substr(code, 1, length(?)) = ?")
        args += [sel.code_prefix, sel.code_prefix]
    for key, value in sel.where.items():
        if '"' in key or "\\" in key:
            example = json.dumps({"where": {"floor": "1"}})
            raise CalcError("CALC_REQUEST_SHAPE", field=field, example=example)
        sql.append("AND json_extract(fields, ?) = ?")
        args += [f'$."{key}"', value]
    sql.append("ORDER BY code, created_at, id")
    return [_item(row) for row in conn.execute(" ".join(sql), args).fetchall()]


def _shown(sel: Selector) -> str:
    return json.dumps(sel.model_dump(exclude_defaults=True), ensure_ascii=False)


def _members(conn, spec: EachRef, skip_missing: bool, field: str) -> tuple[list[dict], list[str]]:
    """The current `spec.name` number of every matching item, and the codes of items without."""
    items = select(conn, spec.each, field=f"{field}.each.where")
    if not items:
        raise CalcError("CALC_NO_MATCH", field=field, selector=_shown(spec.each))
    rows, missing = [], []
    for item in items:
        found = _current(conn, item["id"], spec.name)
        if len(found) > 1:
            raise _ambiguous(conn, item["id"], spec.name, found, field)
        if found:
            rows += found
        else:
            missing.append(item["code"] or item["id"])
    if missing and not (skip_missing and rows):
        codes = ", ".join(missing[:_CODES])
        raise CalcError(
            "CALC_MISSING_IN_ITEMS", field=field, n=len(missing), name=spec.name, codes=codes
        )
    return rows, missing


# Inputs.


def resolve(
    conn, req: CalcRequest, table: UnitTable, *, item: dict | None, used_names: set[str]
) -> Resolved:
    """Reads every input of `req`, and each name in `used_names` that is not an input from
    `item`'s current numbers.

    `request` is `req` with every name explicit and pinned: a number by its id, a list by its ids,
    an `each` by its selector, a constant as exact text; `item` is the target item's id, and
    `save` and `for_each` are left out. It is a valid `CalcRequest` again. `used` also lists the
    unit definitions the inputs' units use, as `("unit:<symbol>", 0, number id)`."""
    inputs: dict[str, Input] = {}
    used: list[tuple[str, int, str]] = []
    pinned: dict[str, dict] = {}
    skipped: list[str] = []
    dates: list[str] = []

    def read(name: str, rows: list[dict], is_list: bool) -> None:
        values = []
        for seq, number in enumerate(rows):
            unit = _read(table, number["name"], number["unit"], number["currency"])
            values.append(Quantity(Decimal(number["value"]), unit))
            used.append((name, seq, number["id"]))
            dates.append(number["dated"])
        inputs[name] = Input(name, tuple(values), is_list, "ledger")

    for name, spec in req.inputs.items():
        field = f"inputs.{name}"
        if isinstance(spec, Constant):
            text = _constant(spec.constant, field)
            value = Quantity(Decimal(text), table.parse(spec.unit))
            inputs[name] = Input(name, (value,), False, "constant")
            pinned[name] = {"constant": text, "unit": spec.unit, "why": spec.why}
            continue
        if isinstance(spec, NumberRef):
            rows = [_number(conn, spec.number, field)]
            pinned[name] = {"number": rows[0]["id"]}
        elif isinstance(spec, SlotRef):
            target = find_item(conn, spec.item, field=field)
            rows = [current_number(conn, target["id"], spec.name, field=field)]
            pinned[name] = {"number": rows[0]["id"]}
        elif isinstance(spec, ListRef):
            rows = [_number(conn, number_id, field) for number_id in spec.numbers]
            pinned[name] = {"numbers": [n["id"] for n in rows]}
        else:
            rows, missing = _members(conn, spec, req.skip_missing, field)
            skipped += missing
            pinned[name] = {"each": spec.each.model_dump(exclude_defaults=True), "name": spec.name}
        read(name, rows, isinstance(spec, ListRef | EachRef))

    from_item = sorted(used_names - set(req.inputs))
    for name in from_item:
        if item is None:
            names = ", ".join(sorted(req.inputs))
            raise CalcError("CALC_UNKNOWN_NAME", field="formula", name=name, names=names)
        found = _current(conn, item["id"], name)
        if not found:
            have = conn.execute(
                "SELECT DISTINCT name FROM numbers WHERE item_id = ? AND valid_until IS NULL",
                (item["id"],),
            ).fetchall()
            names = ", ".join(sorted(set(req.inputs) | {n for (n,) in have}))
            code = item["code"] or item["id"]
            raise CalcError("CALC_UNKNOWN_NAME", field="formula", name=name, names=names, item=code)
        if len(found) > 1:
            raise _ambiguous(conn, item["id"], name, found, "formula")
        read(name, found, False)
        pinned[name] = {"number": found[0]["id"]}

    definitions: dict[str, str] = {}
    for value in (v for i in inputs.values() for v in i.values):
        definitions.update(table.definitions(value.unit))
    for symbol, number_id in definitions.items():
        used.append((f"unit:{symbol}", 0, number_id))
        dates.append(_number(conn, number_id, "unit")["dated"])

    request = req.model_dump(exclude={"inputs", "item", "for_each", "save"})
    request.update(item=item["id"] if item else None, inputs=pinned)
    return Resolved(inputs, used, request, max(dates, default=None), skipped, from_item)


def _constant(text: str, field: str) -> str:
    """The ledger's rule for exact decimal text, so `٥` is 5 and `1,000` is refused."""
    try:
        return ledger._exact(text)
    except RecordsError:
        raise CalcError("NUMBER_NOT_EXACT", field=field) from None
