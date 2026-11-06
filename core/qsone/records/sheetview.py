"""A spreadsheet file as Excel shows it, for the Sheet viewer (read only): its sheets, hidden ones
too and marked so, and one sheet's rows and columns with each cell as Excel shows it (a number
in its own format: «#,##0.00» shows 1,900.00, General shows 1900). The shape of a Deliverable's
Sheet view, so the same viewer draws it; nothing here is a ledger number or can be edited.

A row is `r<row>` and a column its letters, so a source's cell (sheet, row, column) is found."""

import csv
import io
import re

from qsone import copy
from qsone.records import boq
from qsone.records.arabic import display_text
from qsone.records.files import read_original
from qsone.records.project import Records, RecordsError

MAX_ROWS = 20_000  # rows in one answer: a sheet longer than this shows its first rows
WRAP_AT = 40  # a column whose longest text is longer than this wraps, at WRAP_WIDTH
WRAP_WIDTH = 320
KINDS = (*boq.KINDS, "csv")
_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-z]")


def _shown(cell: boq.Cell) -> tuple[str, bool]:
    """The cell's text as Excel shows it, and whether it is a number."""
    value = cell.value
    if isinstance(value, int | float) and not isinstance(value, bool):
        text, _ = boq.exact(value, cell.fmt)
        if text is not None:
            if cell.fmt and "," in cell.fmt.split(";")[0]:
                whole, _, part = text.partition(".")
                sign = "-" if whole.startswith("-") else ""
                whole = f"{int(whole.lstrip('-')):,}"
                text = f"{sign}{whole}{'.' + part if part else ''}"
            return text, True
    return boq._text(value, cell.fmt).strip(), False


def _csv_sheet(data: bytes) -> boq.Sheet:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1256")
    sheet, line = boq.Sheet("", False), 1
    reader = csv.reader(io.StringIO(text))
    try:
        for row in reader:
            for c, value in enumerate(row, 1):
                if value.strip():
                    sheet.cells.setdefault(line, {})[c] = boq.Cell(display_text(value), None)
            line = reader.line_num + 1  # the text pieces' {"line"}: a source finds its row
    except csv.Error:
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None
    return sheet


def file_sheet(rec: Records, file_id: str, name: str | None) -> dict:
    """The file's sheet `name` (the first Excel shows when None) as a read-only Sheet view, with
    `sheets` ([{name, hidden}]) and `sheet`. FILE_NOT_FOUND 404; a file that is no spreadsheet,
    or one that cannot be opened, FILE_UNREADABLE 409 (the screen then shows its text)."""
    with rec.read() as conn:
        found = conn.execute("SELECT name, kind FROM files WHERE id = ?", (file_id,)).fetchone()
    if found is None:
        raise RecordsError(copy.FILE_NOT_FOUND, status=404, field="file")
    title, kind = found
    if kind not in KINDS:
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file")
    data = read_original(rec, file_id)
    if kind == "csv":
        sheets, sheet = [{"name": "", "hidden": False}], _csv_sheet(data)
    else:
        try:
            book = boq.Workbook(file_id, title, kind, data)
            reader = boq._xlsx if kind == "xlsx" else boq._xls
            listed, _ = reader(data, None)
            _, sheet = boq.read(book, name)
        except RecordsError:
            raise
        except Exception:  # noqa: BLE001 - openpyxl's and xlrd's own errors
            raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None
        sheets = [{"name": n, "hidden": hidden} for n, hidden in listed]

    last = max((c for row in sheet.cells.values() for c in row), default=0)
    rows: list[dict] = []
    texts, numbers = dict.fromkeys(range(1, last + 1), 0), dict.fromkeys(range(1, last + 1), 0)
    longest = dict.fromkeys(range(1, last + 1), 0)
    for r in sorted(sheet.cells)[:MAX_ROWS]:
        cells = {}
        for c, cell in sheet.cells[r].items():
            text, number = _shown(cell)
            if not text:
                continue
            cells[boq.letters(c)] = {"text": text}
            (numbers if number else texts)[c] += 1
            longest[c] = max(longest[c], len(text))
        if cells:
            rows.append(
                {"id": f"r{r}", "kind": "item", "item_id": f"r{r}", "item_version": 1,
                 "version": 1, "code": str(r), "cells": cells}
            )  # fmt: skip
    columns = [
        {"key": "code", "from": "code", "label": {"en": "#", "ar": "#"}, "kind": "text",
         "edit": False, "frozen": True, "wrap": False, "width": 48}
    ]  # fmt: skip
    for c in range(1, last + 1):
        if not texts[c] and not numbers[c]:
            continue
        wrap = longest[c] > WRAP_AT
        letter = boq.letters(c)
        columns.append(
            {"key": letter, "label": {"en": letter, "ar": letter},
             "kind": "number" if numbers[c] > texts[c] else "text", "edit": False,
             "frozen": False, "wrap": wrap, "width": WRAP_WIDTH if wrap else 120}
        )  # fmt: skip
    words = " ".join(cell["text"] for row in rows[:200] for cell in row["cells"].values())
    arabic = len(_ARABIC.findall(words)) > len(_LATIN.findall(words))
    return {
        "id": f"file-sheet-{file_id}-{sheet.name}",
        "kind": "sheet",
        "variant": "file_sheet",
        "title": title,
        "file_id": file_id,
        "sheet": sheet.name,
        "sheets": sheets,
        "language": "ar" if arabic else "en",
        "status": "draft",
        "code": None,
        "same_provider": False,
        "off_desk": False,
        "version": 1,
        "at": "",
        "revision": None,
        "sample": False,
        "sources": {},
        "pending": 0,
        "open_comments": 0,
        "records_moved": False,
        "columns": columns,
        "rows": rows,
        "total": None,
        "incomplete": {},
        "more": len(sheet.cells) > MAX_ROWS,
    }
