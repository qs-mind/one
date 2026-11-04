"""Out-of-date numbers and recalculation, in order.

A saved calculation's input rows make the dependency graph: calculation B depends on A when B
read A's output. A calculation counts while it is current and its output is still current; one
whose output was corrected by hand is overridden, never listed and never recalculated. It is
out of date when an input it read was corrected, or when the items its `each` inputs match have
changed; everything built on it waits for it. `recalculate` works through that list in order,
each step a new calculation version and a ledger correction of its output, so old values still
answer `as_of`.
"""

import heapq
import json
from collections.abc import Iterable
from dataclasses import dataclass

from qsone import copy
from qsone.calc import engine
from qsone.calc.evaluate import evaluate
from qsone.calc.formula import names, parse
from qsone.calc.resolve import current_of, find_item, resolve, select, unit_table
from qsone.calc.spec import CalcRequest, Rounding, Selector
from qsone.records import ledger
from qsone.records.project import Records, RecordsError


@dataclass(frozen=True)
class Stale:
    calculation: str
    number: str
    item: str
    code: str | None
    name: str
    because: list[dict]
    # {"input": "fx", "was": <id>, "now": <id>, "reason": "<correction reason>"}
    # {"members": {"added": [codes], "removed": [codes]}}
    # {"waits_for": <calculation id>}


@dataclass(frozen=True)
class Change:
    calculation: str
    replaced: str
    number: str
    replaced_number: str
    item: str
    code: str | None
    name: str
    was: str
    now: str
    unit: str


@dataclass(frozen=True)
class Recalculated:
    changes: list[Change]
    failed: list[dict]  # {"calculation", "code", "error": {en, ar}}
    waiting: list[str]  # calculations not run because one upstream failed


@dataclass(frozen=True)
class _Calc:
    id: str
    output: str
    request: dict
    recorded_at: str
    item: str
    code: str | None
    name: str
    value: str


# Reading the graph.

_CALCS = (
    "SELECT c.id, c.output, c.request, c.recorded_at, n.item_id, i.code, n.name, n.value"
    " FROM calculations c JOIN numbers n ON n.id = c.output JOIN items i ON i.id = n.item_id"
    " WHERE c.valid_until IS NULL AND n.valid_until IS NULL ORDER BY c.recorded_at, c.id"
)
_INPUTS = (
    "SELECT ci.calc_id, ci.name, ci.number_id, n.item_id, n.valid_until"
    " FROM calc_inputs ci JOIN calculations c ON c.id = ci.calc_id"
    " JOIN numbers n ON n.id = ci.number_id WHERE c.valid_until IS NULL"
)


def _calcs(conn) -> dict[str, _Calc]:
    rows = conn.execute(_CALCS).fetchall()
    return {row[0]: _Calc(row[0], row[1], json.loads(row[2]), *row[3:]) for row in rows}


def _inputs(conn, calc_id: str | None = None) -> dict[str, list[tuple]]:
    """Each current calculation's input rows: (name, number id, item id, valid_until)."""
    sql, args = _INPUTS, ()
    if calc_id is not None:
        sql, args = sql + " AND ci.calc_id = ?", (calc_id,)
    found: dict[str, list[tuple]] = {}
    for calc, *row in conn.execute(sql + " ORDER BY ci.rowid", args).fetchall():
        found.setdefault(calc, []).append(tuple(row))
    return found


def _causes(conn, calc: _Calc, rows: list[tuple]) -> tuple[list[dict], set[str]]:
    """Why `calc` itself is out of date, and the current numbers it would read now."""
    because, reads = [], set()
    for name, number_id, _, valid_until in rows:
        if valid_until is None:
            reads.add(number_id)
            continue
        now = current_of(conn, number_id)
        (reason,) = conn.execute("SELECT reason FROM numbers WHERE id = ?", (now,)).fetchone()
        because.append({"input": name, "was": number_id, "now": now, "reason": reason})
        reads.add(now)
    for name, spec in calc.request["inputs"].items():
        if "each" not in spec:
            continue
        stored = list(dict.fromkeys(item for n, _, item, _ in rows if n == name))
        members = _members_now(conn, spec, calc.request["skip_missing"])
        reads.update(number for _, _, found in members for number in found)
        now = [item for item, _, _ in members]
        added = [code for item, code, _ in members if item not in stored]
        removed = [_code(conn, item) for item in stored if item not in now]
        if added or removed:
            because.append({"members": {"added": added, "removed": removed}})
    return because, reads


