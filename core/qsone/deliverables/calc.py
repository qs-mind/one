"""A Sheet's calculated cells, saved by the QS Calc Engine. The only Plan 6 file that imports
`qsone.calc`.

The Template Data Sheet names each calculated column's formula (`quantity * rate`) and its
totals' formula (`sum(amount)`). Here they become `CalcRequest`s, in order: the item amounts, then
the sections from the deepest, then the bill. Each runs as `calculate(save)`, which writes nothing
when its inputs have not moved, so bringing a whole Deliverable up to date is cheap.
"""

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from qsone import copy
from qsone.calc.engine import calculate
from qsone.calc.errors import CalcError
from qsone.calc.formula import names, parse
from qsone.calc.spec import CalcRequest, ListRef
from qsone.records import audit
from qsone.records.project import Records, RecordsError

CALC_ACTOR = "calc_engine"  # shown as "QS Calc Engine"
BILL_ROW = "total"  # the row a bill total is reported under (a document's `cell` uses it too)
_CURRENCY_OF = re.compile(r"currency_of:(?P<name>.+)")


def formula_names(formula: str) -> set[str]:
    """The number names a formula reads, by the QS Calc Engine's own parser. Raises its
    `CalcError` (a `RecordsError`) when the formula does not parse."""
    return names(parse(formula))


def number_cell(*, value, unit, currency, number_id, source_id, dated, source_kind) -> dict:
    """A number as a Sheet cell shows it: unit and currency only when set."""
    cell = {"value": value}
    if unit is not None:
        cell["unit"] = unit
    if currency is not None:
        cell["currency"] = currency
    cell |= {
        "number_id": number_id,
        "source": source_id,
        "dated": dated,
        "calculated": source_kind == "calculation",
    }
    return cell


# The Sheet as it is now: its rows in order, each with the section it sits under.


@dataclass(frozen=True)
class _Row:
    id: str  # the part id
    kind: str  # "item" or "section"
    item_id: str
    parent: str | None  # the section's part id; None means the bill
    depth: int  # 0 at the top level


@dataclass(frozen=True)
class _Sheet:
    title: str
    language: str
    columns: list[dict]
    bill_item: str | None
    rows: list[_Row]


@dataclass(frozen=True)
class _Target:
    row: str  # a part id, or BILL_ROW
    item_id: str
    column: dict
    children: tuple[str, ...] | None  # the item ids a total sums; None for an item's own


def _sheet(conn, deliverable_id: str) -> _Sheet:
    found = conn.execute(
        "SELECT title, language, template, total_item_id FROM deliverables WHERE id = ?",
        (deliverable_id,),
    ).fetchone()
    if found is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="deliverable")
    title, language, template, bill_item = found
    parts = conn.execute(
        "SELECT id, kind, item_id, node FROM parts WHERE deliverable_id = ?"
        " AND valid_until IS NULL AND removed = 0 AND kind IN ('item', 'section') ORDER BY seq",
        (deliverable_id,),
    ).fetchall()
    rows: list[_Row] = []
    open_sections: list[tuple[str, int]] = []  # (part id, level), outermost first
    for part_id, kind, item_id, node in parts:
        if kind == "section":
            level = json.loads(node).get("level", 1)
            while open_sections and open_sections[-1][1] >= level:
                open_sections.pop()
        parent = open_sections[-1][0] if open_sections else None
        rows.append(_Row(part_id, kind, item_id, parent, len(open_sections)))
        if kind == "section":
            open_sections.append((part_id, level))
    columns = json.loads(template).get("columns", [])
    return _Sheet(title, language, columns, bill_item, rows)


def _number_name(column: dict) -> str:
    return column["from"].removeprefix("number:")


