"""A client BOQ from Excel into the Source Ledger (Plan 5, Task 9). The AI maps the columns; code
reads every row.

- `preview` shows a sheet's first rows with their row numbers, a guessed header row and the
  columns its headings name.
- `plan` reads every row below the header (nothing is written) and sorts it: a `boq_item`
  (a description with a quantity, or with a unit), a `boq_heading` (a description only), or a row
  left out with the reason: a total, the headings again, a number that is not exact, a quantity
  with no unit, a row hidden in Excel. An empty row is passed over.
- `write` stores the plan in one transaction: the items, then each number with its own source,
  the cell it came from (`{"sheet", "row", "column"}`), and one audit row whose id is the
  `import_id`. Rates and amounts are copied as written, never computed.

Cells become exact decimal text: the shortest text of the stored double (`repr`), with the
zeros the cell's number format shows (39850.5 shown as 39850.50 stays "39850.50"). A value with
more than 6 decimals (0.1 + 0.2 stored as 0.30000000000000004), text in a number column, or a
date is never guessed: the row is left out and said. Units are kept as written.

Merged cells read as Excel shows them: a text spanning the description column is the row's
description; a description, code or unit merged down a column is each row's. A number is read
only from its own cell. Hidden rows are left out unless asked, and always named; rows with
hidden text or orders to an AI (the file's flags) are imported as data and named."""

import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import openpyxl
import xlrd

from qsone import copy
from qsone.records import audit, ledger
from qsone.records.arabic import display_text, normalise
from qsone.records.files import read_original
from qsone.records.hidden import _xlsx_sheets
from qsone.records.project import Records, RecordsError

FIELDS = ("code", "description", "unit", "quantity", "rate", "amount")
REQUIRED = ("description", "unit", "quantity")
NUMBERS = ("quantity", "rate", "amount")
MAX_DECIMALS = 6
PREVIEW_ROWS = 30
KINDS = ("xlsx", "xls")
ITEM, HEADING = "boq_item", "boq_heading"

Hidden = Literal["skip", "include"]


# Exact cells ------------------------------------------------------------------------------------

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_PLAIN = re.compile(r"[+-]?[0-9]+(\.[0-9]+)?")
_FORMAT_NOISE = re.compile(r'"[^"]*"|\[[^\]]*\]|\\.|_.|\*.')


def _shown_decimals(fmt: str | None) -> int:
    """How many decimals a number format shows: `#,##0.00` 2; General, percent and scientific
    formats 0 (a percent is stored as 0.15 and shown as 15%: the stored value is kept)."""
    if not fmt:
        return 0
    section = _FORMAT_NOISE.sub("", fmt.split(";")[0])
    if "%" in section or re.search(r"[Ee][+-]", section):
        return 0
    found = re.search(r"\.([0#?]+)", section)
    return found[1].count("0") if found else 0


def _within(text: str) -> tuple[str | None, str | None]:
    if Decimal(text).normalize().as_tuple().exponent < -MAX_DECIMALS:
        return None, "decimals"
    return text, None


def exact(value, fmt: str | None) -> tuple[str | None, str | None]:
    """(exact decimal text, None), or (None, why): "text" for text, a date or a flag, "decimals"
    for more than 6 decimals. (None, None) is an empty cell. Never a float."""
    if value is None:
        return None, None
    if isinstance(value, str):
        text = value.translate(_DIGITS).strip()
        if not text:
            return None, None
        return _within(text) if _PLAIN.fullmatch(text) else (None, "text")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, "text"
    if isinstance(value, float):
        if not math.isfinite(value):
            return None, "text"
        # repr is the shortest text that reads back as the same double: what Excel stored
        text = str(int(value)) if value.is_integer() else format(Decimal(repr(value)), "f")
    else:
        text = str(value)
    text, why = _within(text)
    if text is None:
        return None, why
    have = len(text.split(".")[1]) if "." in text else 0
    wanted = _shown_decimals(fmt)
    if wanted > have:
        text += ("" if have else ".") + "0" * (wanted - have)
    return text, None