def _members_now(conn, spec: dict, skip_missing: bool) -> list[tuple[str, str, list[str]]]:
    """(item id, code, current number ids of that name) for each item the selector matches now.
    With `skip_missing`, items without the number are not members."""
    items = select(conn, Selector(**spec["each"]))
    found: dict[str, list[str]] = {}
    rows = conn.execute(
        "SELECT item_id, id FROM numbers WHERE name = ? AND valid_until IS NULL"
        " ORDER BY recorded_at, rowid",
        (spec["name"],),
    )
    for item_id, number_id in rows:
        found.setdefault(item_id, []).append(number_id)
    return [
        (item["id"], item["code"] or item["id"], found.get(item["id"], []))
        for item in items
        if found.get(item["id"]) or not skip_missing
    ]


def _code(conn, item_id: str) -> str:
    (code,) = conn.execute("SELECT code FROM items WHERE id = ?", (item_id,)).fetchone()
    return code or item_id


def _stale(conn) -> tuple[dict[str, _Calc], list[str], dict[str, list[dict]], dict]:
    """The current calculations, the out-of-date ones in recalculation order, each one's causes
    and the stale calculations each one waits for."""
    calcs = _calcs(conn)
    inputs = _inputs(conn)
    by_output = {calc.output: calc.id for calc in calcs.values()}
    because, upstream = {}, {}
    for calc in calcs.values():
        because[calc.id], reads = _causes(conn, calc, inputs.get(calc.id, []))
        upstream[calc.id] = {by_output[n] for n in reads if n in by_output} - {calc.id}

    downstream: dict[str, set[str]] = {calc_id: set() for calc_id in calcs}
    for calc_id, ups in upstream.items():
        for up in ups:
            downstream[up].add(calc_id)
    listed = {calc_id for calc_id, causes in because.items() if causes}
    todo = list(listed)
    while todo:
        for down in downstream[todo.pop()]:
            if down not in listed:
                listed.add(down)
                todo.append(down)

    # Kahn's order: of the calculations whose upstream is done, the earliest recorded first.
    waits = {calc_id: upstream[calc_id] & listed for calc_id in listed}
    rank = {calc_id: n for n, calc_id in enumerate(calcs)}
    left = {calc_id: len(ups) for calc_id, ups in waits.items()}
    ready = [rank[calc_id] for calc_id, n in left.items() if n == 0]
    heapq.heapify(ready)
    order: list[str] = []
    ids = list(calcs)
    while ready:
        calc_id = ids[heapq.heappop(ready)]
        order.append(calc_id)
        for down in downstream[calc_id]:
            if down in left:
                left[down] -= 1
                if left[down] == 0:
                    heapq.heappush(ready, rank[down])
    # Calculations that read each other's outputs never get ready; they go last.
    order += sorted(listed - set(order), key=rank.__getitem__)
    place = {calc_id: n for n, calc_id in enumerate(order)}
    for calc_id in order:
        ups = sorted(waits[calc_id], key=place.__getitem__)
        because[calc_id] = because[calc_id] + [{"waits_for": up} for up in ups]
    return calcs, order, because, waits


def why_stale(conn, calc_id: str) -> list[dict]:
    """Why a calculation is out of date; [] when it is not (or is not current)."""
    _, order, because, _ = _stale(conn)
    return because[calc_id] if calc_id in order else []


def stale(rec: Records) -> list[Stale]:
    """Every out-of-date calculation and everything downstream of it, in recalculation order."""
    with rec.read() as conn:
        calcs, order, because, _ = _stale(conn)
    return [
        Stale(c.id, c.output, c.item, c.code, c.name, because[c.id])
        for c in (calcs[calc_id] for calc_id in order)
    ]