def _plan(sheet: _Sheet, rows: Iterable[str] | None) -> list[_Target]:
    """Items first, then sections from the deepest, then the bill. With `rows`, only those rows
    and the sections above them; a row that is no longer in the Sheet (removed) brings every
    section and the bill."""
    by_id = {row.id: row for row in sheet.rows}
    wanted = set(by_id) if rows is None else set(rows)
    sections_wanted: set[str] = set()
    if wanted - set(by_id):
        sections_wanted = {row.id for row in sheet.rows if row.kind == "section"}
    for part_id in wanted & set(by_id):
        row = by_id[part_id]
        if row.kind == "section":
            sections_wanted.add(row.id)
        while row.parent is not None:
            sections_wanted.add(row.parent)
            row = by_id[row.parent]

    children: dict[str | None, list[str]] = {}
    for row in sheet.rows:
        children.setdefault(row.parent, []).append(row.item_id)
    calcs = [c for c in sheet.columns if "calc" in c]
    targets = [
        _Target(row.id, row.item_id, column, None)
        for row in sheet.rows
        if row.kind == "item" and row.id in wanted
        for column in calcs
    ]
    sections = [row for row in sheet.rows if row.id in sections_wanted]
    sections.sort(key=lambda row: -row.depth)  # stable: row order within a depth
    totals = [c for c in calcs if "total" in c]
    targets += [
        _Target(row.id, row.item_id, column, tuple(children.get(row.id, ())))
        for row in sections
        for column in totals
    ]
    if sheet.bill_item is not None:
        targets += [
            _Target(BILL_ROW, sheet.bill_item, column, tuple(children.get(None, ())))
            for column in totals
        ]
    return targets


def _current(conn, item_ids: Iterable[str], name: str) -> dict[str, tuple[str, str | None]]:
    """item id -> (number id, currency) of each item's current number of that name."""
    rows = conn.execute(
        "SELECT item_id, id, currency FROM numbers WHERE name = ? AND valid_until IS NULL"
        " AND item_id IN (SELECT value FROM json_each(?)) ORDER BY recorded_at, rowid",
        (name, json.dumps(list(item_ids))),
    ).fetchall()
    return {item_id: (number_id, currency) for item_id, number_id, currency in rows}


def _request(conn, target: _Target, reason: str) -> CalcRequest | None:
    """The request for one target, from the ledger as it is now; None when an input is missing
    (an item without its quantity, a section with no amounts under it)."""
    column, name = target.column, _number_name(target.column)
    save = {"name": name, "reason": reason}
    if target.children is None:
        formula = column["calc"]["formula"]
        have = {
            number_name: currency
            for number_name, currency in conn.execute(
                "SELECT name, currency FROM numbers WHERE item_id = ? AND valid_until IS NULL",
                (target.item_id,),
            )
        }
        if not formula_names(formula) <= set(have):
            return None
        currency = have[_CURRENCY_OF.fullmatch(column["calc"]["unit"])["name"]]
        return CalcRequest(
            formula=formula, item=target.item_id, result={"unit": currency}, save=save
        )
    found = _current(conn, target.children, name)
    listed = [found[item_id] for item_id in target.children if item_id in found]
    if not listed:
        return None
    return CalcRequest(
        formula=column["total"]["formula"],
        inputs={name: ListRef(numbers=[number_id for number_id, _ in listed])},
        item=target.item_id,
        result={"unit": listed[0][1]},
        save=save,
    )


def _reason(sheet: _Sheet) -> str:
    return copy.fill(copy.DELIVERABLE_CALC_REASON, title=sheet.title)[sheet.language]


def requests(rec: Records, deliverable_id: str, *, rows: Iterable[str] | None = None):
    """The QS Calc Engine requests for the Sheet as it is now, in the order they must run.
    `rows=None` means every row; else those rows and the sections and bill that sum them.

    A total's list holds the current amounts, so once an item amount is saved anew, the totals
    above it must be built again: `bring_up_to_date` builds each one just before it runs."""
    with rec.read() as conn:
        sheet = _sheet(conn, deliverable_id)
        reason = _reason(sheet)
        out = [_request(conn, target, reason) for target in _plan(sheet, rows)]
    return [req for req in out if req is not None]


def _cell(conn, number_id: str) -> dict:
    found = conn.execute(
        "SELECT n.value, n.unit, n.currency, n.id, n.source_id, n.dated, s.kind"
        " FROM numbers n JOIN sources s ON s.id = n.source_id WHERE n.id = ?",
        (number_id,),
    ).fetchone()
    value, unit, currency, number, source_id, dated, kind = found
    return number_cell(
        value=value,
        unit=unit,
        currency=currency,
        number_id=number,
        source_id=source_id,
        dated=dated,
        source_kind=kind,
    )


