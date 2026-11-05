"""Operations: every edit to a Deliverable is one typed operation, from a closed list.

An operation is a dict with "op" and its fields. `validate` checks it against the Deliverable as it
is now and fills its `expect` (the number id, item version, part version or template version it
was made against); `is_stale` says whether that still holds; `apply` writes it inside the
caller's transaction and returns the Sheet rows whose amounts and totals must be brought up to
date (None: all of them). Each kind is a small pair of functions in `_RULES`. A refusal is a
`RecordsError` whose `field` names the operation's own key (`row`, `numbers[1].value`); the
caller puts the operation's index in front.
"""

import json
from datetime import date

from qsone import copy
from qsone.deliverables import store, template
from qsone.records import audit, ledger
from qsone.records.project import Records, RecordsError

SHEET_OPS = {
    *("set_number", "set_field", "add_item_row", "add_section", "set_section_title"),
    *("remove_row", "move_row", "set_columns"),
}
DOC_OPS = {"set_block", "insert_block", "remove_block", "move_block"}
CORE_OPS = {"update_from_records"}  # made by the core only; refused from propose
ENGINEER = "engineer"  # the one actor whose numbers may come without a source
_SEQ = 1024.0  # a new last part goes this far after the one before it
_GAP = 1e-6  # closer than this, every part is renumbered first


def today() -> str:
    """The machine's local date: the date of a number the engineer types."""
    return date.today().isoformat()


def _refuse(text: dict, field: str | None) -> RecordsError:
    return RecordsError(text, status=422, field=field)


def deliverable(conn, deliverable_id: str) -> dict:
    """What the operations read about a Deliverable: id, kind, title, language, template and
    the bill item."""
    found = conn.execute(
        "SELECT id, kind, title, language, template, total_item_id FROM deliverables WHERE id = ?",
        (deliverable_id,),
    ).fetchone()
    if found is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="deliverable")
    keys = ("id", "kind", "title", "language", "template", "total_item_id")
    head = dict(zip(keys, found, strict=True))
    head["template"] = json.loads(head["template"])
    return head


# Reading the Deliverable as it is now.


def _part(conn, head: dict, part_id, kinds: set[str], field: str) -> dict:
    """The current, not removed part of this Deliverable, of one of `kinds`; else ROW_NOT_FOUND."""
    part = store.part_now(conn, part_id) if isinstance(part_id, str) else None
    if (
        part is None
        or part["deliverable_id"] != head["id"]
        or part["removed"]
        or part["kind"] not in kinds
    ):
        raise _refuse(copy.ROW_NOT_FOUND, field)
    return part


def _after(conn, head: dict, op: dict, kinds: set[str], moving: str | None = None) -> None:
    """`after` is None (first) or another current part to go after."""
    after = op.get("after")
    if after is not None and (after == moving or not isinstance(after, str)):
        raise _refuse(copy.ROW_NOT_FOUND, "after")
    if after is not None:
        _part(conn, head, after, kinds, "after")
    op["after"] = after


def _expect(op: dict, now) -> None:
    """Fills `expect` when it was left out; refuses one that no longer holds."""
    if "expect" not in op:
        op["expect"] = now
    elif op["expect"] != now:
        raise _refuse(copy.CHANGE_STALE, "expect")


def _current_number(conn, item_id: str, name: str) -> dict | None:
    cursor = conn.execute(
        "SELECT n.id, n.unit, n.currency, s.kind, s.title FROM numbers n"
        " JOIN sources s ON s.id = n.source_id WHERE n.item_id = ? AND n.name = ?"
        " AND n.valid_until IS NULL ORDER BY n.recorded_at DESC, n.rowid DESC LIMIT 1",
        (item_id, name),
    )
    found = cursor.fetchone()
    return (
        None
        if found is None
        else dict(zip(("id", "unit", "currency", "kind", "title"), found, strict=True))
    )


def _item_version(conn, item_id: str) -> int:
    return conn.execute("SELECT version FROM items WHERE id = ?", (item_id,)).fetchone()[0]


