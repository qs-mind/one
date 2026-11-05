"""Undo after an accept: the Deliverable goes back to the Saved version before it.

An accept writes its changes, the QS Calc Engine's amounts and totals, and one Saved version, in one
transaction; the version keeps `audit_from`, the audit row before those writes. `undo_accept` reads
the audit rows the accept wrote and writes each one's opposite as a new entry, never editing or
deleting: a part gets a new row version as it was, a number a correction back to its old entry (a
number the accept added is ended, as the engine ends a total), an item its old fields, the
template its old columns. Then the amounts and totals are brought up to date again, a new Saved
version is saved, and the changes the accept held wait again, each made current against the
Deliverable as it is now, so accepting one again applies it.

It is refused (UNDO_TOO_LATE) once anything the accept wrote has moved since, or another version
was saved; and for an accept that took in an Update from Project Records (UNDO_RECORDS): those
moves were made in Project Records, outside the Deliverable, and are corrected there.
"""

import json

from qsone import copy
from qsone.deliverables import calc, events, ops, store
from qsone.deliverables.changes import _SHOWN, Change, _changes, _dump, _engineer_only
from qsone.records import audit, ledger
from qsone.records.project import Records, RecordsError


def _late() -> RecordsError:
    return RecordsError(copy.UNDO_TOO_LATE, status=409, field="version")


def _held(conn, deliverable_id: str, n: int) -> tuple[list[Change], int]:
    """The changes version `n` accepted and its `audit_from`; refused when it cannot be undone."""
    found = conn.execute(
        "SELECT changes, audit_from FROM versions WHERE deliverable_id = ? AND n = ?",
        (deliverable_id, n),
    ).fetchone()
    if found is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="version")
    ids, audit_from = json.loads(found[0]), found[1]
    if audit_from is None or not ids or n != ops.latest_version(conn, deliverable_id):
        raise _late()
    held = [
        c
        for c in _changes(
            conn, deliverable_id, "AND id IN (SELECT value FROM json_each(?))", (_dump(ids),)
        )
        if c.status == "accepted" and c.version_n == n
    ]
    if len(held) != len(ids):
        raise _late()
    if any(c.op["op"] == "update_from_records" for c in held):
        raise RecordsError(copy.UNDO_RECORDS, status=409, field="version")
    return held, audit_from


def undoable(rec: Records, deliverable_id: str, n: int) -> bool:
    """Whether version `n` is an accept that Undo can take back now."""
    with rec.read() as conn:
        try:
            _held(conn, deliverable_id, n)
        except RecordsError:
            return False
    return True


def _loads(value):
    return None if value is None else json.loads(value)


def _plan(conn, deliverable_id: str, n: int, audit_from: int) -> dict:
    """What the accept wrote, from its audit rows: for each part, item, number chain and the
    template, how it was before the accept and the entry it left."""
    (end,) = conn.execute(
        "SELECT id FROM audit WHERE table_name = 'versions' AND row_id = ? AND action = 'create'",
        (f"{deliverable_id}/{n}",),
    ).fetchone()
    rows = conn.execute(
        "SELECT action, table_name, row_id, before, after FROM audit WHERE id > ? AND id <= ?"
        " ORDER BY id",
        (audit_from, end),
    ).fetchall()
    parts: dict[str, list] = {}
    items: dict[str, list] = {}
    numbers: dict[tuple[str, str], list] = {}
    calculated: dict[tuple[str, str], list] = {}
    template: list = []
    for action, table, row_id, before, after in rows:
        before, after = _loads(before), _loads(after)
        if table == "parts":
            parts.setdefault(row_id, [before, None])[1] = after
        elif table == "items" and action == "update":
            items.setdefault(row_id, [before, None])[1] = after
        elif table == "deliverables" and action == "update" and row_id == deliverable_id:
            template = [template[0] if template else before["template"], after["template"]]
        elif table == "numbers" and action == "create":
            (kind,) = conn.execute(
                "SELECT kind FROM sources WHERE id = ?", (after["source_id"],)
            ).fetchone()
            chains = calculated if kind == "calculation" else numbers
            key = (after["item_id"], after["name"])
            chains.setdefault(key, [after["replaces"], None])[1] = after["id"]
    # The QS Calc Engine's own are brought up to date again from the inputs; only an amount or a
    # total the accept made where there was none is ended first.
    fresh = [last for replaced, last in calculated.values() if replaced is None]
    return {
        "parts": parts,
        "items": items,
        "numbers": numbers,
        "fresh": fresh,
        "template": template,
    }


def _moved(conn, head: dict, plan: dict) -> bool:
    """Whether anything the accept wrote has a newer entry now."""
    for part_id, (_, after) in plan["parts"].items():
        now = store.part_now(conn, part_id)
        if now is None or now["version"] != after["version"]:
            return True
    for item_id, (_, after) in plan["items"].items():
        (version,) = conn.execute("SELECT version FROM items WHERE id = ?", (item_id,)).fetchone()
        if version != after["version"]:
            return True
    for _, last in plan["numbers"].values():
        (until,) = conn.execute("SELECT valid_until FROM numbers WHERE id = ?", (last,)).fetchone()
        if until is not None:
            return True
    return bool(plan["template"]) and head["template"]["version"] != plan["template"][1]["version"]


