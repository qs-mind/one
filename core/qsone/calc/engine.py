"""Calculate, save and explain: the engine's front door.

`calculate` parses the formula once, reads its inputs from the Source Ledger, evaluates it exactly
and, when asked, saves the result as a ledger number whose source is the calculation. The
calculation row keeps the resolved request, the trace and one input row per number read, which
together make the dependency graph. `explain` walks back from any number to its sources.
"""

import json
import math
from dataclasses import dataclass
from uuid import uuid4

from qsone import copy
from qsone.calc import ENGINE_VERSION, graph
from qsone.calc.errors import CalcError
from qsone.calc.evaluate import Evaluation, evaluate
from qsone.calc.formula import names, parse
from qsone.calc.resolve import (
    Resolved,
    _shown,
    current_number,
    find_item,
    ledger_columns,
    ledger_unit,
    resolve,
    select,
    unit_table,
)
from qsone.calc.spec import CalcRequest, EachRef, Rounding
from qsone.calc.units import UnitTable
from qsone.records import audit, ledger
from qsone.records.project import Records

_STEPS = 20  # steps shown in a preview
_DEFAULT_ROUND = Rounding().model_dump()


@dataclass(frozen=True)
class Result:
    item: str | None
    code: str | None
    value: str
    unit: str
    exact: bool
    number: str | None  # None in a preview
    calculation: str | None  # None in a preview
    unchanged: bool
    dated: str | None


@dataclass(frozen=True)
class Outcome:
    results: list[Result]  # one, or one per matching item
    skipped: list[str]
    defaults_used: dict  # {"round": {...}} and/or {"from_item": [...]}
    notes: list[dict]  # {en, ar}
    steps: list[dict]  # a preview that is not for_each: the first 20 steps


# Calculating.


@dataclass(frozen=True)
class _Run:
    item: dict | None
    res: Resolved
    ev: Evaluation


def calculate(rec: Records, req: CalcRequest, *, actor: str) -> Outcome:
    tree = parse(req.formula)
    used_names = names(tree)
    rounding = req.result.round or Rounding()
    with rec.write(actor) if req.save else rec.read() as conn:
        table = unit_table(conn)
        runs, missing = [], []
        for item in _targets(conn, req):
            try:
                res = resolve(conn, req, table, item=item, used_names=used_names)
                ev = evaluate(
                    tree, req.formula, res.inputs, table, unit=req.result.unit, rounding=rounding
                )
            except CalcError as e:
                if req.for_each is None:
                    raise
                if e.key == "CALC_UNKNOWN_NAME" and "item" in e.values:
                    missing.append((e.values["name"], e.values["item"]))
                    continue
                _naming(e, item)
                raise
            runs.append(_Run(item, res, ev))
        if missing and not (req.skip_missing and runs):
            name = missing[0][0]
            codes = [code for n, code in missing if n == name]
            raise CalcError(
                "CALC_MISSING_IN_ITEMS",
                field="for_each",
                n=len(codes),
                name=name,
                codes=", ".join(codes[:20]),
            )

        if req.save is None:
            results = [_preview(run, table) for run in runs]
        else:
            at = rec.clock()
            results = []
            for run in runs:
                try:
                    results.append(_save(conn, at, actor, req, run, table))
                except CalcError as e:
                    if req.for_each is not None:
                        _naming(e, run.item)
                    raise

    skipped = [code for run in runs for code in run.res.skipped] + [c for _, c in missing]
    defaults_used: dict = {}
    if req.result.round is None:
        defaults_used["round"] = dict(_DEFAULT_ROUND)
    from_item = sorted({name for run in runs for name in run.res.from_item})
    if from_item:
        defaults_used["from_item"] = from_item
    steps = runs[0].ev.steps[:_STEPS] if req.save is None and req.for_each is None else []
    return Outcome(results, skipped, defaults_used, _notes(req, runs, missing, table), steps)


def _targets(conn, req: CalcRequest) -> list[dict | None]:
    if req.item is not None:
        return [find_item(conn, req.item, field="item")]
    if req.for_each is None:
        return [None]
    items = select(conn, req.for_each, field="for_each.where")
    if not items:
        raise CalcError("CALC_NO_MATCH", field="for_each", selector=_shown(req.for_each))
    return items


