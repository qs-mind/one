"""Suggested changes: every edit waits, as a pending change, until the engineer accepts it.

`propose` checks each operation and tries it in a dry run (apply it, bring its amounts and
totals up to date, save a version, read the view, then roll everything back), so the change can
show what it would do: `before` and `after` for its own cell, row, block or columns, and
`follows`, the amounts and totals the QS Calc Engine would write. They are shown, never trusted:
`accept` does the work again, in one transaction, and saves one Saved version for the batch.

A Deliverable is pinned to its latest Saved version, and that version's view reads the ledger as
of its own time. So a ledger move from outside (a correction in Project Records, an agent's
calculation) shows only through the one pending "Update from Project Records" change, which
`refresh_records_change` keeps current. Any accept saves a new version, which takes the ledger
as it is then, so while that update is pending an accept must name it with the rest
(UPDATE_FIRST otherwise): a move is never taken in without the engineer accepting it.
"""

import json
from dataclasses import dataclass
from uuid import uuid4

from qsone import copy
from qsone.deliverables import calc, events, ops, store, template
from qsone.records import audit
from qsone.records.project import Records, RecordsError

CALC_ACTOR = calc.CALC_ACTOR  # the author of an Update from Project Records
_SHOWN = "_shown"  # the key in a stored op that holds what the change shows


@dataclass(frozen=True)
class Change:
    id: str
    deliverable_id: str
    op: dict
    reason: str | None
    author: str
    comment_id: str | None
    status: str  # pending, accepted, rejected or stale
    created_at: str
    decided_at: str | None
    decided_by: str | None
    version_n: int | None
    before: dict | None  # the cell, row, block or columns as shown now
    after: dict | None  # and as they would be (a number id the dry run made is None)
    follows: list[dict]  # amounts and totals this change recalculates: {row, column, before, after}
    note: dict | None = None  # {en, ar}, e.g. NUMBER_WAS_CALCULATED


class _Undo(Exception):
    """Raised inside a dry run's write so that nothing it did is kept."""


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _engineer_only(actor: str) -> None:
    if actor != ops.ENGINEER:
        raise ValueError("only the engineer accepts or rejects a Suggested change")


# Reading.

_COLUMNS = (
    "id, deliverable_id, op, reason, author, comment_id, status, created_at, decided_at,"
    " decided_by, version_n"
)


def _change(row) -> Change:
    fields = dict(zip([c.strip() for c in _COLUMNS.split(",")], row, strict=True))
    op = json.loads(fields.pop("op"))
    shown = op.pop(_SHOWN, {})
    return Change(
        **fields,
        op=op,
        before=shown.get("before"),
        after=shown.get("after"),
        follows=shown.get("follows", []),
        note=shown.get("note"),
    )


def _changes(conn, deliverable_id: str, where: str = "", args: tuple = ()) -> list[Change]:
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM changes WHERE deliverable_id = ? {where}"
        " ORDER BY created_at, rowid",
        (deliverable_id, *args),
    ).fetchall()
    return [_change(row) for row in rows]


def list_changes(rec: Records, deliverable_id: str, *, status: str | None = None) -> list[Change]:
    """The Deliverable's changes, oldest first; with `status`, only those."""
    with rec.read() as conn:
        ops.deliverable(conn, deliverable_id)
        if status is None:
            return _changes(conn, deliverable_id)
        return _changes(conn, deliverable_id, "AND status = ?", (status,))


def pending(rec: Records, deliverable_id: str) -> list[Change]:
    """The pending changes, oldest first, with the Update from Project Records made current."""
    refresh_records_change(rec, deliverable_id)
    return list_changes(rec, deliverable_id, status="pending")


# Writing a change row, inside a write.


def _insert(conn, rec, deliverable_id, op, shown, *, actor, reason, comment_id) -> Change:
    row = {
        "id": uuid4().hex,
        "deliverable_id": deliverable_id,
        "op": {**op, _SHOWN: shown},
        "reason": reason,
        "author": actor,
        "comment_id": comment_id,
        "status": "pending",
        "created_at": rec.clock(),
        "decided_at": None,
        "decided_by": None,
        "version_n": None,
    }
    stored = {**row, "op": _dump(row["op"])}
    conn.execute(
        f"INSERT INTO changes ({', '.join(stored)}) VALUES ({', '.join('?' * len(stored))})",
        tuple(stored.values()),
    )
    audit.record(
        conn,
        at=row["created_at"],
        actor=actor,
        action="create",
        table="changes",
        row_id=row["id"],
        before=None,
        after=row,
    )
    (found,) = _changes(conn, deliverable_id, "AND id = ?", (row["id"],))
    return found