def _text(value, fmt: str | None = None) -> str:
    """A text cell as shown: a number as exact text, a date as its day."""
    if value is None:
        return ""
    if isinstance(value, str):
        return display_text(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    shown, _ = exact(value, fmt)
    return shown if shown is not None else str(value)


# Reading a sheet --------------------------------------------------------------------------------


def letters(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def column(letters_: str) -> int:
    n = 0
    for ch in letters_:
        n = n * 26 + ord(ch) - 64
    return n


@dataclass(frozen=True)
class Cell:
    value: object
    fmt: str | None


@dataclass
class Sheet:
    """One sheet as Excel shows it: cells by row and column (from 1), hidden rows and columns,
    merged ranges (top row, left column, bottom row, right column)."""

    name: str
    hidden: bool
    cells: dict[int, dict[int, Cell]] = field(default_factory=dict)
    hidden_rows: set[int] = field(default_factory=set)
    hidden_columns: set[int] = field(default_factory=set)
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)

    @property
    def last_row(self) -> int:
        return max(self.cells, default=0)


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RANGE = re.compile(r"([A-Z]+)(\d+):([A-Z]+)(\d+)")


def _xlsx_layout(data: bytes, sheet: Sheet) -> None:
    """Hidden rows and columns and merged ranges, from the sheet's XML (openpyxl's read-only
    mode has neither), parsed as it streams."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        path = next(p for name, _, p in _xlsx_sheets(z) if name == sheet.name)
        with z.open(path) as f:
            for _, el in ET.iterparse(f):
                if el.tag == f"{_NS}row":
                    if el.get("hidden") in ("1", "true"):
                        sheet.hidden_rows.add(int(el.get("r", "0")))
                    el.clear()
                elif el.tag == f"{_NS}col" and el.get("hidden") in ("1", "true"):
                    lo, hi = int(el.get("min", "0")), int(el.get("max", "0"))
                    sheet.hidden_columns.update(range(lo, min(hi, 16384) + 1))
                elif el.tag == f"{_NS}mergeCell":
                    m = _RANGE.fullmatch(el.get("ref", ""))
                    if m:
                        top, bottom = sorted((int(m[2]), int(m[4])))
                        left, right = sorted((column(m[1]), column(m[3])))
                        sheet.merges.append((top, left, bottom, right))


def _xlsx(data: bytes, name: str | None) -> tuple[list, Sheet | None]:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        names = [(ws.title, ws.sheet_state != "visible") for ws in wb.worksheets]
        if name is None:
            return names, None
        ws = wb[name]
        ws.reset_dimensions()  # a wrong <dimension> in the file would cut rows or columns
        sheet = Sheet(name, ws.sheet_state != "visible")
        for r, row in enumerate(ws.iter_rows(), 1):
            for c in row:
                if c.value is not None:
                    sheet.cells.setdefault(r, {})[c.column] = Cell(c.value, c.number_format)
    finally:
        wb.close()
    _xlsx_layout(data, sheet)
    return names, sheet


def _xls_value(cell, datemode: int):
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value, "#ERROR")
    if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER):
        return cell.value
    return None


def _xls(data: bytes, name: str | None) -> tuple[list, Sheet | None]:
    book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    try:
        names = [(ws.name, ws.visibility != 0) for ws in book.sheets()]
        if name is None:
            return names, None
        ws = book.sheet_by_name(name)
        sheet = Sheet(name, ws.visibility != 0)
        for r in range(ws.nrows):
            for c in range(ws.row_len(r)):
                value = _xls_value(ws.cell(r, c), book.datemode)
                if value is None or value == "":
                    continue
                fmt = book.format_map.get(book.xf_list[ws.cell_xf_index(r, c)].format_key)
                sheet.cells.setdefault(r + 1, {})[c + 1] = Cell(value, fmt and fmt.format_str)
        sheet.hidden_rows = {r + 1 for r, info in ws.rowinfo_map.items() if info.hidden}
        sheet.hidden_columns = {c + 1 for c, info in ws.colinfo_map.items() if info.hidden}
        sheet.merges = [(rlo + 1, clo + 1, rhi, chi) for rlo, rhi, clo, chi in ws.merged_cells]
        return names, sheet
    finally:
        book.release_resources()


@dataclass(frozen=True)
class Workbook:
    file_id: str
    name: str
    kind: str
    data: bytes


def workbook(rec: Records, file_id: str) -> Workbook:
    """The file, if it is an Excel workbook. Raises `RecordsError`: FILE_NOT_IN_PROJECT,
    BOQ_NOT_EXCEL (field file_id)."""
    with rec.read() as conn:
        row = conn.execute("SELECT name, kind FROM files WHERE id = ?", (file_id,)).fetchone()
    if row is None:
        raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=422, field="file_id")
    if row[1] not in KINDS:
        raise RecordsError(copy.BOQ_NOT_EXCEL, status=422, field="file_id")
    return Workbook(file_id, row[0], row[1], read_original(rec, file_id))


def read(book: Workbook, sheet: str | None) -> tuple[list[str], Sheet]:
    """The sheet names and one sheet: `sheet`, or the first one Excel shows. Raises
    `RecordsError` BOQ_NO_SHEET (field sheet) with the sheet names."""
    reader = _xlsx if book.kind == "xlsx" else _xls
    listed, _ = reader(book.data, None)
    names = [n for n, _ in listed]
    if sheet is None:
        sheet = next((n for n, hidden in listed if not hidden), names[0] if names else None)
    if sheet not in names:
        text = copy.fill(copy.BOQ_NO_SHEET, sheets=", ".join(names))
        raise RecordsError(text, status=422, field="sheet")
    return names, reader(book.data, sheet)[1]


# What the headings say --------------------------------------------------------------------------

_HEADER_WORDS = {
    "code": ("البند", "رقم البند", "م", "مسلسل", "كود", "الكود", "item", "item no", "no", "ref",
             "code", "s n", "serial", "sr"),
    "description": ("الوصف", "وصف", "البيان", "بيان", "بيان الأعمال", "وصف البند", "وصف الأعمال",
                    "description", "item description", "particulars", "desc"),
    "unit": ("الوحدة", "وحدة", "وحدة القياس", "unit", "uom", "u m"),
    "quantity": ("الكمية", "كمية", "الكميات", "qty", "quantity", "quantities", "qnty"),
    "rate": ("الفئة", "فئة", "الفئه", "سعر الوحدة", "السعر", "rate", "unit rate", "unit price",
             "price"),
    "amount": ("الإجمالي", "إجمالي", "اجمالي", "القيمة", "الجملة", "المبلغ", "amount", "total",
               "total price", "total amount", "value"),
}  # fmt: skip
_KEYWORDS = sorted(
    ((normalise(w), f) for f, words in _HEADER_WORDS.items() for w in words),
    key=lambda kw: -len(kw[0]),
)


def heading_field(text: str) -> str | None:
    """The BOQ field a column heading names, by its longest matching word ("سعر الوحدة" is the
    rate, not the unit); a word of one or two letters ("م", "no") must be the whole heading."""
    t = normalise(text)
    if not t:
        return None
    for word, name in _KEYWORDS:
        if t == word or (len(word) >= 3 and f" {word} " in f" {t} "):
            return name
    return None


def _named(row: dict[int, Cell]) -> dict[str, str]:
    """field -> column letter, for the first column whose heading names each field."""
    found: dict[str, str] = {}
    for col in sorted(row):
        name = heading_field(_text(row[col].value)) if isinstance(row[col].value, str) else None
        if name and name not in found:
            found[name] = letters(col)
    return found


def _header_guess(sheet: Sheet, upto: int) -> int | None:
    for r in sorted(sheet.cells):
        if r > upto:
            break
        named = _named(sheet.cells[r])
        if len(named) >= 3 and ("description" in named or "quantity" in named):
            return r
    return None


def preview(rec: Records, file_id: str, sheet: str | None, *, rows: int = PREVIEW_ROWS) -> dict:
    """{"name", "sheets", "sheet", "sheet_hidden", "rows": [{"row": n, "cells": {"A": "…"}}],
    "header_guess": n | None, "columns_guess": {field: letter}, "hidden_rows", "merged_rows",
    "last_row"}: the first `rows` rows of the sheet with content, as text."""
    book = workbook(rec, file_id)
    names, ws = read(book, sheet)
    shown = sorted(ws.cells)[:rows]
    guess = _header_guess(ws, shown[-1] if shown else 0)
    merged = sorted({r for top, _, bottom, _ in ws.merges for r in range(top, bottom + 1)})
    return {
        "name": book.name,
        "sheets": names,
        "sheet": ws.name,
        "sheet_hidden": ws.hidden,
        "rows": [
            {
                "row": r,
                "cells": {
                    letters(c): t
                    for c, cell in sorted(ws.cells[r].items())
                    if (t := _text(cell.value, cell.fmt))
                },
            }
            for r in shown
        ],
        "header_guess": guess,
        "columns_guess": {} if guess is None else _named(ws.cells[guess]),
        "hidden_rows": [r for r in shown if r in ws.hidden_rows],
        "merged_rows": [r for r in shown if r in set(merged)],
        "last_row": ws.last_row,
    }


# Sorting the rows -------------------------------------------------------------------------------

_TOTAL = re.compile(
    r"(?<!\w)(?:ال)?[إاأ]جمال[يى](?!\w)|(?<!\w)(?:ال)?مجموع(?!\w)|(?<!\w)(?:ال)?جمل[ةه](?!\w)"
    r"|(?<!\w)(?:ال)?مرحل(?!\w)|ما قبله|(?<!\w)المنقول(?!\w)"
    r"|(?<!\w)sub-?totals?(?!\w)|(?<!\w)totals?(?!\w)|carried (?:forward|over|to)"
    r"|brought forward|to collection|to summary",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Row:
    row: int
    kind: str  # ITEM or HEADING
    code: str | None
    description: str
    unit: str | None
    numbers: dict[str, tuple[str, str]]  # field -> (exact text, column letter)
    hidden: bool


@dataclass(frozen=True)
class Plan:
    file_id: str
    file_name: str
    sheet: str
    header_row: int
    columns: dict[str, str]
    hidden_policy: Hidden
    rows: list[Row]
    skipped: list[dict]  # [{"row", "why": {en, ar}}]
    first_row: int
    last_row: int
    headers: dict[str, str]  # field -> the heading in the file
    examples: dict[str, list[str]]  # field -> its first values
    hidden_rows: list[int]  # hidden rows with content, imported or not
    flagged_rows: list[int]  # imported rows with hidden text or orders to an AI
    no_quantity: list[int]  # items with a unit and no quantity yet
    already: int  # rows of this file version and sheet imported before
    sheet_hidden: bool
    hidden_columns: list[str]  # mapped columns hidden in Excel

    @property
    def items(self) -> int:
        return sum(r.kind == ITEM for r in self.rows)

    @property
    def headings(self) -> int:
        return sum(r.kind == HEADING for r in self.rows)

    @property
    def numbers(self) -> int:
        return sum(len(r.numbers) for r in self.rows)


def _origins(sheet: Sheet, columns: dict[str, int]) -> dict[tuple[int, str], tuple | None]:
    """(row, field) -> the merged range's top-left cell, for each text field (code,
    description, unit) inside a merged range but not its top-left. A range that spans the
    description column gives its text to the description alone: the other fields it spans are
    blank (None), its top-left too."""
    out: dict[tuple[int, str], tuple | None] = {}
    texts = {f: c for f, c in columns.items() if f not in NUMBERS}
    for top, left, bottom, right in sheet.merges:
        inside = [f for f, c in texts.items() if left <= c <= right]
        for r in range(top, bottom + 1):
            for f in inside:
                if "description" in inside and f != "description":
                    out[(r, f)] = None
                elif (r, texts[f]) != (top, left):
                    out[(r, f)] = (top, left)
    return out


def _flagged(rec: Records, file_id: str, sheet: str) -> set[int]:
    """Rows of the sheet with hidden text (white, tiny, invisible) or orders to an AI."""
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT kind, locator FROM file_flags WHERE file_id = ? AND kind IN"
            " ('white_text', 'tiny_text', 'invisible_text', 'ai_instruction')",
            (file_id,),
        ).fetchall()
    found: set[int] = set()
    for _, text in rows:
        loc = json.loads(text)
        if loc.get("sheet") != sheet:
            continue
        if isinstance(loc.get("row"), int):
            found.add(loc["row"])
        for ref in loc.get("cells") or ():
            m = re.fullmatch(r"[A-Z]+(\d+)", ref)
            if m:
                found.add(int(m[1]))
    return found


def _imported_rows(rec: Records, file_id: str, sheet: str) -> set[int]:
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT json_extract(fields, '$.row') FROM items WHERE kind IN (?, ?)"
            " AND json_extract(fields, '$.file_id') = ? AND json_extract(fields, '$.sheet') = ?",
            (ITEM, HEADING, file_id, sheet),
        ).fetchall()
    return {r for (r,) in rows}


def plan(
    rec: Records,
    file_id: str,
    *,
    sheet: str,
    header_row: int,
    columns: dict[str, str],
    rows: tuple[int, int] | None = None,
    hidden: Hidden = "skip",
) -> Plan:
    """Every row below `header_row` (or within `rows`), sorted; nothing is written. Rows of this
    file version and sheet imported before are passed over (counted in `already`). Raises
    `RecordsError`: FILE_NOT_IN_PROJECT, BOQ_NOT_EXCEL, BOQ_NO_SHEET, BOQ_NO_ROWS."""
    book = workbook(rec, file_id)
    _, ws = read(book, sheet)
    cols = {f: column(columns[f]) for f in FIELDS if f in columns}
    first = max(header_row + 1, rows[0] if rows else 1)
    last = min(ws.last_row, rows[1] if rows else ws.last_row)
    origins = _origins(ws, cols)
    header = ws.cells.get(header_row, {})
    headers = {f: _text(header[c].value) if c in header else "" for f, c in cols.items()}
    flagged, before = _flagged(rec, file_id, sheet), _imported_rows(rec, file_id, sheet)

    def raw(r: int, f: str):
        if f not in cols:
            return None, None
        at = origins.get((r, f), (r, cols[f]))
        cell = None if at is None else ws.cells.get(at[0], {}).get(at[1])
        return (None, None) if cell is None else (cell.value, cell.fmt)

    def skip(r: int, why: dict) -> None:
        skipped.append({"row": r, "why": why})

    out: list[Row] = []
    skipped: list[dict] = []
    hidden_rows, no_quantity, already = [], [], 0
    for r in range(first, last + 1):
        texts = {f: _text(*raw(r, f)) for f in ("code", "description", "unit")}
        values = {f: raw(r, f) for f in NUMBERS}
        if not any(texts.values()) and all(_text(v) == "" for v, _ in values.values()):
            continue  # an empty row
        if r in before:
            already += 1
            continue
        is_hidden = r in ws.hidden_rows
        if is_hidden:
            hidden_rows.append(r)
            if hidden == "skip":
                skip(r, copy.BOQ_WHY_HIDDEN)
                continue
        shown = {f: _text(*values[f]) for f in NUMBERS} | texts
        again = [f for f, c in cols.items() if headers[f] and shown[f] == headers[f]]
        if len(again) >= 2:
            skip(r, copy.BOQ_WHY_HEADER)
            continue
        quantity_empty = _text(values["quantity"][0]) == ""
        if quantity_empty and (_TOTAL.search(texts["description"]) or _TOTAL.search(texts["code"])):
            skip(r, copy.BOQ_WHY_TOTAL)
            continue
        numbers, bad = {}, None
        for f in NUMBERS:
            text, why = exact(*values[f])
            if why is not None:
                bad = (f, why)
                break
            if text is not None:
                numbers[f] = (text, letters(cols[f]))
        if bad is not None:
            f, why = bad
            words = copy.BOQ_WHY_TEXT if why == "text" else copy.BOQ_WHY_DECIMALS
            skip(r, copy.fill(words, field=copy.BOQ_FIELDS[f], column=letters(cols[f])))
            continue
        code, description, unit = (texts[f] or None for f in ("code", "description", "unit"))
        if "quantity" in numbers and unit is None:
            skip(r, copy.BOQ_WHY_NO_UNIT)
            continue
        if numbers and description is None:
            skip(r, copy.BOQ_WHY_NO_DESCRIPTION)
            continue
        if description is None:
            continue  # a code alone: no description and no number is not a BOQ row
        if unit is None and numbers:
            skip(r, copy.BOQ_WHY_NUMBER_ONLY)
            continue
        kind = ITEM if unit is not None else HEADING
        if kind == ITEM and "quantity" not in numbers:
            no_quantity.append(r)
        out.append(Row(r, kind, code, description, unit, numbers, is_hidden))

    if not out and not already:
        raise RecordsError(copy.BOQ_NO_ROWS, status=422, field="header_row")
    examples: dict[str, list[str]] = {f: [] for f in cols}
    for row in out:
        if row.kind != ITEM:
            continue
        values = {"code": row.code, "description": row.description, "unit": row.unit}
        values |= {f: t for f, (t, _) in row.numbers.items()}
        for f in cols:
            if values.get(f) and len(examples[f]) < 3:
                examples[f].append(values[f])
    return Plan(
        file_id=file_id,
        file_name=book.name,
        sheet=ws.name,
        header_row=header_row,
        columns={f: columns[f] for f in cols},
        hidden_policy=hidden,
        rows=out,
        skipped=skipped,
        first_row=first,
        last_row=last,
        headers=headers,
        examples=examples,
        hidden_rows=hidden_rows,
        flagged_rows=sorted(r.row for r in out if r.row in flagged),
        no_quantity=no_quantity,
        already=already,
        sheet_hidden=ws.hidden,
        hidden_columns=[letters(c) for f, c in cols.items() if c in ws.hidden_columns],
    )


# Writing ----------------------------------------------------------------------------------------

Source = Callable[[dict], dict]  # {"sheet", "row", "column"} -> a source row (ledger.write_source)


def import_key(
    file_id: str,
    *,
    sheet: str,
    header_row: int,
    columns: dict[str, str],
    rows: tuple[int, int] | None,
    hidden: Hidden,
    currency: str | None,
    dated: str | None,
) -> str:
    """The same file version, sheet, columns and choices: the same import."""
    asked = {
        "file_id": file_id,
        "sheet": sheet,
        "header_row": header_row,
        "columns": dict(sorted(columns.items())),
        "rows": list(rows) if rows else None,
        "hidden": hidden,
        "currency": currency if {"rate", "amount"} & set(columns) else None,
        "dated": dated,
    }
    return hashlib.sha256(json.dumps(asked, sort_keys=True).encode()).hexdigest()


def earlier(rec: Records, key: str) -> dict | None:
    """The summary of an import made before with this key, or None."""
    with rec.read() as conn:
        row = conn.execute(
            "SELECT row_id, after FROM audit WHERE action = 'import' AND table_name = 'boq_imports'"
            " AND json_extract(after, '$.key') = ? ORDER BY id LIMIT 1",
            (key,),
        ).fetchone()
    if row is None:
        return None
    summary = json.loads(row[1])
    summary.pop("key", None)
    return summary | {"import_id": row[0]}


def write(
    rec: Records, p: Plan, *, actor: str, source: Source, currency: str | None, key: str
) -> dict:
    """The plan in one transaction: items and headings, each number with the source `source`
    gives for its cell, and the audit row. Returns the summary, with `import_id`; an import
    made before with `key` is returned as it was, with `already_imported`, and adds nothing."""
    with rec.write(actor) as conn:
        found = earlier(rec, key)
        if found is not None:
            return found | {"already_imported": True}
        import_id, at = uuid4().hex, rec.clock()
        for order, row in enumerate(p.rows, 1):
            fields: dict = {"description": row.description}
            if row.unit is not None:
                fields["unit"] = row.unit
            fields |= {"order": order, "file_id": p.file_id, "sheet": p.sheet, "row": row.row}
            fields["import_id"] = import_id
            item_id = ledger.write_item(
                conn, at=at, actor=actor, kind=row.kind, code=row.code, fields=fields
            )
            for name, (text, col) in row.numbers.items():
                src = source({"sheet": p.sheet, "row": row.row, "column": col})
                source_id = ledger.write_source(conn, at=at, actor=actor, **src)
                ledger.write_number(
                    conn,
                    at=at,
                    actor=actor,
                    item_id=item_id,
                    name=name,
                    value=text,
                    source_id=source_id,
                    dated=src["dated"],
                    unit=None if name == "amount" else row.unit,
                    currency=None if name == "quantity" else currency,
                )
        summary = {
            "file_id": p.file_id,
            "sheet": p.sheet,
            "header_row": p.header_row,
            "columns": p.columns,
            "items": p.items,
            "headings": p.headings,
            "numbers": p.numbers,
            "first_row": p.first_row,
            "last_row": p.last_row,
            "skipped": p.skipped,
            "hidden_rows": (
                {}
                if not p.hidden_rows
                else {"included" if p.hidden_policy == "include" else "skipped": p.hidden_rows}
            ),
            "flagged_rows": p.flagged_rows,
            "no_quantity": p.no_quantity,
            "already_imported_rows": p.already,
        }
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="import",
            table="boq_imports",
            row_id=import_id,
            before=None,
            after=summary | {"key": key},
        )
    return summary | {"import_id": import_id}


def import_sheet(
    rec: Records,
    file_id: str,
    *,
    sheet: str,
    header_row: int,
    columns: dict[str, str],
    rows: tuple[int, int] | None,
    actor: str,
    source: Source,
    currency: str | None = None,
    hidden: Hidden = "skip",
    dated: str | None = None,
) -> dict:
    """`plan`, then `write`. `source` builds each number's source from its cell (the tools give
    the evidence check, `tools_records.evidence`); `dated` is only part of the import's key."""
    p = plan(rec, file_id, sheet=sheet, header_row=header_row, columns=columns, rows=rows,
             hidden=hidden)  # fmt: skip
    key = import_key(file_id, sheet=sheet, header_row=header_row, columns=columns, rows=rows,
                     hidden=hidden, currency=currency, dated=dated)  # fmt: skip
    return write(rec, p, actor=actor, source=source, currency=currency, key=key)