def _end_number(conn, rec: Records, number_id: str, actor: str) -> None:
    """A number the accept added: kept in the ledger, marked `valid_until`, with an audit row."""
    cursor = conn.execute("SELECT * FROM numbers WHERE id = ?", (number_id,))
    old = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    at = rec.clock()
    conn.execute("UPDATE numbers SET valid_until = ? WHERE id = ?", (at, number_id))
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="end",
        table="numbers",
        row_id=number_id,
        before=old,
        after={**old, "valid_until": at},
    )


def _put_back(conn, rec: Records, head: dict, plan: dict, actor: str) -> None:
    reason = copy.fill(copy.UNDO_ACCEPT_REASON, title=head["title"])[head["language"]]
    for part_id, (before, _) in plan["parts"].items():
        now = store.part_now(conn, part_id)
        was = before or {**now, "removed": True}  # a part the accept added is removed again
        store.put_part(
            conn,
            rec,
            deliverable_id=head["id"],
            part_id=part_id,
            kind=now["kind"],
            seq=was["seq"],
            item_id=now["item_id"],
            node=was["node"],
            actor=actor,
            removed=bool(was["removed"]),
        )
    for item_id, (before, _) in plan["items"].items():
        fields = before["fields"]
        ledger.update_item(
            rec,
            item_id,
            fields=json.loads(fields) if isinstance(fields, str) else fields,
            actor=actor,
        )
    for replaced, last in plan["numbers"].values():
        if replaced is None:
            _end_number(conn, rec, last, actor)
            continue
        cursor = conn.execute("SELECT * FROM numbers WHERE id = ?", (replaced,))
        old = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
        ledger.write_correction(
            conn,
            last,
            at=rec.clock(),
            actor=actor,
            value=old["value"],
            reason=reason,
            source_id=old["source_id"],
            dated=old["dated"],
            unit=old["unit"],
            currency=old["currency"],
        )
    for number_id in plan["fresh"]:
        (until,) = conn.execute(
            "SELECT valid_until FROM numbers WHERE id = ?", (number_id,)
        ).fetchone()
        if until is None:
            _end_number(conn, rec, number_id, actor)
    if plan["template"]:
        columns = plan["template"][0]["columns"]
        op = {"op": "set_columns", "columns": columns, "expect": head["template"]["version"]}
        ops.apply(conn, rec, head, op, actor=actor, reason=None)


def _wait_again(conn, rec: Records, head: dict, change: Change, actor: str) -> bool:
    """The change pending again, its `expect` made current; stale when it no longer applies."""
    raw = {k: v for k, v in change.op.items() if k != "expect"}
    try:
        op = ops.validate(rec, head, raw, actor=change.author)
        status = "pending"
    except RecordsError:
        op, status = change.op, "stale"
    shown = {"before": change.before, "after": change.after, "follows": change.follows}
    shown["note"] = change.note
    at = rec.clock()
    conn.execute(
        "UPDATE changes SET op = ?, status = ?, decided_at = ?, decided_by = ?, version_n = NULL"
        " WHERE id = ?",
        (
            _dump({**op, _SHOWN: shown}),
            status,
            None if status == "pending" else at,
            None if status == "pending" else actor,
            change.id,
        ),
    )
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="update",
        table="changes",
        row_id=change.id,
        before={"id": change.id, "status": change.status, "version_n": change.version_n},
        after={"id": change.id, "status": status, "version_n": None, "op": op},
    )
    return status == "pending"


def undo_accept(rec: Records, deliverable_id: str, n: int, *, actor: str) -> dict:
    """Takes back the accept that saved version `n`, which must still be the latest: everything
    it wrote gets a new entry as it was, amounts and totals are brought up to date, and a new
    Saved version is saved. Its changes wait again. Returns {"version", "pending"}. Refused with
    UNDO_TOO_LATE or UNDO_RECORDS (409); only the engineer undoes (ValueError otherwise)."""
    _engineer_only(actor)
    with rec.write(actor) as conn:
        head = ops.deliverable(conn, deliverable_id)
        held, audit_from = _held(conn, deliverable_id, n)
        plan = _plan(conn, deliverable_id, n, audit_from)
        if _moved(conn, head, plan):
            raise _late()
        _put_back(conn, rec, head, plan, actor)
        if head["kind"] == "sheet":
            calc.bring_up_to_date(rec, deliverable_id, actor=actor)
        version = store.save_version(conn, rec, deliverable_id, by=actor, change_ids=[])
        waiting = [c.id for c in held if _wait_again(conn, rec, head, c, actor)]
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return {"version": version, "pending": waiting}
