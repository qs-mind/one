"""The client's own BOQ file: read it for mapping, keep a Fill Plan, preview the fill and make the
filled file from the newest signed-off Revision.

A Fill Plan says which client column is which of our columns, which of them to write, and which
client row is which Sheet row (a part id): `{"sheet": "BOQ", "header_row": 11, "columns": {"rate":
"E", "amount": "F", "code": "A"}, "write": ["rate"], "rows": [{"row": 12, "part": "<part id>"}]}`.
The Lead QS writes it; code fills. Only the engineer accepts a code mismatch (`accept_mismatches`),
so a plan saved by an agent never carries one. Nothing here computes a number: the values come
from the Revision's frozen view, and the bytes are patched by `patch.py`.
"""

import io
import json
from datetime import date, datetime, time
from decimal import Decimal
from uuid import uuid4

import openpyxl
from openpyxl.utils import get_column_letter

from qsone import copy
from qsone.clientfile import patch
from qsone.clientfile.patch import Write
from qsone.deliverables import store
from qsone.records import arabic, audit, files
from qsone.records.project import Records, RecordsError

OUT_SUFFIX = " - QS Mind One"


def _refused(text: dict, field: str | None = None, status: int = 422) -> RecordsError:
    return RecordsError(text, status=status, field=field)


def _client_file(rec: Records, file_id: str) -> tuple[str, bytes]:
    """(name, bytes) of an xlsx or xlsm in Project Records. FILE_NOT_IN_PROJECT (404) for an
    unknown id."""
    with rec.read() as conn:
        row = conn.execute("SELECT name, kind FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise _refused(copy.FILE_NOT_IN_PROJECT, "file_id", status=404)
    name, kind = row
    if kind != "xlsx":  # the file store's kind for .xlsx and .xlsm with a zip inside
        raise _refused(copy.FILL_XLS_NOT_SUPPORTED, "file_id")
    return name, files.read_original(rec, file_id)


def _text(value) -> str | None:
    """A client cell as text, numbers as written (never an exponent), a formula as `=…`."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        text = format(Decimal(repr(value)), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return str(value)


def _cells(data: bytes, sheet: str | None, start_row: int, stop_row: int | None):
    """(sheet names, sheet, rows): each row `(n, {letter: text})` from `start_row` up to
    `stop_row` (inclusive) or the end. openpyxl reads only; the bytes are never written by it."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False)
    except Exception:  # a damaged or locked file: openpyxl raises many kinds
        raise _refused(copy.FILE_UNREADABLE) from None
    try:
        names = wb.sheetnames
        name = names[0] if sheet is None else sheet
        if name not in names:
            raise _refused(copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet=name), "sheet")
        ws = wb[name]
        ws.reset_dimensions()  # a wrong <dimension> in the file would cut rows or columns
        rows = [
            (n, {get_column_letter(i): _text(c.value) for i, c in enumerate(cells, start=1)})
            for n, cells in enumerate(
                ws.iter_rows(min_row=start_row, max_row=stop_row), start=start_row
            )
        ]
        return names, name, rows
    finally:
        wb.close()


def read_sheet(
    rec: Records, file_id: str, *, sheet: str | None = None, start_row: int = 1, limit: int = 50
) -> dict:
    """One page of the client's sheet (the first sheet by default), for mapping:
    `{"sheets", "sheet", "rows": [{"row": 12, "cells": {"A": "03/02", "E": None}}], "next"}`.
    Empty rows are left out; `next` is the row to ask for next, or None at the end."""
    start_row, limit = max(1, int(start_row)), max(1, int(limit))
    _, data = _client_file(rec, file_id)
    names, name, rows = _cells(data, sheet, start_row, start_row + limit)
    return {
        "sheets": names,
        "sheet": name,
        "rows": [
            {"row": n, "cells": cells}
            for n, cells in rows[:limit]
            if any(v is not None for v in cells.values())
        ],
        "next": start_row + limit if len(rows) > limit else None,
    }