def _columns(head: dict) -> list[tuple[dict, dict]]:
    return [(c, template.source_of(c)) for c in head["template"].get("columns", [])]


def _number_column(head: dict, name, field: str, *, editable: bool) -> None:
    """A number the Sheet shows in its own column: never a calculated one (AMOUNT_IS_COMPUTED);
    for a typed edit, an editable column."""
    shown = [(c, s) for c, s in _columns(head) if s.get("number") == name and not s["unit"]]
    if any("calc" in c for c, _ in shown):
        raise _refuse(copy.AMOUNT_IS_COMPUTED, field)
    if not shown or (editable and not any(c.get("edit") for c, _ in shown)):
        raise _refuse(copy.OP_NOT_IN_TEMPLATE, field)


def _source_given(conn, number: dict, actor: str, field: str) -> None:
    """An agent's number names an existing source; the engineer's may leave it out."""
    source_id = number.get("source_id")
    if source_id is None and actor == ENGINEER:
        return
    found = (
        isinstance(source_id, str)
        and conn.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone()
    )
    if not found:
        raise _refuse(copy.NUMBER_NEEDS_SOURCE, field)


def _text(op: dict, key: str, *, empty: bool = False) -> str:
    value = op.get(key)
    if not isinstance(value, str) or not (empty or value.strip()):
        raise _refuse(copy.OP_UNKNOWN, key)
    return value if empty else value.strip()


def _only(op: dict, keys: tuple[str, ...]) -> dict:
    """The operation with its own keys only, in a fixed order."""
    return {"op": op["op"], **{k: op[k] for k in keys if k in op}}


_NUMBER_KEYS = ("name", "value", "unit", "currency", "source_id", "dated")


# Sheet operations: validate.


def _v_set_number(conn, head, op, actor):
    part = _part(conn, head, op.get("row"), {"item"}, "row")
    _number_column(head, op.get("name"), "name", editable=True)
    _source_given(conn, op, actor, "source_id")
    now = _current_number(conn, part["item_id"], op["name"])
    _expect(op, now and now["id"])
    return _only(op, ("row", *_NUMBER_KEYS, "expect"))


def _v_set_field(conn, head, op, actor):
    part = _part(conn, head, op.get("row"), {"item"}, "row")
    key = op.get("key")
    if not any(s.get("field") == key and c.get("edit") for c, s in _columns(head)):
        raise _refuse(copy.OP_NOT_IN_TEMPLATE, "key")
    _text(op, "value", empty=True)
    _expect(op, _item_version(conn, part["item_id"]))
    return _only(op, ("row", "key", "value", "expect"))


def _v_add_item_row(conn, head, op, actor):
    _after(conn, head, op, {"item", "section"})
    op["code"] = _text(op, "code")
    fields = op.get("fields", {})
    if not (isinstance(fields, dict) and all(isinstance(v, str) for v in fields.values())):
        raise _refuse(copy.OP_UNKNOWN, "fields")
    numbers = op.get("numbers", [])
    if not isinstance(numbers, list):
        raise _refuse(copy.OP_UNKNOWN, "numbers")
    checked = []
    for j, number in enumerate(numbers):
        at = f"numbers[{j}]"
        if not isinstance(number, dict):
            raise _refuse(copy.OP_UNKNOWN, at)
        _number_column(head, number.get("name"), f"{at}.name", editable=False)
        _source_given(conn, number, actor, f"{at}.source_id")
        checked.append({k: number[k] for k in _NUMBER_KEYS if k in number})
    if len({n["name"] for n in checked}) < len(checked):
        raise _refuse(copy.OP_UNKNOWN, "numbers")
    return {**_only(op, ("after", "code")), "fields": fields, "numbers": checked}


def _level(op: dict) -> int:
    level = op.get("level", 1)
    if not (isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 6):
        raise _refuse(copy.OP_UNKNOWN, "level")
    return level


