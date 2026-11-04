"""Text from dropped files: PDF, Excel, CSV and plain text, each in pieces with where it came from.
Everything is read from memory, never from a temporary file."""

import csv
import datetime as dt
import io
from dataclasses import dataclass
from typing import Literal

import openpyxl
import pypdfium2 as pdfium
import xlrd

from qsone.records.arabic import display_text

Status = Literal["read", "partly_read", "stored", "unreadable"]


@dataclass(frozen=True)
class Piece:
    locator: dict  # {"page": 3} | {"sheet": "BOQ", "row": 23} | {"line": 10}
    text: str


@dataclass(frozen=True)
class Extracted:
    kind: str  # pdf, xlsx, xls, csv, txt, other
    status: Status
    pages: int | None  # PDF pages or workbook sheets
    pieces: list[Piece]
    note: str | None  # name of a copy.py text, e.g. "FILE_SCANNED_PAGES"


_KINDS = {"pdf": "pdf", "xlsx": "xlsx", "xlsm": "xlsx", "xls": "xls", "csv": "csv", "txt": "txt"}
_MAGIC = {"pdf": b"%PDF-", "xlsx": b"PK\x03\x04", "xls": b"\xd0\xcf\x11\xe0"}


def extract(name: str, data: bytes) -> Extracted:
    kind = _KINDS.get(name.rsplit(".", 1)[1].lower()) if "." in name else None
    if kind is None or not data.startswith(_MAGIC.get(kind, b"")):
        return Extracted("other", "stored", None, [], "FILE_NOT_READ_YET")
    if kind == "pdf":
        return _pdf(data)
    if kind in ("xlsx", "xls"):
        try:
            sheets = _xlsx(data) if kind == "xlsx" else _xls(data)
        except Exception:  # the readers raise many kinds of error on a damaged or locked file
            return Extracted(kind, "unreadable", None, [], "FILE_UNREADABLE")
        pieces = [p for sheet, rows in sheets for p in _table(sheet, rows)]
        return Extracted(kind, "read", len(sheets), pieces, None)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1256")
    if kind == "csv":
        try:
            return Extracted(kind, "read", None, _csv(text), None)
        except csv.Error:
            return Extracted(kind, "unreadable", None, [], "FILE_UNREADABLE")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    pieces = [Piece({"line": n}, t) for n, t in enumerate(map(display_text, lines), 1) if t]
    return Extracted(kind, "read", None, pieces, None)


def chunk(pieces: list[Piece], max_chars: int = 800) -> list[Piece]:
    """Split pieces longer than `max_chars` at the last newline or space; parts keep the locator."""
    out = []
    for piece in pieces:
        text = piece.text
        while len(text) > max_chars:
            cut = max(text.rfind("\n", 0, max_chars + 1), text.rfind(" ", 0, max_chars + 1))
            if cut <= 0:
                part, text = text[:max_chars], text[max_chars:]
            else:
                part, text = text[:cut].rstrip(), text[cut + 1 :].lstrip()
            out.append(Piece(piece.locator, part))
        if text:
            out.append(Piece(piece.locator, text))
    return out


def _pdf(data: bytes) -> Extracted:
    pieces, pdf = [], None
    try:
        pdf = pdfium.PdfDocument(data)
        pages = len(pdf)
        for i in range(pages):
            page = pdf[i]
            textpage = page.get_textpage()
            text = display_text(textpage.get_text_range())
            textpage.close()
            page.close()
            if text:
                pieces.append(Piece({"page": i + 1}, text))
    except pdfium.PdfiumError:
        return Extracted("pdf", "unreadable", None, [], "FILE_UNREADABLE")
    finally:
        if pdf is not None:
            pdf.close()
    if len(pieces) == pages:
        return Extracted("pdf", "read", pages, pieces, None)
    status = "partly_read" if pieces else "unreadable"
    return Extracted("pdf", status, pages, pieces, "FILE_SCANNED_PAGES")


def _xlsx(data: bytes) -> list[tuple[str, list]]:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets:
            ws.reset_dimensions()  # a wrong <dimension> in the file would cut rows or columns
            sheets.append((ws.title, list(ws.iter_rows(values_only=True))))
        return sheets
    finally:
        wb.close()


def _xls(data: bytes) -> list[tuple[str, list]]:
    book = xlrd.open_workbook(file_contents=data)
    try:
        return [
            (
                sheet.name,
                [[_xls_value(c, book.datemode) for c in sheet.row(r)] for r in range(sheet.nrows)],
            )
            for sheet in book.sheets()
        ]
    finally:
        book.release_resources()


def _xls_value(cell: xlrd.sheet.Cell, datemode: int):
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return xlrd.error_text_from_code.get(cell.value)
    return cell.value if cell.ctype in (xlrd.XL_CELL_TEXT, xlrd.XL_CELL_NUMBER) else None


def _cell(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, str):
        return display_text(value)
    return "" if value is None else str(value)


def _table(sheet: str, rows: list) -> list[Piece]:
    """One piece per non-empty row, after the nearest heading above it: a row with a single text
    cell and no numbers."""
    pieces, heading = [], None
    for n, row in enumerate(rows, 1):
        values = [v for v in row if _cell(v)]
        cells = [_cell(v) for v in values]
        if not cells:
            continue
        pieces.append(
            Piece({"sheet": sheet, "row": n}, " | ".join([heading, *cells] if heading else cells))
        )
        if len(values) == 1 and isinstance(values[0], str) and any(ch.isalpha() for ch in cells[0]):
            heading = cells[0]
    return pieces


def _csv(text: str) -> list[Piece]:
    pieces, line = [], 1
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        cells = [t for t in map(display_text, row) if t]
        if cells:
            pieces.append(Piece({"line": line}, " | ".join(cells)))
        line = reader.line_num + 1
    return pieces