# Recalculating.


def recalculate(rec: Records, *, actor: str, only: Iterable[str] | None = None) -> Recalculated:
    """Recalculates the out-of-date calculations in order, in one transaction with a savepoint
    each. With `only`, just those and the out-of-date calculations they need first. A step that
    fails is rolled back and listed; everything downstream of it waits."""
    changes: list[Change] = []
    failed: list[dict] = []
    waiting: list[str] = []
    with rec.write(actor) as conn:
        calcs, order, _, waits = _stale(conn)
        if only is not None:
            wanted, todo = set(), [calc_id for calc_id in only if calc_id in waits]
            while todo:
                calc_id = todo.pop()
                if calc_id not in wanted:
                    wanted.add(calc_id)
                    todo += waits[calc_id]
            order = [calc_id for calc_id in order if calc_id in wanted]
        if not order:
            return Recalculated([], [], [])
        at = rec.clock()
        table = unit_table(conn)
        roots: dict[str, str] = {}  # recalculated number -> the reason it was recalculated
        done: set[str] = set()
        for calc_id in order:
            calc = calcs[calc_id]
            if waits[calc_id] - done:  # an upstream step failed or is waiting
                waiting.append(calc_id)
                continue
            conn.execute("SAVEPOINT recalc")
            try:
                change = _run(conn, at, actor, calc, table, roots)
            except RecordsError as e:
                conn.execute("ROLLBACK TO recalc")
                conn.execute("RELEASE recalc")
                failed.append({"calculation": calc_id, "code": calc.code, "error": e.text})
                continue
            conn.execute("RELEASE recalc")
            done.add(calc_id)
            changes.append(change)
    return Recalculated(changes, failed, waiting)


def _run(conn, at: str, actor: str, calc: _Calc, table, roots: dict[str, str]) -> Change:
    """Rebuilds the stored request on current inputs, evaluates it with the stored unit and
    rounding, and saves it over the old calculation and its output."""
    because, _ = _causes(conn, calc, _inputs(conn, calc.id).get(calc.id, []))
    inputs = {}
    for name, spec in calc.request["inputs"].items():
        if "number" in spec:
            spec = {"number": current_of(conn, spec["number"])}
        elif "numbers" in spec:
            spec = {"numbers": [current_of(conn, n) for n in spec["numbers"]]}
        inputs[name] = spec
    req = CalcRequest(**{**calc.request, "inputs": inputs})
    item = find_item(conn, calc.item)
    tree = parse(req.formula)
    res = resolve(conn, req, table, item=item, used_names=names(tree))
    rounding = req.result.round or Rounding()
    ev = evaluate(tree, req.formula, res.inputs, table, unit=req.result.unit, rounding=rounding)
    reason = _reason(because, roots)
    result = engine.save_one(
        conn,
        at,
        actor,
        res.request,
        ev,
        res,
        table,
        item=item,
        name=calc.name,
        replaces=ledger._row(conn, "numbers", calc.output),
        reason=reason,
        replaces_calc=calc.id,
        because=because,
    )
    roots[result.number] = reason
    return Change(
        calculation=result.calculation,
        replaced=calc.id,
        number=result.number,
        replaced_number=calc.output,
        item=calc.item,
        code=calc.code,
        name=calc.name,
        was=calc.value,
        now=result.value,
        unit=result.unit,
    )


def _reason(because: list[dict], roots: dict[str, str]) -> str:
    """The English reason for the correction (the trace keeps the causes as data). A number
    recalculated in this run passes on the reason it was recalculated for, so every number
    downstream names the input that started it."""
    for cause in because:
        if "input" in cause:
            if cause["now"] in roots:
                return roots[cause["now"]]
            return copy.fill(copy.CALC_RECALCULATED, name=cause["input"], reason=cause["reason"])[
                "en"
            ]
    return copy.CALC_RECALC_MEMBERS["en"]