def _naming(e: CalcError, item: dict) -> None:
    """The refusal for one item of a for_each names that item's code."""
    e.values.setdefault("item", item["code"] or item["id"])


def _notes(req: CalcRequest, runs: list[_Run], missing: list, table: UnitTable) -> list[dict]:
    notes = []
    if any(not run.ev.exact for run in runs):
        notes.append(copy.CALC_NOTE_INEXACT)
    own: dict[str, str] = {}
    for run in runs:
        for spelling in sorted(run.ev.units):
            for unit in table.own_units(table.parse(spelling)):
                own.setdefault(unit.casefold(), unit)
    notes += [copy.fill(copy.CALC_NOTE_OWN_UNIT, unit=unit) for unit in own.values()]
    each = [spec.name for spec in req.inputs.values() if isinstance(spec, EachRef)]
    skips = [(", ".join(each), code) for run in runs for code in run.res.skipped] + missing
    for name in dict.fromkeys(name for name, _ in skips):
        codes = [code for n, code in skips if n == name]
        notes.append(
            copy.fill(copy.CALC_NOTE_SKIPPED, n=len(codes), name=name, codes=", ".join(codes[:20]))
        )
    return notes


def _preview(run: _Run, table: UnitTable) -> Result:
    return Result(
        item=run.item["id"] if run.item else None,
        code=run.item["code"] if run.item else None,
        value=f"{run.ev.value:f}",
        unit=table.format(run.ev.unit),
        exact=run.ev.exact,
        number=None,
        calculation=None,
        unchanged=False,
        dated=run.res.dated,
    )


def _save(conn, at: str, actor: str, req: CalcRequest, run: _Run, table: UnitTable) -> Result:
    """The saving rules, in order, then `save_one`."""
    item, res, ev, name = run.item, run.res, run.ev, req.save.name
    if not any(i.origin == "ledger" for i in res.inputs.values()):
        raise CalcError("CALC_NEEDS_LEDGER_INPUT", field="inputs")
    ledger_columns(name, ev.unit, table)
    try:
        old = current_number(conn, item["id"], name, field="save.name")
    except CalcError as e:
        if e.key != "CALC_NUMBER_MISSING":
            raise
        old = None
    old_calc = None
    if old is not None:
        old_calc = conn.execute(
            "SELECT id, request, value FROM calculations WHERE output = ? AND valid_until IS NULL",
            (old["id"],),
        ).fetchone()
        used, _ = _all_used(conn, ev, res, table)
        if old_calc is not None and old_calc[1] == _canonical(res.request):
            stored = conn.execute(
                "SELECT name, seq, number_id FROM calc_inputs WHERE calc_id = ?", (old_calc[0],)
            ).fetchall()
            if set(stored) == set(used):
                return Result(
                    item=item["id"],
                    code=item["code"],
                    value=old_calc[2],
                    unit=table.format(ev.unit),
                    exact=ev.exact,
                    number=old["id"],
                    calculation=old_calc[0],
                    unchanged=True,
                    dated=old["dated"],
                )
        if not (req.save.reason or "").strip():
            title = conn.execute(
                "SELECT title FROM sources WHERE id = ?", (old["source_id"],)
            ).fetchone()[0]
            raise CalcError(
                "CALC_SAVE_NEEDS_REASON",
                field="save.reason",
                item=item["code"] or item["id"],
                name=name,
                value=old["value"],
                unit=ledger_unit(name, old["unit"], old["currency"]),
                source=title,
            )
        own = [n for n, _, number_id in used if number_id == old["id"]]
        if own:
            raise CalcError("CALC_SAVE_OWN_INPUT", field="save.name", name=own[0])
    return save_one(
        conn,
        at,
        actor,
        res.request,
        ev,
        res,
        table,
        item=item,
        name=name,
        replaces=old,
        reason=req.save.reason,
        replaces_calc=old_calc[0] if old_calc else None,
    )


def _canonical(request: dict) -> str:
    return json.dumps(request, sort_keys=True, ensure_ascii=False)