def _decide(conn, rec, change: Change, status: str, *, actor: str, version_n=None) -> None:
    at = rec.clock()
    conn.execute(
        "UPDATE changes SET status = ?, decided_at = ?, decided_by = ?, version_n = ? WHERE id = ?",
        (status, at, actor, version_n, change.id),
    )
    before = {"id": change.id, "status": change.status, "decided_at": None, "decided_by": None}
    after = {"id": change.id, "status": status, "decided_at": at, "decided_by": actor}
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="update",
        table="changes",
        row_id=change.id,
        before={**before, "version_n": None},
        after={**after, "version_n": version_n},
    )


# The dry run behind every change.


def _settle(conn, value):
    """`value` with every `number_id` and `source` that the rolled-back dry run made set to None:
    they were never kept."""
    found: list[dict] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if "number_id" in current:
                found.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    if not found:
        return value
    numbers = {c["number_id"] for c in found if c["number_id"]}
    sources = {c.get("source") for c in found if c.get("source")}
    kept_numbers = {
        n
        for (n,) in conn.execute(
            "SELECT id FROM numbers WHERE id IN (SELECT value FROM json_each(?))",
            (_dump(sorted(numbers)),),
        )
    }
    kept_sources = {
        s
        for (s,) in conn.execute(
            "SELECT id FROM sources WHERE id IN (SELECT value FROM json_each(?))",
            (_dump(sorted(sources)),),
        )
    }
    for cell in found:
        if cell["number_id"] not in kept_numbers:
            cell["number_id"] = None
        if cell.get("source") and cell["source"] not in kept_sources:
            cell["source"] = None
    return value


def _try(rec, head: dict, op: dict, *, actor: str, reason: str | None) -> tuple[dict, list]:
    """Applies the op, brings its rows up to date, saves a version and reads the view, inside a
    write that is then rolled back. Returns (the view as it would be, the cells it recalculated)."""
    out: list = []
    try:
        with rec.write(actor) as conn:
            rows = ops.apply(conn, rec, head, op, actor=actor, reason=reason)
            follows = []
            if head["kind"] == "sheet":
                follows = calc.bring_up_to_date(rec, head["id"], actor=actor, rows=rows)
            store.save_version(conn, rec, head["id"], by=actor, change_ids=[])
            out += [store.view(rec, head["id"]), follows]
            raise _Undo
    except _Undo:
        pass
    return out[0], out[1]


def _column_of(head: dict, source: dict) -> str | None:
    """The key of the Sheet column that shows this number or field."""
    for column in head["template"].get("columns", []):
        found = template.source_of(column)
        if source.items() <= found.items():
            return column["key"]
    return None


def _shown_of(v: dict, head: dict, op: dict, new: set[str]) -> dict | None:
    """What the op's own target looks like in view `v`: a cell, a row, a block or the columns.
    `new` holds the part ids that only the dry run made."""
    kind = op["op"]
    if kind == "set_pack":
        return {"steps": v["steps"], "files": v["files"]}
    if kind == "set_columns":
        return {"columns": v["columns"]}
    if kind in ops.DOC_OPS:
        if kind == "insert_block":
            return next((b for b in v["blocks"] if b["id"] in new), None)
        return next((b for b in v["blocks"] if b["id"] == op["block"]), None)
    if kind in ("add_item_row", "add_section"):
        return next((r for r in v["rows"] if r["id"] in new), None)
    row = next((r for r in v["rows"] if r["id"] == op["row"]), None)
    if row is None or kind in ("remove_row", "move_row"):
        return row
    if kind == "set_section_title":
        return {"text": row["title"]}
    found = {"number": op["name"], "unit": False} if kind == "set_number" else {"field": op["key"]}
    return row["cells"].get(_column_of(head, found))