def _checked(plan, v: dict, data: bytes) -> dict:
    """The plan, checked against the Deliverable's view and the client's sheet, in one shape."""
    if not isinstance(plan, dict):
        raise _refused(copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet=""), "sheet")
    sheet = plan.get("sheet")
    if not isinstance(sheet, str):
        raise _refused(copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet=str(sheet)), "sheet")
    present = patch.sheet_rows(data, sheet)
    header_row = plan.get("header_row", 0)
    if type(header_row) is not int or header_row < 0:
        raise _refused(copy.fill(copy.FILL_ROW_MISSING, row=header_row), "header_row")

    ours = {c["key"] for c in v.get("columns", [])}
    given = plan.get("columns")
    if not isinstance(given, dict):
        raise _refused(copy.COLUMN_NOT_ALLOWED, "columns")
    columns = {}
    for key, letter in given.items():
        letter = letter.strip().upper() if isinstance(letter, str) else ""
        if key not in ours:
            raise _refused(copy.COLUMN_NOT_ALLOWED, f"columns.{key}")
        if patch.column_number(letter) is None:
            raise _refused(copy.FILL_COLUMN_LETTER, f"columns.{key}")
        columns[key] = letter
    write = plan.get("write")
    if not isinstance(write, list):
        raise _refused(copy.COLUMN_NOT_ALLOWED, "write")
    for i, key in enumerate(write):
        if key not in columns:  # a column of ours, mapped to a client column
            raise _refused(copy.COLUMN_NOT_ALLOWED, f"write[{i}]")

    item_rows = {r["id"] for r in v.get("rows", []) if r["kind"] == "item"}
    given_rows = plan.get("rows")
    if not isinstance(given_rows, list):
        raise _refused(copy.ROW_NOT_FOUND, "rows")
    rows, seen_rows, seen_parts = [], set(), set()
    for i, entry in enumerate(given_rows):
        row = entry.get("row") if isinstance(entry, dict) else None
        part = entry.get("part") if isinstance(entry, dict) else None
        if type(row) is not int or row < 1:
            raise _refused(copy.fill(copy.FILL_ROW_MISSING, row=row), f"rows[{i}].row")
        if row in seen_rows:
            raise _refused(copy.fill(copy.FILL_ROW_TWICE, row=row), f"rows[{i}].row")
        if part in seen_parts:
            raise _refused(copy.fill(copy.FILL_ROW_TWICE, row=row), f"rows[{i}].part")
        if part not in item_rows:
            raise _refused(copy.ROW_NOT_FOUND, f"rows[{i}].part")
        if row not in present:
            raise _refused(copy.fill(copy.FILL_ROW_MISSING, row=row), f"rows[{i}].row")
        seen_rows.add(row)
        seen_parts.add(part)
        rows.append({"row": row, "part": part})
    return {
        "sheet": sheet,
        "header_row": header_row,
        "columns": columns,
        "write": list(write),
        "rows": rows,
        "accept_mismatches": [],
    }


def save_plan(rec: Records, deliverable_id: str, file_id: str, plan: dict, *, actor: str) -> str:
    """Checks and keeps a Fill Plan; returns its id. Raises `RecordsError`:
    FILE_NOT_IN_PROJECT (404), FILL_XLS_NOT_SUPPORTED (not an xlsx or xlsm),
    FILL_SHEET_NOT_FOUND, FILL_COLUMN_LETTER (a column letter outside A–XFD),
    COLUMN_NOT_ALLOWED (not a column of ours, or a `write` key that is not mapped),
    FILL_ROW_TWICE (a row or a part given twice), ROW_NOT_FOUND (not an item row of this
    Deliverable) or FILL_ROW_MISSING (a row the client's sheet does not have)."""
    v = store.view(rec, deliverable_id)
    _, data = _client_file(rec, file_id)
    checked = _checked(plan, v, data)
    plan_id = uuid4().hex
    with rec.write(actor) as conn:
        at = rec.clock()
        row = {
            "id": plan_id,
            "deliverable_id": deliverable_id,
            "file_id": file_id,
            "plan": checked,
            "created_at": at,
            "created_by": actor,
        }
        conn.execute(
            "INSERT INTO fill_plans(id, deliverable_id, file_id, plan, created_at, created_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (plan_id, deliverable_id, file_id, json.dumps(checked, ensure_ascii=False), at, actor),
        )
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="create",
            table="fill_plans",
            row_id=plan_id,
            before=None,
            after=row,
        )
    return plan_id


