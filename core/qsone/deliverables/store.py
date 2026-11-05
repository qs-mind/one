"""The Deliverable store: create a Sheet or a Document, keep its parts, and rebuild its view.

A Deliverable holds no values. Its parts (Sheet rows and Document blocks) point at items and
ledger numbers, and its amounts and totals are ledger numbers that the QS Calc Engine saved. A part
is never deleted: a change writes a new row version and marks the old one `valid_until`.

A Deliverable is pinned to its latest Saved version. Its view is rebuilt for that version's time
from three places: the parts valid then, each item's fields from its audit row then, and the
ledger as of then. The current view and any past version come from the same code. The template
(columns) is read from the Deliverable's newest audit row at that time, so a change of columns
must write one. Nothing here computes a number or calls the QS Calc Engine.
"""

import json
import re
import zlib
from uuid import uuid4

from qsone import copy
from qsone.deliverables import calc, template
from qsone.records import audit, ledger
from qsone.records.project import Records, RecordsError

LANGUAGES = ("ar", "en")
_SEQ = 1024.0  # parts are written 1024, 2048, ... apart, so a row fits between two
# A run of digits (Western, Arabic-Indic or Persian) with its decimal or grouping marks.
_DIGITS = re.compile(r"[0-9٠-٩۰-۹]+(?:[.,٫٬][0-9٠-٩۰-۹]+)*")

_AT = "valid_from <= :at AND (valid_until IS NULL OR valid_until > :at)"
_NUMBER_AT = "n.recorded_at <= :at AND (n.valid_until IS NULL OR n.valid_until > :at)"
_NUMBER_COLUMNS = (
    "n.id, n.item_id, n.name, n.value, n.unit, n.currency, n.source_id, n.dated,"
    " s.kind, s.title, s.locator, s.url, s.dated, f.name, s.file_id"
)
_NUMBER_JOIN = (
    "FROM numbers n JOIN sources s ON s.id = n.source_id LEFT JOIN files f ON f.id = s.file_id"
)


def _not_found(field: str = "deliverable") -> RecordsError:
    return RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field=field)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# Creating.


def _rows_checked(rows: list[dict]) -> list[dict]:
    """Each row is {"section": title, "level": n} (with an optional "item_id") or {"item_id"}."""
    out = []
    for i, row in enumerate(rows):
        field = f"rows[{i}]"
        if not isinstance(row, dict):
            raise RecordsError(copy.ROW_NOT_FOUND, status=422, field=field)
        if "section" in row:
            title, level = row["section"], row.get("level", 1)
            if (
                set(row) - {"section", "level", "item_id"}
                or not (isinstance(title, str) and title.strip())
                or not (isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 6)
            ):
                raise RecordsError(copy.ROW_NOT_FOUND, status=422, field=field)
            out.append({"section": title.strip(), "level": level, "item_id": row.get("item_id")})
        elif set(row) == {"item_id"} and isinstance(row["item_id"], str):
            out.append({"item_id": row["item_id"]})
        else:
            raise RecordsError(copy.ROW_NOT_FOUND, status=422, field=field)
    return out


def _template(kind: str, columns, rows, blocks) -> dict:
    base = template.base(kind)
    if kind == "sheet":
        if blocks is not None:
            raise RecordsError(copy.NODE_NOT_ALLOWED, status=422, field="blocks")
        return {
            "kind": "sheet",
            "base": base["version"],
            "version": 1,
            "columns": template.columns_for(columns),
            "ops": base["ops"],
            "anchors": base["anchors"],
        }
    if columns is not None:
        raise RecordsError(copy.COLUMN_NOT_ALLOWED, status=422, field="columns")
    if rows is not None:
        raise RecordsError(copy.ROW_NOT_FOUND, status=422, field="rows")
    for i, block in enumerate(blocks or []):
        try:
            template.check_node(block)
        except RecordsError as e:
            raise RecordsError(e.text, status=422, field=f"blocks[{i}]") from None
    return {**base, "base": base["version"], "version": 1}