def _v_add_section(conn, head, op, actor):
    _after(conn, head, op, {"item", "section"})
    op["title"], op["level"] = _text(op, "title"), _level(op)
    return _only(op, ("after", "title", "level"))


def _v_set_section_title(conn, head, op, actor):
    part = _part(conn, head, op.get("row"), {"section"}, "row")
    op["title"] = _text(op, "title")
    _expect(op, part["version"])
    return _only(op, ("row", "title", "expect"))


def _v_remove(key: str, kinds: set[str]):
    def check(conn, head, op, actor):
        part = _part(conn, head, op.get(key), kinds, key)
        _expect(op, part["version"])
        return _only(op, (key, "expect"))

    return check


def _v_move(key: str, kinds: set[str]):
    def check(conn, head, op, actor):
        part = _part(conn, head, op.get(key), kinds, key)
        _after(conn, head, op, kinds, moving=part["id"])
        _expect(op, part["version"])
        return _only(op, (key, "after", "expect"))

    return check


def _v_set_columns(conn, head, op, actor):
    columns = op.get("columns")
    if not isinstance(columns, list):
        raise _refuse(copy.COLUMN_NOT_ALLOWED, "columns")
    op["columns"] = template.columns_for(columns)
    _expect(op, head["template"]["version"])
    return _only(op, ("columns", "expect"))


# Document operations: validate.


def _node(op: dict) -> dict:
    node = op.get("node")
    try:
        template.check_node(node)
    except RecordsError as e:
        raise _refuse(e.text, "node") from None
    return node


def _v_set_block(conn, head, op, actor):
    part = _part(conn, head, op.get("block"), {"block"}, "block")
    op["node"] = _node(op)
    _expect(op, part["version"])
    return _only(op, ("block", "node", "expect"))


def _v_insert_block(conn, head, op, actor):
    _after(conn, head, op, {"block"})
    op["node"] = _node(op)
    return _only(op, ("after", "node"))


# Apply: inside the caller's write. Each returns the rows to bring up to date (None: all).


def _put(conn, rec, head, part, actor, **change) -> str:
    """The part again, as a new row version with `change` (seq, node or removed)."""
    return store.put_part(
        conn,
        rec,
        deliverable_id=head["id"],
        part_id=part["id"],
        kind=part["kind"],
        seq=change.get("seq", part["seq"]),
        item_id=part["item_id"],
        node=change.get("node", part["node"]),
        actor=actor,
        removed=change.get("removed", part["removed"]),
    )


def _in_order(conn, head: dict, leave_out: str | None = None) -> list[dict]:
    rows = conn.execute(
        "SELECT id FROM parts WHERE deliverable_id = ? AND valid_until IS NULL AND removed = 0"
        " ORDER BY seq",
        (head["id"],),
    ).fetchall()
    return [store.part_now(conn, part_id) for (part_id,) in rows if part_id != leave_out]


def _seq_after(conn, rec, head: dict, after: str | None, actor: str, moving=None) -> float:
    """The seq for a part placed after `after` (None: first): the midpoint of its neighbours, or
    the last one's plus 1024. When the midpoint would leave a gap under 1e-6, every part is first
    renumbered 1024 apart, by new row versions."""
    for attempt in (1, 2):
        parts = _in_order(conn, head, leave_out=moving)
        at = next((i for i, p in enumerate(parts) if p["id"] == after), -1) if after else -1
        low = parts[at]["seq"] if at >= 0 else 0.0
        if at + 1 >= len(parts):
            return low + _SEQ
        high = parts[at + 1]["seq"]
        if (high - low) / 2 >= _GAP or attempt == 2:
            return (low + high) / 2
        for n, part in enumerate(parts, start=1):
            _put(conn, rec, head, part, actor, seq=_SEQ * n)
    raise AssertionError("unreachable")


def _manual_reason(head: dict) -> str:
    return copy.fill(copy.MANUAL_EDIT_REASON, title=head["title"])[head["language"]]