def _note(conn, op: dict) -> dict | None:
    """NUMBER_WAS_CALCULATED when a typed number replaces one the QS Calc Engine saved."""
    if op["op"] != "set_number" or op["expect"] is None:
        return None
    found = conn.execute(
        "SELECT s.kind, s.title FROM numbers n JOIN sources s ON s.id = n.source_id WHERE n.id = ?",
        (op["expect"],),
    ).fetchone()
    if found is None or found[0] != "calculation":
        return None
    return copy.fill(copy.NUMBER_WAS_CALCULATED, formula=found[1])


def _shown(conn, rec, head: dict, now: dict, op: dict, *, actor, reason) -> dict:
    then, follows = _try(rec, head, op, actor=actor, reason=reason)
    parts = "blocks" if head["kind"] == "document" else "rows"
    new = {p["id"] for p in then.get(parts, [])} - {p["id"] for p in now.get(parts, [])}
    return _settle(
        conn,
        {
            "before": _shown_of(now, head, op, set()),
            "after": _shown_of(then, head, op, new),
            "follows": follows,
            "note": _note(conn, op),
        },
    )


# Proposing.


def propose(
    rec: Records,
    deliverable_id: str,
    ops_: list[dict],
    *,
    actor: str,
    reason: str | None = None,
    comment_id: str | None = None,
) -> list[Change]:
    """Holds each operation as a pending Suggested change, made by `actor`. Every op is checked
    and tried before any is stored, so a refusal stores nothing; its `field` names the op
    (`ops[2].value`). The ledger is left as it was."""
    if not isinstance(ops_, list) or not ops_:
        raise RecordsError(copy.OP_UNKNOWN, status=422, field="ops")
    with rec.write(actor) as conn:
        head = ops.deliverable(conn, deliverable_id)
        now = store.view(rec, deliverable_id)
        made = []
        for i, raw in enumerate(ops_):
            try:
                op = ops.validate(rec, head, raw, actor=actor)
                made.append((op, _shown(conn, rec, head, now, op, actor=actor, reason=reason)))
            except RecordsError as e:
                e.field = f"ops[{i}]" + (f".{e.field}" if e.field else "")
                raise
        out = [
            _insert(
                conn,
                rec,
                deliverable_id,
                op,
                shown,
                actor=actor,
                reason=reason,
                comment_id=comment_id,
            )
            for op, shown in made
        ]
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return out


# Update from Project Records.


def _why(conn, after: dict | None) -> dict:
    """Why a cell moved: recalculated by the QS Calc Engine, or corrected (with its reason)."""
    if after is None or after.get("calculated"):
        return {"recalculated": True}
    if after.get("number_id") is None:
        return {"corrected": None}  # a text cell: an item field changed
    (reason,) = conn.execute(
        "SELECT reason FROM numbers WHERE id = ?", (after["number_id"],)
    ).fetchone()
    return {"corrected": reason}


def _cells_moved(conn, head: dict, now: dict, then: dict) -> list[dict]:
    """Every shown cell that differs between the pinned view and the view as Project Records
    are now: {row, column, before, after}; a Document's references by block and ref key."""
    out = []
    if head["kind"] == "sheet":
        rows_then = {r["id"]: r for r in then["rows"]}
        for row in now["rows"]:
            cells = rows_then.get(row["id"], {}).get("cells", {})
            for key in dict.fromkeys([*row["cells"], *cells]):
                before, after = row["cells"].get(key), cells.get(key)
                if before != after:
                    out.append({"row": row["id"], "column": key, "before": before, "after": after})
        if now["total"] != then["total"]:
            out.append(
                {
                    "row": calc.BILL_ROW,
                    "column": _total_column(head),
                    "before": now["total"],
                    "after": then["total"],
                }
            )
    else:
        where = {}
        for block in now["blocks"]:
            for node in _walk(block["node"]):
                key = store.ref_key(node)
                if key:
                    where.setdefault(key, block["id"])
        for key in dict.fromkeys([*now["refs"], *then["refs"]]):
            before, after = now["refs"].get(key), then["refs"].get(key)
            if before != after:
                out.append({"row": where.get(key), "column": key, "before": before, "after": after})
    return out