def create(
    rec: Records,
    *,
    kind: str,
    variant: str,
    title: str,
    language: str,
    actor: str,
    columns: list[dict] | None = None,
    rows: list[dict] | None = None,
    blocks: list[dict] | None = None,
    desk: dict | None = None,
    off_desk: bool = False,
) -> str:
    """A new Deliverable, complete at version 1, in one write: the Deliverable, an item of kind
    `section` for each section row without one and an item of kind `bill` for a Sheet's total,
    the parts, every calculated cell brought up to date, version 1 and the audit rows. Then it
    is published on the activity stream. Refusals: TEMPLATE_UNKNOWN (kind), COLUMN_NOT_ALLOWED
    (columns[i]...), ROW_NOT_FOUND (rows[i]), NODE_NOT_ALLOWED (blocks[i])."""
    tmpl = _template(kind, columns, rows, blocks)
    if language not in LANGUAGES:
        raise ValueError(f"language must be one of {LANGUAGES}")
    if not title.strip() or not variant.strip():
        raise ValueError("a Deliverable needs a title and a variant")
    checked = _rows_checked(rows or [])
    deliverable_id = uuid4().hex
    with rec.write(actor) as conn:
        wanted = [(i, r["item_id"]) for i, r in enumerate(checked) if r.get("item_id")]
        known = {
            item_id
            for (item_id,) in conn.execute(
                "SELECT id FROM items WHERE id IN (SELECT value FROM json_each(?))",
                (_dump([item_id for _, item_id in wanted]),),
            )
        }
        for i, item_id in wanted:
            if item_id not in known:
                raise RecordsError(copy.ROW_NOT_FOUND, status=422, field=f"rows[{i}]")
        at = rec.clock()
        bill = None
        if kind == "sheet":
            bill = ledger.write_item(conn, at=at, actor=actor, kind="bill", code=title)
        row = {
            "id": deliverable_id,
            "kind": kind,
            "variant": variant,
            "title": title,
            "language": language,
            "template": tmpl,
            "total_item_id": bill,
            "desk": desk,
            "off_desk": int(off_desk),
            "created_at": at,
            "created_by": actor,
            "updated_at": at,
        }
        stored = {
            **row,
            "template": _dump(tmpl),
            "desk": None if desk is None else _dump(desk),
        }
        marks = ", ".join("?" * len(stored))
        conn.execute(
            f"INSERT INTO deliverables ({', '.join(stored)}) VALUES ({marks})",
            tuple(stored.values()),
        )
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="create",
            table="deliverables",
            row_id=deliverable_id,
            before=None,
            after=row,
        )
        for n, part in enumerate(checked if kind == "sheet" else blocks or [], start=1):
            if kind == "document":
                kind_, item_id, node = "block", None, part
            elif "section" in part:
                item_id = part["item_id"] or ledger.write_item(
                    conn, at=at, actor=actor, kind="section", code=part["section"]
                )
                kind_, node = "section", {"title": part["section"], "level": part["level"]}
            else:
                kind_, item_id, node = "item", part["item_id"], {}
            put_part(
                conn,
                rec,
                deliverable_id=deliverable_id,
                part_id=None,
                kind=kind_,
                seq=_SEQ * n,
                item_id=item_id,
                node=node,
                actor=actor,
            )
        if kind == "sheet":
            calc.bring_up_to_date(rec, deliverable_id, actor=actor)
        save_version(conn, rec, deliverable_id, by=actor, change_ids=[])
    from qsone.deliverables import events  # events reads this module's entries

    events.publish_deliverable(rec, rec.id, deliverable_id)
    return deliverable_id


# Parts and versions, inside the caller's write.


