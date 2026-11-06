"""The client's BOQ as `boq_import` read it: the canvas's read-only Client BOQ frames, and the
check of Priced BOQ rows that are not in it.

A Client BOQ is shown as the client wrote it: each item's code, description and unit as first
imported, and each quantity, rate and amount as first recorded from its cell (with that cell as
its source), even when a Deliverable built on the same item later changed it. One frame per
file: every import of the file adds to it. A file replaced by a newer version is not shown.

`not_in_client` is code, not AI: a Priced BOQ row is in the client's BOQ when it is one of the
imported items, or its code or its description is one of theirs (compared as `arabic.clean`
writes them). Nothing here writes."""

import json
import re

from qsone import copy
from qsone.deliverables import calc, store, template
from qsone.records import arabic, boq
from qsone.records.project import Records, RecordsError

NUMBERS = ("quantity", "rate", "amount")
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")


def _imports(conn) -> dict[str, dict]:
    """{file id: {"at", "columns"}} of every import of a current file: the newest import's
    time, and every column any import of it mapped."""
    out: dict[str, dict] = {}
    for at, after in conn.execute(
        "SELECT a.at, a.after FROM audit a JOIN files f"
        " ON f.id = json_extract(a.after, '$.file_id') AND f.valid_until IS NULL"
        " WHERE a.action = 'import' AND a.table_name = 'boq_imports' ORDER BY a.id"
    ):
        found = json.loads(after)
        entry = out.setdefault(found["file_id"], {"at": at, "columns": set()})
        entry["at"] = at
        entry["columns"] |= set(found.get("columns", {}))
    return out


def _items(conn, file_id: str) -> list[dict]:
    """The file's imported items and headings as first written, in sheet and row order."""
    rows = conn.execute(
        "SELECT a.row_id, a.after FROM audit a JOIN items i ON i.id = a.row_id"
        " WHERE a.table_name = 'items' AND a.action = 'create'"
        " AND json_extract(a.after, '$.fields.file_id') = ? AND i.kind IN (?, ?)",
        (file_id, boq.ITEM, boq.HEADING),
    ).fetchall()
    items = [json.loads(after) | {"id": item_id} for item_id, after in rows]
    return sorted(items, key=lambda i: (i["fields"].get("sheet", ""), i["fields"].get("row", 0)))


def list_imported(rec: Records) -> list[dict]:
    """Each current file with an imported BOQ, newest import first: {"file_id", "name", "items",
    "headings", "at"} (the canvas's Client BOQ frames)."""
    with rec.read() as conn:
        found = _imports(conn)
        out = []
        for file_id, entry in found.items():
            (name,) = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,)).fetchone()
            kinds = [i["kind"] for i in _items(conn, file_id)]
            out.append(
                {
                    "file_id": file_id,
                    "name": name,
                    "items": kinds.count(boq.ITEM),
                    "headings": kinds.count(boq.HEADING),
                    "at": entry["at"],
                }
            )
    return sorted(out, key=lambda e: e["at"], reverse=True)


def summary(rec: Records, file_id: str) -> dict | None:
    """The file's entry of `list_imported`, or None."""
    return next((e for e in list_imported(rec) if e["file_id"] == file_id), None)


def _language(items: list[dict]) -> str:
    text = " ".join(str(i["fields"].get("description", "")) for i in items)
    return "ar" if len(_ARABIC.findall(text)) >= len(_LATIN.findall(text)) else "en"


def _numbers(conn, file_id: str, item_ids: list[str]) -> tuple[dict, dict]:
    """The numbers first recorded from the file's cells, {item id: {name: cell}}, and their
    sources (with the file's id, for the screen's jump to the file)."""
    rows = conn.execute(
        "SELECT n.id, n.item_id, n.name, n.value, n.unit, n.currency, n.source_id, n.dated,"
        " s.kind, s.title, s.locator, s.url, s.dated, f.name"
        " FROM numbers n JOIN sources s ON s.id = n.source_id JOIN files f ON f.id = s.file_id"
        " WHERE s.file_id = :f AND s.kind = 'boq'"
        " AND n.item_id IN (SELECT value FROM json_each(:ids)) ORDER BY n.recorded_at, n.rowid",
        {"f": file_id, "ids": json.dumps(item_ids)},
    ).fetchall()
    numbers: dict[str, dict] = {}
    sources: dict[str, dict] = {}
    for number_id, item_id, name, value, unit, currency, source_id, dated, *source in rows:
        on_item = numbers.setdefault(item_id, {})
        if name in on_item:  # a later number on the same item is not the client's
            continue
        on_item[name] = calc.number_cell(
            value=value,
            unit=unit,
            currency=currency,
            number_id=number_id,
            source_id=source_id,
            dated=dated,
            source_kind=source[0],
        )
        kind, title, locator, url, source_dated, file_name = source
        sources[source_id] = {
            "kind": kind,
            "title": title,
            "file_name": file_name,
            "file_id": file_id,
            "locator": json.loads(locator),
            "url": url,
            "dated": source_dated,
        }
    return numbers, sources