def _source_and_date(conn, rec, head: dict, number: dict, actor: str, at: str) -> tuple:
    """The number's source and date: the one it names, dated as given or as its source; or,
    for the engineer's own, a new source of kind `engineer`, dated today."""
    source_id = number.get("source_id")
    if source_id is None:
        source_id = ledger.write_source(
            conn,
            at=at,
            actor=actor,
            kind="engineer",
            title=copy.ENTERED_BY_ENGINEER[head["language"]],
            dated=today(),
        )
        return source_id, number.get("dated") or today()
    (dated,) = conn.execute("SELECT dated FROM sources WHERE id = ?", (source_id,)).fetchone()
    return source_id, number.get("dated") or dated or today()


def _default_unit(conn, item_id: str) -> str | None:
    """A new number's unit, when none is given: the item's own quantity or rate unit."""
    found = conn.execute(
        "SELECT unit FROM numbers WHERE item_id = ? AND valid_until IS NULL AND unit IS NOT NULL"
        " AND name IN ('quantity', 'rate') ORDER BY name LIMIT 1",
        (item_id,),
    ).fetchone()
    return found and found[0]


def _default_currency(conn, head: dict, name: str) -> str | None:
    """A new rate's currency, when none is given: the Sheet's, from any of its current rates."""
    if name != "rate":
        return None
    found = conn.execute(
        "SELECT n.currency FROM numbers n JOIN parts p ON p.item_id = n.item_id"
        " WHERE p.deliverable_id = ? AND p.valid_until IS NULL AND n.name = 'rate'"
        " AND n.valid_until IS NULL AND n.currency IS NOT NULL LIMIT 1",
        (head["id"],),
    ).fetchone()
    return found and found[0]


def _write_number(conn, rec, head, item_id: str, number: dict, actor: str, reason) -> None:
    at = rec.clock()
    source_id, dated = _source_and_date(conn, rec, head, number, actor, at)
    now = _current_number(conn, item_id, number["name"])
    common = {"at": at, "actor": actor, "value": number.get("value"), "dated": dated}
    if now is not None:
        ledger.write_correction(
            conn,
            now["id"],
            **common,
            reason=reason or _manual_reason(head),
            source_id=source_id,
            unit=number.get("unit"),
            currency=number.get("currency"),
        )
        return
    ledger.write_number(
        conn,
        **common,
        item_id=item_id,
        name=number["name"],
        source_id=source_id,
        unit=number.get("unit") or _default_unit(conn, item_id),
        currency=number.get("currency") or _default_currency(conn, head, number["name"]),
    )


def _a_set_number(conn, rec, head, op, actor, reason):
    part = _part(conn, head, op["row"], {"item"}, "row")
    _write_number(conn, rec, head, part["item_id"], op, actor, reason)
    return [part["id"]]


def _a_set_field(conn, rec, head, op, actor, reason):
    part = _part(conn, head, op["row"], {"item"}, "row")
    (fields,) = conn.execute("SELECT fields FROM items WHERE id = ?", (part["item_id"],)).fetchone()
    fields = {**json.loads(fields), op["key"]: op["value"]}
    ledger.update_item(rec, part["item_id"], fields=fields, actor=actor)
    return [part["id"]]


def _a_add_item_row(conn, rec, head, op, actor, reason):
    item_id = ledger.write_item(
        conn, at=rec.clock(), actor=actor, kind="boq_item", code=op["code"], fields=op["fields"]
    )
    for j, number in enumerate(op["numbers"]):
        try:
            _write_number(conn, rec, head, item_id, number, actor, reason)
        except RecordsError as e:
            e.field = f"numbers[{j}]" + (f".{e.field}" if e.field else "")
            raise
    part_id = store.put_part(
        conn,
        rec,
        deliverable_id=head["id"],
        part_id=None,
        kind="item",
        seq=_seq_after(conn, rec, head, op["after"], actor),
        item_id=item_id,
        node={},
        actor=actor,
    )
    return [part_id]