def part_now(conn, part_id: str) -> dict | None:
    """The part's current row version, with its node read, or None."""
    cursor = conn.execute(
        "SELECT id, deliverable_id, seq, kind, item_id, node, version, valid_from, removed"
        " FROM parts WHERE id = ? AND valid_until IS NULL",
        (part_id,),
    )
    found = cursor.fetchone()
    if found is None:
        return None
    part = dict(zip([d[0] for d in cursor.description], found, strict=True))
    part["node"] = json.loads(part["node"])
    part["removed"] = bool(part["removed"])
    return part


def put_part(
    conn,
    rec: Records,
    *,
    deliverable_id: str,
    part_id: str | None,
    kind: str,
    seq: float,
    item_id: str | None,
    node: dict,
    actor: str,
    removed: bool = False,
) -> str:
    """Writes a new row version of the part (a new part when `part_id` is None) and marks the
    old one `valid_until`; returns the part id."""
    at = rec.clock()
    old = None if part_id is None else part_now(conn, part_id)
    if part_id is not None and old is None:
        raise RecordsError(copy.ROW_NOT_FOUND, status=422, field="row")
    part_id = part_id or uuid4().hex
    if old is not None:
        conn.execute(
            "UPDATE parts SET valid_until = ? WHERE id = ? AND valid_until IS NULL", (at, part_id)
        )
    new = {
        "id": part_id,
        "deliverable_id": deliverable_id,
        "seq": float(seq),
        "kind": kind,
        "item_id": item_id,
        "node": node,
        "version": 1 if old is None else old["version"] + 1,
        "valid_from": at,
        "removed": removed,
    }
    stored = {**new, "node": _dump(node), "removed": int(removed)}
    conn.execute(
        f"INSERT INTO parts ({', '.join(stored)}) VALUES ({', '.join('?' * len(stored))})",
        tuple(stored.values()),
    )
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="create" if old is None else "update",
        table="parts",
        row_id=part_id,
        before=old,
        after=new,
    )
    return part_id


def save_version(conn, rec: Records, deliverable_id: str, *, by: str, change_ids: list[str]) -> int:
    """Inside a write: the next Saved version, at this moment, listing the changes it holds."""
    (last,) = conn.execute(
        "SELECT coalesce(max(n), 0) FROM versions WHERE deliverable_id = ?", (deliverable_id,)
    ).fetchone()
    n, at = last + 1, rec.clock()
    conn.execute(
        "INSERT INTO versions (deliverable_id, n, at, by, changes) VALUES (?, ?, ?, ?, ?)",
        (deliverable_id, n, at, by, _dump(change_ids)),
    )
    conn.execute("UPDATE deliverables SET updated_at = ? WHERE id = ?", (at, deliverable_id))
    row = {"deliverable_id": deliverable_id, "n": n, "at": at, "by": by, "changes": change_ids}
    audit.record(
        conn,
        at=at,
        actor=by,
        action="create",
        table="versions",
        row_id=f"{deliverable_id}/{n}",
        before=None,
        after=row,
    )
    return n


# Reading.


def status(rec: Records, deliverable_id: str) -> dict:
    """{"status": "draft" | "checked" | "signed_off", "code", "same_provider", "off_desk"}."""
    with rec.read() as conn:
        head = _head(conn, deliverable_id)
        return _status(conn, deliverable_id, head["latest"], head["off_desk"])


def _head(conn, deliverable_id: str) -> dict:
    cursor = conn.execute(
        "SELECT id, kind, variant, title, language, total_item_id, desk, off_desk, updated_at,"
        " (SELECT max(n) FROM versions WHERE deliverable_id = d.id) AS latest"
        " FROM deliverables d WHERE id = ?",
        (deliverable_id,),
    )
    found = cursor.fetchone()
    if found is None:
        raise _not_found()
    head = dict(zip([d[0] for d in cursor.description], found, strict=True))
    head["desk"] = None if head["desk"] is None else json.loads(head["desk"])
    head["off_desk"] = bool(head["off_desk"])
    return head