def _plan(rec: Records, plan_id: str) -> tuple[str, str, dict]:
    with rec.read() as conn:
        row = conn.execute(
            "SELECT deliverable_id, file_id, plan FROM fill_plans WHERE id = ?", (plan_id,)
        ).fetchone()
    if row is None:
        raise _refused(copy.FILL_PLAN_NOT_FOUND, "plan", status=404)
    return row[0], row[1], json.loads(row[2])


def _code(text: str | None) -> str:
    """A code as compared: trimmed, Western digits (`٠٣/٠٢` is `03/02`), no kashida."""
    return arabic.clean(text or "")


def _run(rec: Records, plan_id: str) -> tuple[dict, patch.Patched, str, dict]:
    """(the preview, the patched file, the client's file name, the plan)."""
    deliverable_id, file_id, plan = _plan(rec, plan_id)
    with rec.read() as conn:
        (revision,) = conn.execute(
            "SELECT max(no) FROM revisions WHERE deliverable_id = ? AND signed_off = 1",
            (deliverable_id,),
        ).fetchone()
    if revision is None:
        raise _refused(copy.FILL_NEEDS_SIGNOFF, status=409)
    v = store.view(rec, deliverable_id, revision=revision)
    name, data = _client_file(rec, file_id)
    _, _, read = _cells(data, plan["sheet"], plan["header_row"] + 1, None)
    client = dict(read)
    columns = plan["columns"]
    code_at, text_at = columns.get("code"), columns.get("description")
    by_part = {r["id"]: r for r in v["rows"] if r["kind"] == "item"}

    writes, cells, mismatches, mapped = [], [], [], set()
    for entry in plan["rows"]:
        row, ours = entry["row"], by_part.get(entry["part"])
        if ours is None:  # the row was removed before this Revision
            continue
        mapped.add(row)
        theirs = client.get(row, {})
        code_theirs = theirs.get(code_at) if code_at else None
        if code_at and _code(code_theirs) != _code(ours.get("code")):
            mismatches.append(
                {
                    "row": row,
                    "code_ours": ours.get("code"),
                    "code_theirs": code_theirs,
                    "accepted": row in plan["accept_mismatches"],
                    "text": copy.fill(
                        copy.FILL_CODE_MISMATCH,
                        row=row,
                        theirs=code_theirs or "",
                        ours=ours.get("code") or "",
                    ),
                }
            )
        for key in plan["write"]:
            cell = ours["cells"].get(key, {})
            value = cell.get("value", cell.get("text"))
            if value is None:  # nothing of ours to write, such as a rate-only item's amount
                continue
            ref = f"{columns[key]}{row}"
            cells.append(Write(plan["sheet"], ref, Decimal(value) if "value" in cell else value))
            writes.append(
                {
                    "cell": ref,
                    "row": row,
                    "column": key,
                    "before": theirs.get(columns[key]),
                    "after": value,
                    "code_ours": ours.get("code"),
                    "code_theirs": code_theirs,
                    "client_text": theirs.get(text_at) if text_at else None,
                }
            )
    patched = patch.patch_xlsx(data, cells)
    skipped = {ref for ref, _ in patched.skipped}
    unmapped_rows = [
        n
        for n, values in read
        if n not in mapped
        and (values.get(code_at) if code_at else any(x is not None for x in values.values()))
    ]
    out = {
        "plan_id": plan_id,
        "deliverable_id": deliverable_id,
        "file_id": file_id,
        "revision": revision,
        "sheet": plan["sheet"],
        "writes": [w for w in writes if w["cell"] not in skipped],
        "skipped": [{"cell": ref, "reason": why} for ref, why in patched.skipped],
        "mismatches": mismatches,
        "unmapped_rows": unmapped_rows,
        "unmapped_items": [
            {"part": part, "code": r.get("code")}
            for part, r in by_part.items()
            if part not in {e["part"] for e in plan["rows"]}
        ],
        "accepted_mismatches": plan["accept_mismatches"],
    }
    return out, patched, name, plan