def _end_total(conn, rec: Records, target: _Target, actor: str) -> dict | None:
    """A section or the bill with no amounts under it any more (every priced row removed or moved
    away) has no total, as when it was made with none. Its saved total is ended: kept in the
    ledger, marked `valid_until`, with an audit row, so the bill stops counting it and a past
    version still shows it. Only a total the QS Calc Engine saved is ended, never a typed one.
    The Engine itself cannot save "the sum of nothing": a saved result needs a ledger input and
    its date. Returns the ended cell, or None when there was nothing to end."""
    name = _number_name(target.column)
    cursor = conn.execute(
        "SELECT n.* FROM numbers n JOIN sources s ON s.id = n.source_id WHERE n.item_id = ?"
        " AND n.name = ? AND n.valid_until IS NULL AND s.kind = 'calculation'",
        (target.item_id, name),
    )
    found = cursor.fetchone()
    if found is None:
        return None
    old = dict(zip([d[0] for d in cursor.description], found, strict=True))
    cell = _cell(conn, old["id"])
    at = rec.clock()
    conn.execute("UPDATE numbers SET valid_until = ? WHERE id = ?", (at, old["id"]))
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="end",
        table="numbers",
        row_id=old["id"],
        before=old,
        after={**old, "valid_until": at},
    )
    return cell


def bring_up_to_date(
    rec: Records,
    deliverable_id: str,
    *,
    actor: str,
    reason: str | None = None,
    rows: Iterable[str] | None = None,
    skipped: list[dict] | None = None,
) -> list[dict]:
    """Runs `calculate(save)` for each request, in one write (it joins the caller's), and
    returns the cells it wrote: `[{"row", "column", "before", "after"}]`, where `before` is the
    cell's number before (None when there was none), `after` is None for a total that was ended
    (nothing left under it), and `row` is a part id or "total". The reason defaults to
    «calculated in "<title>"» in the Deliverable's language. With `skipped`, a request the
    QS Calc Engine refuses is left out and noted there (`{"row", "column", "error"}`), so the rest
    still comes up to date; without it the refusal is raised."""
    changed = []
    with rec.write(actor) as conn:
        sheet = _sheet(conn, deliverable_id)
        reason = reason or _reason(sheet)
        for target in _plan(sheet, rows):
            req = _request(conn, target, reason)
            if req is None:
                ended = None if target.children is None else _end_total(conn, rec, target, actor)
                if ended is not None:
                    changed.append(
                        {
                            "row": target.row,
                            "column": target.column["key"],
                            "before": ended,
                            "after": None,
                        }
                    )
                continue
            old = _current(conn, [target.item_id], req.save.name).get(target.item_id)
            try:
                [result] = calculate(rec, req, actor=actor).results
            except CalcError as e:
                if skipped is None:
                    raise
                skipped.append({"row": target.row, "column": target.column["key"], "error": e.text})
                continue
            if result.unchanged:
                continue
            changed.append(
                {
                    "row": target.row,
                    "column": target.column["key"],
                    "before": _cell(conn, old[0]) if old else None,
                    "after": _cell(conn, result.number),
                }
            )
    return changed


class _RollBack(Exception):
    """Raised inside a dry run's write so that nothing it did is kept."""


def dry_run[T](
    rec: Records,
    deliverable_id: str,
    fn: Callable[[], T],
    *,
    rows: Iterable[str] | None = None,
    actor: str = CALC_ACTOR,
) -> tuple[T, list[dict]]:
    """Runs `fn()` and `bring_up_to_date` inside one write, keeps what they return, then rolls
    everything back: the ledger, the calculations, the parts and the audit are as they were. Inside
    an outer write only this one's own work is undone. Publishes nothing."""
    out: list = []
    try:
        with rec.write(actor):
            out.append(fn())
            out.append(bring_up_to_date(rec, deliverable_id, actor=actor, rows=rows))
            raise _RollBack
    except _RollBack:
        pass
    return out[0], out[1]