def _status(conn, deliverable_id: str, latest: int, off_desk: bool) -> dict:
    check, signed = conn.execute(
        "SELECT (SELECT json_array(version_n, code, same_provider) FROM checks"
        "  WHERE deliverable_id = :d ORDER BY at DESC, rowid DESC LIMIT 1),"
        " EXISTS (SELECT 1 FROM revisions WHERE deliverable_id = :d AND signed_off = 1"
        "  AND version_n = :n)",
        {"d": deliverable_id, "n": latest},
    ).fetchone()
    version_n, code, same_provider = json.loads(check) if check else (None, None, 0)
    current = version_n == latest
    state = "signed_off" if signed else "checked" if current else "draft"
    return {
        "status": state,
        "code": code if current else None,
        "same_provider": bool(same_provider) if current else False,
        "off_desk": off_desk,
    }


def view(
    rec: Records, deliverable_id: str, *, version: int | None = None, revision: int | None = None
) -> dict:
    """The Deliverable as the screen, the exports and the agents read it: the latest Saved version,
    or version `n`, rebuilt; or a Revision's frozen snapshot. Numbers are exact strings."""
    with rec.read() as conn:
        if revision is not None:
            found = conn.execute(
                "SELECT snapshot FROM revisions WHERE deliverable_id = ? AND no = ?",
                (deliverable_id, revision),
            ).fetchone()
            if found is None:
                raise _not_found("revision")
            return json.loads(zlib.decompress(found[0]))
        return _view(conn, _head(conn, deliverable_id), version)


def _view(conn, head: dict, version: int | None) -> dict:
    d = head["id"]
    n = head["latest"] if version is None else version
    found = conn.execute(
        "SELECT v.at, (SELECT after FROM audit WHERE table_name = 'deliverables' AND row_id = :d"
        "  AND at <= v.at ORDER BY id DESC LIMIT 1),"
        " (SELECT json_array(no, version_n, signed_off) FROM revisions WHERE deliverable_id = :d"
        "  ORDER BY no DESC LIMIT 1),"
        " (SELECT count(*) FROM changes WHERE deliverable_id = :d AND status = 'pending'),"
        " (SELECT count(*) FROM comments WHERE deliverable_id = :d AND status = 'open'"
        "  AND parent_id IS NULL)"
        " FROM versions v WHERE v.deliverable_id = :d AND v.n = :n",
        {"d": d, "n": n},
    ).fetchone()
    if found is None:
        raise _not_found("version")
    at, then, revision, pending, open_comments = found
    revision = json.loads(revision) if revision else None
    out = {
        "id": d,
        "kind": head["kind"],
        "variant": head["variant"],
        "title": head["title"],
        "language": head["language"],
        **_status(conn, d, head["latest"], head["off_desk"]),
        "version": n,
        "at": at,
        "revision": None
        if revision is None
        else {"no": revision[0], "version": revision[1], "signed_off": bool(revision[2])},
    }
    if head["kind"] == "sheet":
        body = _sheet_view(conn, d, head["total_item_id"], json.loads(then)["template"], at)
    else:
        body = _document_view(conn, d, at)
    moved = body.pop("records_moved")
    return out | body | {"pending": pending, "open_comments": open_comments, "records_moved": moved}


def _numbers(conn, item_ids: list[str], at: str) -> tuple[dict, dict]:
    """The items' numbers as of `at` ({item id: {name: cell}}, newest wins) and their sources."""
    rows = conn.execute(
        f"SELECT {_NUMBER_COLUMNS} {_NUMBER_JOIN}"
        f" WHERE n.item_id IN (SELECT value FROM json_each(:ids)) AND {_NUMBER_AT}"
        " ORDER BY n.recorded_at, n.rowid",
        {"ids": _dump(item_ids), "at": at},
    ).fetchall()
    by_item: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    for row in rows:
        item_id, name, cell, source_id, source = _read_number(row)
        by_item.setdefault(item_id, {})[name] = cell
        sources[source_id] = source
    return by_item, sources