def _all_used(conn, ev: Evaluation, res: Resolved, table: UnitTable):
    """`res.used` plus the unit definitions only the formula or the result unit names, and the
    newest date among them all."""
    used, dated = list(res.used), res.dated
    listed = {n for n, _, _ in used}
    for spelling in sorted(ev.units):
        for symbol, number_id in table.definitions(table.parse(spelling)).items():
            if f"unit:{symbol}" in listed:
                continue
            listed.add(f"unit:{symbol}")
            used.append((f"unit:{symbol}", 0, number_id))
            (day,) = conn.execute("SELECT dated FROM numbers WHERE id = ?", (number_id,)).fetchone()
            dated = max(dated or day, day)
    return used, dated


def save_one(
    conn,
    at: str,
    actor: str,
    req_resolved: dict,
    ev: Evaluation,
    res: Resolved,
    table: UnitTable,
    *,
    item: dict,
    name: str,
    replaces: dict | None,
    reason: str | None,
    replaces_calc: str | None = None,
    because: list | None = None,
) -> Result:
    """Writes one result, inside the caller's transaction: its source, its number (or a
    correction of `replaces`), the calculation row, its inputs and the audit rows. When
    `replaces_calc` is given, that calculation is marked `valid_until`."""
    unit, currency = ledger_columns(name, ev.unit, table)
    if replaces is not None and currency is None and replaces["currency"] is not None:
        # A correction keeps the old currency unless given one: this result has none.
        was = ledger_unit(name, replaces["unit"], replaces["currency"])
        raise CalcError(
            "CALC_RESULT_UNIT", field="result.unit", got=table.format(ev.unit), want=was
        )
    used, dated = _all_used(conn, ev, res, table)
    calc_id = uuid4().hex
    value = f"{ev.value:f}"
    formula = req_resolved["formula"]
    source_id = ledger.write_source(
        conn,
        at=at,
        actor=actor,
        kind="calculation",
        title=formula[:200],
        locator={"calculation": calc_id},
        dated=dated,
    )
    if replaces is None:
        number_id = ledger.write_number(
            conn,
            at=at,
            actor=actor,
            item_id=item["id"],
            name=name,
            value=value,
            source_id=source_id,
            dated=dated,
            unit=unit,
            currency=currency,
        )
    else:
        number_id = ledger.write_correction(
            conn,
            replaces["id"],
            at=at,
            actor=actor,
            value=value,
            reason=reason,
            source_id=source_id,
            dated=dated,
            # An amount's unit is the item's label, so a correction keeps it; others are cleared.
            unit=unit if unit is not None or name == "amount" else "",
            currency=currency,
        )

    defaults_used: dict = {}
    if req_resolved["result"]["round"] is None:
        defaults_used["round"] = dict(_DEFAULT_ROUND)
    if res.from_item:
        defaults_used["from_item"] = list(res.from_item)
    notes = []
    if not ev.exact:
        notes.append("CALC_NOTE_INEXACT")
    if any(table.own_units(table.parse(s)) for s in ev.units):
        notes.append("CALC_NOTE_OWN_UNIT")
    if res.skipped:
        notes.append("CALC_NOTE_SKIPPED")
    trace = {
        "steps": ev.steps,
        "constants": ev.constants,
        "rounding": ev.rounding,
        "defaults_used": defaults_used,
        "notes": notes,
        "because": because or [],
    }
    row = {
        "id": calc_id,
        "formula": formula,
        "request": req_resolved,
        "value": value,
        "unit": table.format(ev.unit),
        "exact": int(ev.exact),
        "trace": trace,
        "engine": ENGINE_VERSION,
        "output": number_id,
        "recorded_at": at,
        "recorded_by": actor,
        "replaces": replaces_calc,
        "reason": reason if replaces is not None else None,
        "valid_until": None,
    }
    stored = {
        **row,
        "request": _canonical(req_resolved),
        "trace": json.dumps(trace, ensure_ascii=False),
    }
    conn.execute(
        f"INSERT INTO calculations ({', '.join(stored)}) VALUES ({', '.join('?' * len(stored))})",
        tuple(stored.values()),
    )
    conn.executemany(
        "INSERT INTO calc_inputs (calc_id, name, seq, number_id) VALUES (?, ?, ?, ?)",
        [(calc_id, n, seq, number) for n, seq, number in used],
    )
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create",
        table="calculations",
        row_id=calc_id,
        before=None,
        after=row,
    )
    if replaces_calc is not None:
        before = _calculation(conn, replaces_calc)
        conn.execute("UPDATE calculations SET valid_until = ? WHERE id = ?", (at, replaces_calc))
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="replace",
            table="calculations",
            row_id=replaces_calc,
            before=before,
            after={**before, "valid_until": at},
        )
    return Result(
        item=item["id"],
        code=item["code"],
        value=value,
        unit=row["unit"],
        exact=ev.exact,
        number=number_id,
        calculation=calc_id,
        unchanged=False,
        dated=dated,
    )