def _text(value) -> dict | None:
    return {"text": value} if isinstance(value, str) and value.strip() else None


def sheet(rec: Records, file_id: str) -> dict:
    """The Client BOQ of the file as a read-only Sheet view (the shape of a Deliverable's, so
    the Sheet viewer draws it): headings as section rows, items with their numbers and sources.
    CLIENT_BOQ_NOT_FOUND (404) when nothing was imported from the file."""
    with rec.read() as conn:
        found = _imports(conn).get(file_id)
        if found is None:
            raise RecordsError(copy.CLIENT_BOQ_NOT_FOUND, status=404, field="file")
        (name,) = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,)).fetchone()
        items = _items(conn, file_id)
        numbers, sources = _numbers(conn, file_id, [i["id"] for i in items])
    mapped = found["columns"] | {"description", "unit"}
    columns = [
        {
            "key": c["key"],
            "from": c["from"],
            "label": c["label"],
            "kind": "number" if c["key"] in NUMBERS else "text",
            "edit": False,  # the client's document: never edited here
            "frozen": c.get("frozen", False),
            "wrap": c.get("wrap", False),
            "width": c.get("width", template.WIDTH),
        }
        for c in template.base("sheet")["default_columns"]
        if c["key"] in mapped
    ]
    rows = []
    for item in items:
        fields = item["fields"]
        if item["kind"] == boq.HEADING:
            title = fields.get("description", "")
            rows.append(
                {
                    "id": item["id"],
                    "kind": "section",
                    "level": 1,
                    "item_id": item["id"],
                    "title": title,
                    "version": 1,
                    "cells": {
                        k.removeprefix("file_"): v
                        for k, v in numbers.get(item["id"], {}).items()
                        if k.removeprefix("file_") in NUMBERS
                    },
                }
            )
            continue
        cells = {
            k: v
            for k, v in (
                ("code", _text(item.get("code"))),
                ("description", _text(fields.get("description"))),
                ("unit", _text(fields.get("unit"))),
            )
            if v is not None
        }
        cells |= {k: v for k, v in numbers.get(item["id"], {}).items() if k in NUMBERS}
        rows.append(
            {
                "id": item["id"],
                "kind": "item",
                "item_id": item["id"],
                "item_version": 1,
                "version": 1,
                "code": item.get("code"),
                "cells": cells,
            }
        )
    return {
        "id": f"client-boq-{file_id}",
        "kind": "sheet",
        "variant": "client_boq",
        "title": name,
        "file_id": file_id,
        "language": _language(items),
        "status": "draft",
        "code": None,
        "same_provider": False,
        "off_desk": False,
        "version": 1,
        "at": found["at"],
        "revision": None,
        "sample": any(s["kind"] == "sample" for s in sources.values()),
        "columns": columns,
        "rows": rows,
        "total": None,
        "sources": sources,
        "incomplete": {},
        "progress": None,
        "pending": 0,
        "open_comments": 0,
        "records_moved": False,
    }


# Rows not in the client's BOQ -----------------------------------------------------------------


def _same(text) -> str:
    """A code or description as compared: `arabic.clean`, then case-folded."""
    return arabic.clean(text or "").casefold() if isinstance(text, str) else ""


def _description(v: dict, row: dict) -> str:
    key = next((c["key"] for c in v["columns"] if c.get("from") == "field:description"), None)
    cell = row["cells"].get(key or "description") or {}
    return cell.get("text", "")


def not_in_client(rec: Records, deliverable_id: str, *, version: int | None = None) -> list[dict]:
    """The item rows of a Priced BOQ Sheet (variant `boq`) whose item is not in any imported
    client BOQ of the project, in order: [{"row": part id, "code", "description"}]. Empty when
    the project has no imported client BOQ, or for any other Deliverable."""
    v = store.view(rec, deliverable_id, version=version)
    if v["kind"] != "sheet" or v.get("variant") != "boq":
        return []
    with rec.read() as conn:
        theirs = [i for file_id in _imports(conn) for i in _items(conn, file_id)]
    theirs = [i for i in theirs if i["kind"] == boq.ITEM]
    if not theirs:
        return []
    ids = {i["id"] for i in theirs}
    codes = {_same(i.get("code")) for i in theirs} - {""}
    descriptions = {_same(i["fields"].get("description")) for i in theirs} - {""}
    out = []
    for row in v["rows"]:
        if row["kind"] != "item" or row["item_id"] in ids:
            continue
        code, description = row.get("code") or "", _description(v, row)
        if _same(code) in codes or _same(description) in descriptions:
            continue
        out.append({"row": row["id"], "code": code, "description": description})
    return out