def _a_add_section(conn, rec, head, op, actor, reason):
    item_id = ledger.write_item(conn, at=rec.clock(), actor=actor, kind="section", code=op["title"])
    store.put_part(
        conn,
        rec,
        deliverable_id=head["id"],
        part_id=None,
        kind="section",
        seq=_seq_after(conn, rec, head, op["after"], actor),
        item_id=item_id,
        node={"title": op["title"], "level": op["level"]},
        actor=actor,
    )
    return None  # the rows under it now sum into it, not into the section above


def _a_set_section_title(conn, rec, head, op, actor, reason):
    part = _part(conn, head, op["row"], {"section"}, "row")
    _put(conn, rec, head, part, actor, node={**part["node"], "title": op["title"]})
    return []


def _a_remove(key: str, kinds: set[str]):
    def write(conn, rec, head, op, actor, reason):
        part = _part(conn, head, op[key], kinds, key)
        _put(conn, rec, head, part, actor, removed=True)
        # A removed item row brings every total up to date; a removed section moves its rows.
        return [part["id"]] if part["kind"] == "item" else None

    return write


def _a_move(key: str, kinds: set[str]):
    def write(conn, rec, head, op, actor, reason):
        part = _part(conn, head, op[key], kinds, key)
        order = [p["id"] for p in _in_order(conn, head)]
        before = order[order.index(part["id"]) - 1] if order.index(part["id"]) else None
        seq = _seq_after(conn, rec, head, op["after"], actor, moving=part["id"])
        _put(conn, rec, head, store.part_now(conn, part["id"]), actor, seq=seq)
        if part["kind"] != "item":
            return None
        return [part["id"]] + ([before] if before else [])  # its new and its old sections

    return write


def _a_set_columns(conn, rec, head, op, actor, reason):
    cursor = conn.execute("SELECT * FROM deliverables WHERE id = ?", (head["id"],))
    old = dict(zip([d[0] for d in cursor.description], cursor.fetchone(), strict=True))
    old["template"] = json.loads(old["template"])
    old["desk"] = None if old["desk"] is None else json.loads(old["desk"])
    tmpl = {**old["template"], "columns": op["columns"], "version": op["expect"] + 1}
    at = rec.clock()
    conn.execute(
        "UPDATE deliverables SET template = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tmpl, ensure_ascii=False), at, head["id"]),
    )
    # The view reads a version's columns from this audit row, so it holds the whole row.
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="update",
        table="deliverables",
        row_id=head["id"],
        before=old,
        after={**old, "template": tmpl, "updated_at": at},
    )
    head["template"] = tmpl
    return None


def _a_set_block(conn, rec, head, op, actor, reason):
    part = _part(conn, head, op["block"], {"block"}, "block")
    _put(conn, rec, head, part, actor, node=op["node"])
    return []


def _a_insert_block(conn, rec, head, op, actor, reason):
    store.put_part(
        conn,
        rec,
        deliverable_id=head["id"],
        part_id=None,
        kind="block",
        seq=_seq_after(conn, rec, head, op["after"], actor),
        item_id=None,
        node=op["node"],
        actor=actor,
    )
    return []


def _a_update_from_records(conn, rec, head, op, actor, reason):
    return None  # writes nothing: the new version takes the ledger as it is now


_ROWS = {"item", "section"}
_RULES = {
    "set_number": (_v_set_number, _a_set_number),
    "set_field": (_v_set_field, _a_set_field),
    "add_item_row": (_v_add_item_row, _a_add_item_row),
    "add_section": (_v_add_section, _a_add_section),
    "set_section_title": (_v_set_section_title, _a_set_section_title),
    "remove_row": (_v_remove("row", _ROWS), _a_remove("row", _ROWS)),
    "move_row": (_v_move("row", _ROWS), _a_move("row", _ROWS)),
    "set_columns": (_v_set_columns, _a_set_columns),
    "set_block": (_v_set_block, _a_set_block),
    "insert_block": (_v_insert_block, _a_insert_block),
    "remove_block": (_v_remove("block", {"block"}), _a_remove("block", {"block"})),
    "move_block": (_v_move("block", {"block"}), _a_move("block", {"block"})),
    "update_from_records": (None, _a_update_from_records),
}