def _calculation(conn, calc_id: str) -> dict:
    cursor = conn.execute("SELECT * FROM calculations WHERE id = ?", (calc_id,))
    row = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    row["request"], row["trace"] = json.loads(row["request"]), json.loads(row["trace"])
    return row


# Explaining.


def explain(rec: Records, number_id: str, *, page: int = 1, per_page: int = 50) -> dict:
    """A number with its item and source and, when it was calculated, the calculation: its
    inputs (each with its source and date) and steps, paged together."""
    with rec.read() as conn:
        number = ledger._row(conn, "numbers", number_id)
        if number is None:
            raise CalcError("CALC_NUMBER_NOT_FOUND", field="number", ref=number_id)
        item = ledger._row(conn, "items", number["item_id"])
        source = ledger._row(conn, "sources", number["source_id"])
        replaced_by = conn.execute(
            "SELECT id FROM numbers WHERE replaces = ?", (number_id,)
        ).fetchone()
        found = conn.execute(
            "SELECT id FROM calculations WHERE output = ?", (number_id,)
        ).fetchone()
        calculation = None
        if found is not None:
            calculation = _explain_calculation(conn, found[0], page, per_page)
    return {
        "number": {
            "id": number["id"],
            "item": {"id": item["id"], "code": item["code"], "kind": item["kind"]},
            "name": number["name"],
            "value": number["value"],
            "unit": number["unit"],
            "currency": number["currency"],
            "dated": number["dated"],
            "recorded_at": number["recorded_at"],
            "recorded_by": number["recorded_by"],
            "current": number["valid_until"] is None,
            "replaced_by": replaced_by[0] if replaced_by else None,
            "reason": number["reason"],
        },
        "source": {
            key: source[key]
            for key in ("id", "kind", "title", "file_id", "locator", "url", "dated")
        },
        "calculation": calculation,
    }


def _explain_calculation(conn, calc_id: str, page: int, per_page: int) -> dict:
    calc = _calculation(conn, calc_id)
    rows = conn.execute(
        "SELECT ci.name, ci.seq, n.id, n.name, n.value, n.unit, n.currency, n.dated, s.kind,"
        " s.title, EXISTS (SELECT 1 FROM calculations c WHERE c.output = n.id)"
        " FROM calc_inputs ci JOIN numbers n ON n.id = ci.number_id"
        " JOIN sources s ON s.id = n.source_id WHERE ci.calc_id = ? ORDER BY ci.rowid",
        (calc_id,),
    ).fetchall()
    inputs = [
        {
            "name": name,
            "seq": seq,
            "number": number,
            "value": value,
            "unit": ledger_unit(number_name, unit, currency),
            "dated": dated,
            "source": {"kind": kind, "title": title},
            "calculated": bool(calculated),
        }
        for (
            name,
            seq,
            number,
            number_name,
            value,
            unit,
            currency,
            dated,
            kind,
            title,
            calculated,
        ) in rows
    ]
    steps = calc["trace"]["steps"]
    pages = max(1, math.ceil(max(len(inputs), len(steps)) / per_page))
    start = (page - 1) * per_page
    because = graph.why_stale(conn, calc_id)
    return {
        "id": calc["id"],
        "formula": calc["formula"],
        "unit": calc["unit"],
        "rounding": calc["trace"]["rounding"],
        "exact": bool(calc["exact"]),
        "engine": calc["engine"],
        "recorded_at": calc["recorded_at"],
        "recorded_by": calc["recorded_by"],
        "stale": bool(because),
        "because": because,
        "inputs": inputs[start : start + per_page],
        "constants": calc["trace"]["constants"],
        "steps": steps[start : start + per_page],
        "page": page,
        "pages": pages,
    }
