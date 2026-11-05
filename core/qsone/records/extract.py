"""Text from dropped files: PDF, Excel, CSV, plain text, Word, DXF, IFC and saved web pages, each
in pieces with where it came from, and flags for text a person does not see. Images, old Word
files and DWG drawings are kept with a plain note. Everything is read from memory, never from a
temporary file."""

import csv
import datetime as dt
import io
import zipfile
from dataclasses import dataclass, field
from typing import Literal

import openpyxl
import pypdfium2 as pdfium
import xlrd

from qsone.records import hidden
from qsone.records.arabic import display_text
from qsone.records.hidden import Flag

Status = Literal["read", "partly_read", "stored", "unreadable"]


@dataclass(frozen=True)
class Piece:
    locator: dict  # {"page": 3} | {"sheet": "BOQ", "row": 23} | {"line": 10} | {"layer": "A"}…
    text: str


@dataclass(frozen=True)
class Extracted:
    kind: str  # pdf, xlsx, xls, csv, txt, web, docx, doc, dxf, dwg, ifc, png, jpg, webp, other
    status: Status
    pages: int | None  # PDF pages, workbook sheets, or 1 for an image
    pieces: list[Piece]
    note: str | None  # name of a copy.py text, e.g. "FILE_SCANNED_PAGES"
    flags: list[Flag] = field(default_factory=list)  # hidden text and orders to an AI


_KINDS = {
    "pdf": "pdf",
    "xlsx": "xlsx",
    "xlsm": "xlsx",
    "xls": "xls",
    "csv": "csv",
    "txt": "txt",
    "web": "web",
    "docx": "docx",
    "doc": "doc",
    "dxf": "dxf",
    "dwg": "dwg",
    "ifc": "ifc",
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpg",
    "webp": "webp",
}
_MAGIC = {
    "pdf": b"%PDF-",
    "xlsx": b"PK\x03\x04",
    "xls": b"\xd0\xcf\x11\xe0",
    "doc": b"\xd0\xcf\x11\xe0",
    "docx": b"PK\x03\x04",
    "dwg": b"AC",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpg": b"\xff\xd8\xff",
    "webp": b"RIFF",
}
# Kept but not read, each with the note that says what to do.
_STORED = {"doc": "FILE_OLD_WORD", "dwg": "FILE_DWG_NOT_YET"}
_IMAGES = {"png", "jpg", "webp"}


def _looks_right(kind: str, data: bytes) -> bool:
    """The content matches the name's kind, by its first bytes (and, for Word, its parts)."""
    if not data.startswith(_MAGIC.get(kind, b"")):
        return False
    if kind == "webp":
        return data[8:12] == b"WEBP"
    if kind == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return "word/document.xml" in z.namelist()
        except zipfile.BadZipFile:
            return False
    if kind == "dxf":
        from qsone.records.readers import dxf

        return dxf.is_ascii(data) or dxf.is_binary(data)
    if kind == "ifc":
        from qsone.records.readers import ifc

        return ifc.is_ifc(data)
    return True


_CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # an OLE2 compound file
_ENCRYPTED = "EncryptedPackage".encode("utf-16-le")  # its stream holding a locked Office file


def _locked(kind: str, data: bytes) -> bool:
    """An .xlsx or .docx locked with a password: Office keeps it as an OLE2 file with an
    EncryptedPackage stream instead of the zip an open one is."""
    return kind in ("xlsx", "docx") and data.startswith(_CFB) and _ENCRYPTED in data[: 1 << 20]


def extract(name: str, data: bytes) -> Extracted:
    kind = _KINDS.get(name.rsplit(".", 1)[1].lower()) if "." in name else None
    if kind is not None and _locked(kind, data):
        return Extracted(kind, "unreadable", None, [], "FILE_LOCKED")
    if kind is None or not _looks_right(kind, data):
        return Extracted("other", "stored", None, [], "FILE_NOT_READ_YET")
    if kind in _STORED:
        return Extracted(kind, "stored", None, [], _STORED[kind])
    if kind in _IMAGES:
        return Extracted(kind, "stored", 1, [], "FILE_IMAGE_STORED")
    if kind == "pdf":
        x = _pdf(data)
    elif kind in ("xlsx", "xls", "docx", "dxf", "ifc"):
        x = _reader(kind, data)
    else:
        x = _text(kind, data)
    ai = hidden.ai_instruction_flags(x.pieces)
    return Extracted(x.kind, x.status, x.pages, x.pieces, x.note, x.flags + ai) if ai else x