def validate(rec: Records, deliverable: dict, op: dict, *, actor: str) -> dict:
    """The operation checked against the Deliverable as it is now, with only its own keys and its
    `expect` filled when it was left out. Refuses an unknown or core-only operation (OP_UNKNOWN),
    one its template does not allow (OP_NOT_IN_TEMPLATE), an edit to a calculated or read-only
    column, a part that is not there (ROW_NOT_FOUND), an `expect` that no longer holds
    (CHANGE_STALE) and an agent's number without a source (NUMBER_NEEDS_SOURCE). The ledger's own
    checks on values, units and dates run when the change is tried (`apply` in a dry run)."""
    kind = op.get("op") if isinstance(op, dict) else None
    if kind not in SHEET_OPS | DOC_OPS:
        raise _refuse(copy.OP_UNKNOWN, "op")
    if kind not in deliverable["template"].get("ops", []):
        raise _refuse(copy.OP_NOT_IN_TEMPLATE, "op")
    with rec.read() as conn:
        return _RULES[kind][0](conn, deliverable, dict(op), actor)


def apply(
    conn, rec: Records, deliverable: dict, op: dict, *, actor: str, reason: str | None
) -> list[str] | None:
    """Writes the operation inside the caller's write: ledger numbers (a correction's reason is
    `reason` or «تعديل يدوي في …»), item fields, parts or the template. Returns the Sheet rows
    whose calculated cells follow it, or None for all of them (a template change keeps
    `deliverable["template"]` current)."""
    return _RULES[op["op"]][1](conn, rec, deliverable, op, actor, reason)


def records_mark(conn, deliverable: dict) -> int | None:
    """The newest audit row about the Sheet's items and their numbers: the moment of Project
    Records an Update from Project Records was made against. None for a Document, whose update
    is checked by its cells."""
    if deliverable["kind"] != "sheet":
        return None
    (found,) = conn.execute(
        "WITH scope(id) AS (SELECT item_id FROM parts WHERE deliverable_id = :d"
        "  AND valid_until IS NULL AND removed = 0 AND item_id IS NOT NULL"
        "  UNION SELECT total_item_id FROM deliverables WHERE id = :d)"
        " SELECT max(id) FROM audit WHERE table_name IN ('items', 'numbers') AND row_id IN ("
        "  SELECT id FROM scope UNION ALL"
        "  SELECT id FROM numbers WHERE item_id IN (SELECT id FROM scope))",
        {"d": deliverable["id"]},
    ).fetchone()
    return found


def latest_version(conn, deliverable_id: str) -> int:
    (n,) = conn.execute(
        "SELECT max(n) FROM versions WHERE deliverable_id = ?", (deliverable_id,)
    ).fetchone()
    return n


def is_stale(conn, deliverable: dict, op: dict) -> bool:
    """Whether what the operation was made against has moved: its number, item, part, the parts
    it goes after, or the template; for an Update from Project Records, the latest version or
    Project Records."""
    kind = op["op"]
    if kind == "update_from_records":
        now = {"version": latest_version(conn, deliverable["id"])}
        now["mark"] = records_mark(conn, deliverable)
        return op.get("expect") != now
    if kind == "set_columns":
        return deliverable["template"]["version"] != op["expect"]
    key = "block" if kind in DOC_OPS else "row"
    kinds = {"block"} if kind in DOC_OPS else _ROWS
    try:
        if op.get("after") is not None:
            _part(conn, deliverable, op["after"], kinds, "after")
        if key not in op:  # add_item_row, add_section, insert_block
            return False
        part = _part(conn, deliverable, op[key], kinds, key)
    except RecordsError:
        return True
    if kind == "set_number":
        now = _current_number(conn, part["item_id"], op["name"])
        return (now and now["id"]) != op["expect"]
    if kind == "set_field":
        return _item_version(conn, part["item_id"]) != op["expect"]
    return part["version"] != op["expect"]