def _read_number(row) -> tuple:
    """A row of `_NUMBER_COLUMNS` as (item id, name, cell, source id, source)."""
    number_id, item_id, name, value, unit, currency, source_id, dated = row[:8]
    kind, title, locator, url, source_dated, file_name, file_id = row[8:]
    cell = calc.number_cell(
        value=value,
        unit=unit,
        currency=currency,
        number_id=number_id,
        source_id=source_id,
        dated=dated,
        source_kind=kind,
    )
    source = {
        "kind": kind,
        "title": title,
        "file_name": file_name,
        "file_id": file_id,
        "locator": json.loads(locator),
        "url": url,
        "dated": source_dated,
    }
    return item_id, name, cell, source_id, source


def _sample(conn, cells: list[dict], sources: dict) -> bool:
    """Any shown number from a `sample` source, or any input, at any depth, of a shown
    calculation."""
    if any(s["kind"] == "sample" for s in sources.values()):
        return True
    calculated = [c["number_id"] for c in cells if c["calculated"]]
    if not calculated:
        return False
    (found,) = conn.execute(
        "WITH RECURSIVE walk(id) AS (SELECT value FROM json_each(?) UNION"
        " SELECT ci.number_id FROM walk JOIN calculations c ON c.output = walk.id"
        " JOIN calc_inputs ci ON ci.calc_id = c.id)"
        " SELECT EXISTS (SELECT 1 FROM walk JOIN numbers n ON n.id = walk.id"
        " JOIN sources s ON s.id = n.source_id WHERE s.kind = 'sample')",
        (_dump(calculated),),
    ).fetchone()
    return bool(found)


def _moved(conn, item_ids: list[str], at: str) -> bool:
    """Whether the audit trail has item or number rows for these items after `at`."""
    (found,) = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM audit WHERE row_id IN ("
        "  SELECT value FROM json_each(:ids) UNION ALL"
        "  SELECT id FROM numbers WHERE item_id IN (SELECT value FROM json_each(:ids)))"
        " AND at > :at AND table_name IN ('items', 'numbers'))",
        {"ids": _dump(item_ids), "at": at},
    ).fetchone()
    return bool(found)


def _text(value) -> dict | None:
    return {"text": value} if isinstance(value, str) and value.strip() else None


def _cell(column: dict, source: dict, item: dict, numbers: dict) -> dict | None:
    """One Sheet cell of an item row, or None when it has nothing to show."""
    if "code" in source:
        return _text(item.get("code"))
    fields = item.get("fields", {})
    if "field" in source:
        return _text(fields.get(source["field"]))
    number = numbers.get(source["number"])
    if source["unit"]:
        return _text(number.get("unit")) if number else None
    if number is not None:
        return number
    empty_from = column.get("empty_from")
    return _text(fields.get(empty_from.removeprefix("field:"))) if empty_from else None