def _reader(kind: str, data: bytes) -> Extracted:
    # imported here: the readers import Piece from this module
    from qsone.records.readers import docx, dxf, ifc

    if kind == "dxf" and dxf.is_binary(data):
        return Extracted(kind, "stored", None, [], "FILE_DWG_NOT_YET")
    try:
        if kind in ("xlsx", "xls"):
            sheets, flags = _xlsx(data) if kind == "xlsx" else _xls(data)
            pieces = [p for sheet, rows in sheets for p in _table(sheet, rows)]
            empty = None if pieces else "FILE_SHEETS_EMPTY"
            return Extracted(kind, "read", len(sheets), pieces, empty, flags)
        if kind == "docx":
            pieces, flags, vanished = docx.read(data)
            # vanished text is not in the pieces, but is still checked for orders to an AI
            flags += hidden.ai_instruction_flags(vanished)
            return Extracted(kind, "read", None, pieces, None, flags)
        return Extracted(kind, "read", None, (dxf if kind == "dxf" else ifc).read(data), None)
    except Exception as e:  # the readers raise many kinds of error on a damaged or locked file
        locked = "encrypt" in str(e).lower()  # xlrd: "Workbook is encrypted"
        return Extracted(
            kind, "unreadable", None, [], "FILE_LOCKED" if locked else "FILE_UNREADABLE"
        )


def _text(kind: str, data: bytes) -> Extracted:
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
    pieces, flags, pdf = [], [], None
    try:
        pdf = pdfium.PdfDocument(data)
        pages = len(pdf)
        for i in range(pages):
            page = pdf[i]
            textpage = page.get_textpage()
            text = display_text(textpage.get_text_range())
            flags += hidden.pdf_page_flags(page, textpage, i + 1)
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
        return Extracted("pdf", "read", pages, pieces, None, flags)
    status = "partly_read" if pieces else "unreadable"
    return Extracted("pdf", status, pages, pieces, "FILE_SCANNED_PAGES", flags)


def _xlsx(data: bytes) -> tuple[list[tuple[str, list]], list[Flag]]:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheets = []
        for ws in wb.worksheets:
            ws.reset_dimensions()  # a wrong <dimension> in the file would cut rows or columns
            sheets.append((ws.title, list(ws.iter_rows(values_only=True))))
    finally:
        wb.close()
    return sheets, hidden.xlsx_flags(data)


def _xls(data: bytes) -> tuple[list[tuple[str, list]], list[Flag]]:
    # formatting_info gives hidden rows and columns and the cell fonts, for the flags
    book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    try:
        sheets = [
            (
                sheet.name,
                [[_xls_value(c, book.datemode) for c in sheet.row(r)] for r in range(sheet.nrows)],
            )
            for sheet in book.sheets()
        ]
        flags = hidden.xls_flags(
            book, lambda sheet, r, c: _cell(_xls_value(sheet.cell(r, c), book.datemode))
        )
        return sheets, flags
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


HEADING_CHARS = 80


def _table(sheet: str, rows: list) -> list[Piece]:
    """One piece per non-empty row, after the nearest heading above it: a row with a single short
    text cell (one line, at most 80 characters) and no numbers. A long note, often a merged cell
    across the sheet, is read once in its own row: carried as a heading it would repeat in every
    row below. A heading is not added to a row that already holds it."""
    pieces, heading = [], None
    for n, row in enumerate(rows, 1):
        values = [v for v in row if _cell(v)]
        cells = [_cell(v) for v in values]
        if not cells:
            continue
        carried = [heading, *cells] if heading and heading not in cells else cells
        pieces.append(Piece({"sheet": sheet, "row": n}, " | ".join(carried)))
        text = cells[0]
        if (
            len(values) == 1
            and isinstance(values[0], str)
            and any(ch.isalpha() for ch in text)
            and len(text) <= HEADING_CHARS
            and "\n" not in text
        ):
            heading = text
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