def preview(rec: Records, plan_id: str) -> dict:
    """What the fill would write, from the newest signed-off Revision: `{"writes": [{"cell",
    "before", "after", "code_ours", "code_theirs", "client_text", …}], "skipped", "mismatches",
    "unmapped_rows", "unmapped_items", …}`. Raises FILL_NEEDS_SIGNOFF without a signed-off
    Revision, and FILL_PLAN_NOT_FOUND (404) for an unknown plan."""
    return _run(rec, plan_id)[0]


def accept_mismatches(rec: Records, plan_id: str, rows: list[int], *, actor: str) -> dict:
    """The engineer says these rows are right despite their codes; returns the new preview."""
    deliverable_id, _, plan = _plan(rec, plan_id)
    if not isinstance(rows, list):
        raise _refused(copy.fill(copy.FILL_ROW_MISSING, row=rows), "rows")
    in_plan = {e["row"] for e in plan["rows"]}
    for i, row in enumerate(rows):
        if row not in in_plan:
            raise _refused(copy.fill(copy.FILL_ROW_MISSING, row=row), f"rows[{i}]")
    before = plan["accept_mismatches"]
    plan["accept_mismatches"] = sorted(set(before) | set(rows))
    with rec.write(actor) as conn:
        conn.execute(
            "UPDATE fill_plans SET plan = ? WHERE id = ?",
            (json.dumps(plan, ensure_ascii=False), plan_id),
        )
        audit.record(
            conn,
            at=rec.clock(),
            actor=actor,
            action="update",
            table="fill_plans",
            row_id=plan_id,
            before={"accept_mismatches": before},
            after={"accept_mismatches": plan["accept_mismatches"]},
        )
    return preview(rec, plan_id)


def fill(rec: Records, plan_id: str, *, actor: str) -> tuple[bytes, str, dict]:
    """(the filled file, its name, the report). Raises FILL_CODE_MISMATCH while a code mismatch
    is not accepted, and what `preview` raises. The file is returned, never written to a path."""
    out, patched, name, plan = _run(rec, plan_id)
    blocking = [m for m in out["mismatches"] if not m["accepted"]]
    if blocking:
        index = next(i for i, e in enumerate(plan["rows"]) if e["row"] == blocking[0]["row"])
        raise _refused(blocking[0]["text"], f"rows[{index}]", status=409)
    stem, _, ext = name.rpartition(".")
    ext = "xlsm" if ext.lower() == "xlsm" else "xlsx"
    report = {
        "revision": out["revision"],
        "written": patched.written,
        "skipped": out["skipped"],
        "accepted_mismatches": out["accepted_mismatches"],
        "unmapped_rows": out["unmapped_rows"],
        "unmapped_items": out["unmapped_items"],
    }
    with rec.write(actor) as conn:
        audit.record(
            conn,
            at=rec.clock(),
            actor=actor,
            action="fill",
            table="fill_plans",
            row_id=plan_id,
            before=None,
            after={"revision": out["revision"], "written": len(patched.written)},
        )
    return patched.data, f"{stem or name}{OUT_SUFFIX}.{ext}", report