def _sheet_view(conn, d: str, bill: str | None, tmpl: dict, at: str) -> dict:
    parts = conn.execute(
        f"SELECT id, kind, item_id, node, version FROM parts WHERE deliverable_id = :d AND {_AT}"
        " AND removed = 0 AND kind IN ('item', 'section') ORDER BY seq",
        {"d": d, "at": at},
    ).fetchall()
    item_ids = [p[2] for p in parts] + ([bill] if bill else [])
    items = {
        row_id: json.loads(after)
        for row_id, after in conn.execute(
            "SELECT row_id, after FROM audit WHERE table_name = 'items'"
            " AND action IN ('create', 'update') AND at <= :at"
            " AND row_id IN (SELECT value FROM json_each(:ids)) ORDER BY id",
            {"at": at, "ids": _dump(item_ids)},
        )
    }  # the newest row of each item wins
    numbers, sources = _numbers(conn, item_ids, at)
    columns = tmpl["columns"]
    read = [(column, template.source_of(column)) for column in columns]
    editable = [c["key"] for c in columns if template.kind_of(c) == "number" and c.get("edit")]
    incomplete = {c["key"]: 0 for c in columns if "calc" in c}
    totals = [(c["key"], s["number"]) for c, s in read if "total" in c]
    rows, done, total_items = [], 0, 0
    for part_id, kind, item_id, node, version in parts:
        on_item = numbers.get(item_id, {})
        if kind == "section":
            node = json.loads(node)
            rows.append(
                {
                    "id": part_id,
                    "kind": "section",
                    "level": node.get("level", 1),
                    "item_id": item_id,
                    "title": node.get("title", ""),
                    "version": version,
                    "cells": {key: on_item[name] for key, name in totals if name in on_item},
                }
            )
            continue
        item = items.get(item_id, {})
        cells = {}
        for column, source in read:
            cell = _cell(column, source, item, on_item)
            if cell is not None:
                cells[column["key"]] = cell
        total_items += 1
        done += all(key in cells for key in editable)
        for key in incomplete:
            incomplete[key] += key not in cells
        rows.append(
            {
                "id": part_id,
                "kind": "item",
                "item_id": item_id,
                "item_version": item.get("version"),
                "version": version,
                "code": item.get("code"),
                "cells": cells,
            }
        )
    on_bill = numbers.get(bill, {})
    shown = [cell for on_item in numbers.values() for cell in on_item.values()]
    return {
        "sample": _sample(conn, shown, sources),
        "columns": [
            {
                "key": c["key"],
                "from": c["from"],  # the Sheet viewer turns a paste into ops by it
                "label": c["label"],
                "kind": template.kind_of(c),
                "edit": c.get("edit", False),
                "frozen": c.get("frozen", False),
                "wrap": c.get("wrap", False),
                "width": c.get("width", template.WIDTH),
            }
            for c in columns
        ],
        "rows": rows,
        "total": next((on_bill[name] for _, name in totals if name in on_bill), None),
        "sources": sources,
        "incomplete": incomplete,
        "progress": {"done": done, "total": total_items},
        "records_moved": _moved(conn, item_ids, at),
    }