def _walk(node: dict):
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(current.get("children", []))


def _total_column(head: dict) -> str | None:
    return next((c["key"] for c in head["template"].get("columns", []) if "total" in c), None)


def _records_try(rec, head: dict) -> dict:
    """The view as it would be after bringing everything up to date now, rolled back."""
    out: list = []
    try:
        with rec.write(CALC_ACTOR) as conn:
            if head["kind"] == "sheet":
                # a row the engine refuses (two current rates, say) stays as it is: the view
                # names its problem; it never locks the Deliverable
                calc.bring_up_to_date(rec, head["id"], actor=CALC_ACTOR, skipped=[])
            store.save_version(conn, rec, head["id"], by=CALC_ACTOR, change_ids=[])
            out.append(store.view(rec, head["id"]))
            raise _Undo
    except _Undo:
        pass
    return out[0]


def _refresh(conn, rec, head: dict) -> tuple[Change | None, bool]:
    """Inside a write: keeps the one pending Update from Project Records current. Returns it (or
    None) and whether anything was written."""
    d = head["id"]
    [old] = _changes(
        conn, d, "AND status = 'pending' AND json_extract(op, '$.op') = 'update_from_records'"
    ) or [None]
    expect = {"version": ops.latest_version(conn, d), "mark": ops.records_mark(conn, head)}
    if old is not None and old.op["expect"] == expect and head["kind"] == "sheet":
        return old, False  # nothing moved since it was made
    now = store.view(rec, d)
    cells = []
    if now["records_moved"]:
        then = _records_try(rec, head)
        cells = [
            {**cell, "why": _why(conn, cell["after"])}
            for cell in _settle(conn, _cells_moved(conn, head, now, then))
        ]
    if old is not None and cells and old.op["cells"] == cells and old.op["expect"] == expect:
        return old, False
    if old is not None:
        _decide(conn, rec, old, "stale", actor=CALC_ACTOR)
    if not cells:
        return None, old is not None
    op = {"op": "update_from_records", "cells": cells, "expect": expect}
    shown = {"before": None, "after": None, "follows": [], "note": None}
    change = _insert(
        conn,
        rec,
        d,
        op,
        shown,
        actor=CALC_ACTOR,
        reason=copy.RECORDS_MOVED[head["language"]],
        comment_id=None,
    )
    return change, True


def refresh_records_change(rec: Records, deliverable_id: str) -> Change | None:
    """Keeps the one pending "Update from Project Records" current: when Project Records moved
    after the latest version, its cells are the latest version's view against a dry run of
    bringing everything up to date now, each with why it moved. With no difference the pending
    one, if any, is marked stale; when they differ it is replaced by a fresh one. Its author is
    the QS Calc Engine. Call it before reading a view whose `records_moved` is true."""
    with rec.write(CALC_ACTOR) as conn:
        head = ops.deliverable(conn, deliverable_id)
        change, wrote = _refresh(conn, rec, head)
    if wrote:
        events.publish_deliverable(rec, rec.id, deliverable_id)
    return change


# Accepting and rejecting.


def _decided(conn, deliverable_id: str, change_ids: list[str]) -> dict[str, Change]:
    """The named changes of this Deliverable; CHANGE_NOT_PENDING for one already accepted or
    rejected."""
    if not isinstance(change_ids, list) or not all(isinstance(c, str) for c in change_ids):
        raise RecordsError(copy.CHANGE_NOT_PENDING, status=422, field="ids")
    found = {
        c.id: c
        for c in _changes(
            conn, deliverable_id, "AND id IN (SELECT value FROM json_each(?))", (_dump(change_ids),)
        )
    }
    for i, change_id in enumerate(change_ids):
        if change_id in found and found[change_id].status in ("accepted", "rejected"):
            raise RecordsError(copy.CHANGE_NOT_PENDING, status=409, field=f"ids[{i}]")
    return found