def _walk(node: dict):
    """Every node under `node`, itself first, without recursion."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.get("children", [])))


def ref_key(node: dict) -> str | None:
    """The key of an inline reference in a Document view's `refs`: `num:<number id>` or
    `cell:<deliverable id>:<row>:<column>`; None for any other node."""
    if node.get("type") == "num":
        return f"num:{node['number']}"
    if node.get("type") == "cell":
        return f"cell:{node['deliverable']}:{node['row']}:{node['column']}"
    return None


def _document_view(conn, d: str, at: str) -> dict:
    parts = conn.execute(
        f"SELECT id, node, version FROM parts WHERE deliverable_id = :d AND {_AT}"
        " AND removed = 0 AND kind = 'block' ORDER BY seq",
        {"d": d, "at": at},
    ).fetchall()
    blocks, untraced, nums, cell_refs = [], [], [], []
    for part_id, node, version in parts:
        node = json.loads(node)
        blocks.append({"id": part_id, "version": version, "node": node})
        for inner in _walk(node):
            if inner.get("type") == "num":
                nums.append(inner["number"])
            elif inner.get("type") == "cell":
                cell_refs.append(inner)
            elif "type" not in inner:
                found = _DIGITS.finditer(inner.get("text", ""))
                untraced += [{"block": part_id, "text": m[0]} for m in found]
    refs: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    sample = moved = False
    if nums:
        followed = _numbers_followed(conn, nums, at)
        for start, (_, _, cell, source_id, source) in followed.items():
            refs[f"num:{start}"] = cell
            sources[source_id] = source
        moved = _moved(conn, sorted({row[0] for row in followed.values()}), at)
        sample = _sample(conn, [row[2] for row in followed.values()], sources)
    for sheet_id in dict.fromkeys(ref["deliverable"] for ref in cell_refs):
        sheet = _sheet_then(conn, sheet_id, at)
        if sheet is None:
            continue
        (later,) = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM versions WHERE deliverable_id = ? AND at > ?)",
            (sheet_id, at),
        ).fetchone()
        moved, sample = moved or bool(later), sample or sheet["sample"]
        by_row = {row["id"]: row["cells"] for row in sheet["rows"]}
        calculated = {c["key"] for c in sheet["columns"] if c["kind"] == "calc"}
        for ref in (r for r in cell_refs if r["deliverable"] == sheet_id):
            if ref["row"] == calc.BILL_ROW:
                cell = sheet["total"] if ref["column"] in calculated else None
            else:
                cell = by_row.get(ref["row"], {}).get(ref["column"])
            if cell is not None and "value" in cell:
                refs[ref_key(ref)] = cell
                sources[cell["source"]] = sheet["sources"][cell["source"]]
    return {
        "sample": sample,
        "blocks": blocks,
        "refs": refs,
        "untraced": untraced,
        "sources": sources,
        "total": None,
        "progress": None,
        "records_moved": moved,
    }


def _numbers_followed(conn, number_ids: list[str], at: str) -> dict:
    """Each number id, followed through its corrections to the entry valid at `at`:
    {start id: (item id, name, cell, source id, source)}."""
    rows = conn.execute(
        "WITH RECURSIVE chain(start, id) AS (SELECT value, value FROM json_each(:ids)"
        " UNION SELECT chain.start, n.id FROM chain JOIN numbers n ON n.replaces = chain.id)"
        f" SELECT chain.start, {_NUMBER_COLUMNS} FROM chain JOIN numbers n ON n.id = chain.id"
        " JOIN sources s ON s.id = n.source_id LEFT JOIN files f ON f.id = s.file_id"
        f" WHERE {_NUMBER_AT}",
        {"ids": _dump(number_ids), "at": at},
    ).fetchall()
    return {row[0]: _read_number(row[1:]) for row in rows}


def _sheet_then(conn, sheet_id: str, at: str) -> dict | None:
    """The Sheet's view at its latest version saved by `at`, or None (no such Sheet then)."""
    try:
        head = _head(conn, sheet_id)
    except RecordsError:
        return None
    (n,) = conn.execute(
        "SELECT max(n) FROM versions WHERE deliverable_id = ? AND at <= ?", (sheet_id, at)
    ).fetchone()
    if head["kind"] != "sheet" or n is None:
        return None
    return _view(conn, head, n)


# The list: Plan 7's DeliverableInfo, plus "pending", "total" and "sample".


def _entry(conn, head: dict) -> dict:
    v = _view(conn, head, None)
    return {
        "id": v["id"],
        "kind": v["kind"],
        "title": v["title"],
        "language": v["language"],
        "status": v["status"],
        "code": v["code"],
        "same_provider": v["same_provider"],
        "revision": v["revision"]["no"] if v["revision"] else None,
        "desk": head["desk"],
        "off_desk": v["off_desk"],
        "progress": v["progress"],
        "open_comments": v["open_comments"],
        "updated_at": head["updated_at"],
        "pending": v["pending"],
        "total": v["total"],
        "sample": v["sample"],
    }


def entry(rec: Records, deliverable_id: str) -> dict:
    """The Deliverable's list entry."""
    with rec.read() as conn:
        return _entry(conn, _head(conn, deliverable_id))


def list_deliverables(rec: Records) -> list[dict]:
    """Every Deliverable's list entry, the most recently updated first."""
    with rec.read() as conn:
        ids = conn.execute(
            "SELECT id FROM deliverables ORDER BY updated_at DESC, created_at DESC, rowid DESC"
        ).fetchall()
        return [_entry(conn, _head(conn, d)) for (d,) in ids]