def accept(rec: Records, deliverable_id: str, change_ids: list[str], *, actor: str) -> dict:
    """Accepts the named pending changes in one transaction and one Saved version: each change in
    the order it was made (an Update from Project Records first) is applied, or marked stale when
    what it was made against has moved; then the amounts and totals they touch are brought up to
    date, and the version is saved with the ids of the accepted changes. A version takes the
    ledger as it is then, so while an Update from Project Records is pending, an accept that would
    apply other changes must name it too: else UPDATE_FIRST, and nothing is written. Returns
    {"version", "accepted", "stale"}; with nothing accepted, no version is saved. Only the
    engineer accepts (ValueError otherwise)."""
    _engineer_only(actor)
    refresh_records_change(rec, deliverable_id)  # kept even when this accept is refused
    with rec.write(actor) as conn:
        head = ops.deliverable(conn, deliverable_id)
        update, _ = _refresh(conn, rec, head)
        found = _decided(conn, deliverable_id, change_ids)
        todo = [c for c in found.values() if c.status == "pending"]
        todo.sort(key=lambda c: (c.op["op"] != "update_from_records", c.created_at))
        stale = [c for c in change_ids if c not in {t.id for t in todo}]
        if update is not None and update.id not in change_ids:
            if any(not ops.is_stale(conn, head, c.op) for c in todo):
                raise RecordsError(copy.UPDATE_FIRST, status=409, field="ids")
        accepted, rows, everything = [], set(), False
        (audit_from,) = conn.execute("SELECT coalesce(max(id), 0) FROM audit").fetchone()
        for change in todo:
            if ops.is_stale(conn, head, change.op):
                _decide(conn, rec, change, "stale", actor=actor)
                stale.append(change.id)
                continue
            touched = ops.apply(conn, rec, head, change.op, actor=actor, reason=change.reason)
            everything = everything or touched is None
            rows |= set(touched or [])
            accepted.append(change)
        n = None
        if accepted and head["kind"] == "sheet":
            calc.bring_up_to_date(
                rec, deliverable_id, actor=actor, rows=None if everything else rows
            )
        if accepted:
            ids = [c.id for c in accepted]
            n = store.save_version(
                conn, rec, deliverable_id, by=actor, change_ids=ids, audit_from=audit_from
            )
        for change in accepted:
            _decide(conn, rec, change, "accepted", actor=actor, version_n=n)
    if accepted or stale:
        events.publish_deliverable(rec, rec.id, deliverable_id)
    return {"version": n, "accepted": [c.id for c in accepted], "stale": stale}


def accept_mine(rec: Records, deliverable_id: str, *, actor: str) -> dict:
    """ "Accept all mine": every pending change the engineer made himself, as one accept."""
    _engineer_only(actor)
    ids = [c.id for c in pending(rec, deliverable_id) if c.author == actor]
    if not ids:
        return {"version": None, "accepted": [], "stale": []}
    return accept(rec, deliverable_id, ids, actor=actor)


def reject(rec: Records, deliverable_id: str, change_ids: list[str], *, actor: str) -> list[str]:
    """Rejects the named pending changes; nothing else is written. Returns their ids.
    CHANGE_NOT_PENDING for an unknown id or one already decided. Only the engineer rejects."""
    _engineer_only(actor)
    with rec.write(actor) as conn:
        found = _decided(conn, deliverable_id, change_ids)
        for i, change_id in enumerate(change_ids):
            if change_id not in found or found[change_id].status != "pending":
                raise RecordsError(copy.CHANGE_NOT_PENDING, status=409, field=f"ids[{i}]")
        for change_id in change_ids:
            _decide(conn, rec, found[change_id], "rejected", actor=actor)
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return list(change_ids)


def unreject(rec: Records, deliverable_id: str, change_ids: list[str], *, actor: str) -> list[str]:
    """Undo after a reject: the named changes that are still rejected wait again (nothing else
    was written by the reject, so nothing else moves). Returns their ids. Only the engineer."""
    _engineer_only(actor)
    with rec.write(actor) as conn:
        back = [
            c
            for c in _changes(
                conn,
                deliverable_id,
                "AND status = 'rejected' AND id IN (SELECT value FROM json_each(?))",
                (_dump(change_ids),),
            )
        ]
        for change in back:
            _decide(conn, rec, change, "pending", actor=actor)
    if back:
        events.publish_deliverable(rec, rec.id, deliverable_id)
    return [c.id for c in back]
