"""Text from dropped files: PDF, Excel, CSV, plain text, Word, DXF, IFC and saved web pages, each
in pieces with where it came from, and flags for text a person does not see. Drawing bytes
are read by the local subprocess; images are queued for local background OCR. Readers use
memory except optional LibreOffice conversion of older Office/OpenDocument files in a
disposable folder."""

import csv
import ctypes
import datetime as dt
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from typing import Literal

import openpyxl
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import xlrd

from qsone.records import hidden, office
from qsone.records.arabic import display_number, display_text
from qsone.records.hidden import Flag
from qsone.records.pdfium_guard import pdfium_locked

EXTRACTOR_VERSION = 2

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
    page_sources: dict[int, str] = field(default_factory=dict)


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
    **{kind: kind for kind in office.READ_TARGETS},
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
_STORED = {}
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
    native = _reader("xls", data) if kind == "xls" else None
    if native is not None and native.status == "read":
        ai = hidden.ai_instruction_flags(native.pieces)
        return (
            Extracted(
                native.kind,
                native.status,
                native.pages,
                native.pieces,
                native.note,
                native.flags + ai,
            )
            if ai
            else native
        )
    if kind in office.READ_TARGETS:
        if office.find_soffice() is None:
            return Extracted(kind, "stored", None, [], "FILE_LIBREOFFICE_MISSING")
        target = office.READ_TARGETS[kind]
        converted = office.convert(data, name, target)
        if converted is None:
            return native or Extracted(kind, "stored", None, [], "FILE_OFFICE_CONVERSION_FAILED")
        result = extract(f"converted.{target}", converted)
        if native is not None and result.status != "read":
            return native
        if target == "pdf":
            # These originals have no PDF page viewer. Number the extracted text
            # paragraphs continuously, never cite LibreOffice's print pagination.
            pieces, first = [], {}
            for piece in result.pieces:
                first[piece.locator.get("page")] = len(pieces) + 1
                for text in re.split(r"\n\s*\n", piece.text):
                    if text.strip():
                        pieces.append(Piece({"paragraph": len(pieces) + 1}, text.strip()))
            flags = [
                Flag(
                    flag.kind,
                    {"paragraph": first[flag.locator["page"]]}
                    if flag.locator.get("page") in first
                    else {},
                    flag.excerpt,
                    flag.count,
                )
                for flag in result.flags
            ]
            return Extracted(kind, result.status, None, pieces, result.note, flags)
        return Extracted(
            kind, result.status, result.pages, result.pieces, result.note, result.flags
        )
    if kind is not None and _locked(kind, data):
        return Extracted(kind, "unreadable", None, [], "FILE_LOCKED")
    if kind is None or not _looks_right(kind, data):
        return Extracted("other", "stored", None, [], "FILE_NOT_READ_YET")
    if kind in _STORED:
        return Extracted(kind, "stored", None, [], _STORED[kind])
    if kind in _IMAGES:
        return Extracted(kind, "stored", 1, [], "FILE_IMAGE_STORED")
    if kind in ("dwg", "dxf"):
        x = _drawing(name, data)
    elif kind == "pdf":
        x = _pdf(data)
    elif kind in ("xlsx", "xls", "docx", "ifc"):
        x = _reader(kind, data)
    else:
        x = _text(kind, data)
    ai = hidden.ai_instruction_flags(x.pieces)
    return (
        Extracted(x.kind, x.status, x.pages, x.pieces, x.note, x.flags + ai, x.page_sources)
        if ai
        else x
    )


def _drawing(name: str, data: bytes) -> Extracted:
    from qsone.records.drawings import read_drawing, sheets_from_drawing

    drawing = read_drawing(name, data)
    kind = name.rsplit(".", 1)[-1].lower()
    if drawing.note and not drawing.repaired:
        return Extracted(kind, "stored", None, [], drawing.note)
    sheets = sheets_from_drawing(drawing)
    pieces = [
        Piece({"sheet": t.get("layout", "Model"), "handle": t["handle"]}, t["text"])
        for t in drawing.texts
        if t.get("text")
    ]
    for insert in drawing.inserts:
        pieces.extend(
            Piece(
                {
                    "sheet": insert.get("layout", "Model"),
                    "handle": a.get("handle") or insert["handle"],
                },
                a["value"],
            )
            for a in insert.get("attributes", [])
            if a.get("value")
        )
    return Extracted(
        kind, "partly_read" if drawing.repaired else "read", len(sheets), pieces, drawing.note
    )


def _reader(kind: str, data: bytes) -> Extracted:
    # imported here: the readers import Piece from this module
    from qsone.records.readers import docx, ifc

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
        return Extracted(kind, "read", None, ifc.read(data), None)
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


# A clause number in Arabic-Indic digits with dashes («١٢-١-٢-») in a right-to-left line: a
# dash does not join Arabic-Indic digits, so each number shows on its own and pdfium gives them
# left to right as they are seen («-٢-١-١٢»). Such a run is put back in reading order. A run
# joined by a dot, a comma or a slash shows as one number and is left as it is.
_AN = "[\u0660-\u0669\u06f0-\u06f9]+"
_RTL_RUN = re.compile(
    rf"(?<![\u0660-\u0669\u06f0-\u06f9.,/\u066b\u066c])"
    rf"(?:(?<![\u0660-\u0669\u06f0-\u06f9]):)?[-\u2013]*{_AN}(?:[-\u2013]+{_AN})*[-\u2013]*"
    rf"(?::(?![\u0660-\u0669\u06f0-\u06f9]))?"
    rf"(?![\u0660-\u0669\u06f0-\u06f9.,/\u066b\u066c])"
)
_RTL_TOKEN = re.compile(rf"{_AN}|[-\u2013:]")
_ARABIC_LETTER = re.compile("[\u0621-\u064a]")
# A lam-alef ligature («لا», «لأ», «لإ», «لآ», «لى») is one glyph; some PDFs map it to its two
# letters alef first («خالل» for «خلال», MOF and imamu booklets). Its two letters share one box on
# the page, which a written «ال» never does.
_ALEF_LAM = re.compile("[\u0627\u0623\u0625\u0622\u0649]\u0644")


@pdfium_locked
def _page_text(textpage) -> str:
    """The page's text, with each lam-alef ligature in its letters' order (`_ALEF_LAM`) and
    Arabic-Indic clause numbers in reading order (`_RTL_RUN`): only in a line with Arabic
    letters, and only where the page has the run left to right."""
    text = textpage.get_text_range()
    tp = textpage.raw
    if len(text) != pdfium_c.FPDFText_CountChars(tp) or not _ARABIC_LETTER.search(text):
        return text  # a character index is not a place in the text: nothing is moved
    text = _ligatures(tp, text)
    out, done = [], 0
    for m in _RTL_RUN.finditer(text):
        tokens = _RTL_TOKEN.findall(m[0])
        if len(tokens) < 2:
            continue
        start = text.rfind("\n", 0, m.start()) + 1
        end = text.find("\n", m.end())
        if not _ARABIC_LETTER.search(text[start : len(text) if end < 0 else end]):
            continue
        if not _left_to_right(tp, m.start(), m.end() - 1):
            continue  # already in reading order
        out += [text[done : m.start()], "".join(reversed(tokens))]
        done = m.end()
    return "".join(out) + text[done:] if out else text


@pdfium_locked
def _box(tp, i: int) -> tuple[float, ...] | None:
    box = [ctypes.c_double() for _ in range(4)]  # left, right, bottom, top
    if not pdfium_c.FPDFText_GetCharBox(tp, i, *box):
        return None
    return tuple(b.value for b in box)


@pdfium_locked
def _ligatures(tp, text: str) -> str:
    """`text` with each alef-then-lam pair drawn as one glyph turned to lam-then-alef."""
    chars = None
    for m in _ALEF_LAM.finditer(text):
        i = m.start()
        first = _box(tp, i)
        if first is None or first[0] == first[1] or first != _box(tp, i + 1):
            continue  # two glyphs: a written «ال»
        chars = chars or list(text)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return text if chars is None else "".join(chars)


@pdfium_locked
def _left_to_right(tp, first: int, last: int) -> bool:
    """Character `first` is left of character `last` on the page."""
    boxes = []
    for i in (first, last):
        box = [ctypes.c_double() for _ in range(4)]  # left, right, bottom, top
        if not pdfium_c.FPDFText_GetCharBox(tp, i, *box):
            return False
        boxes.append(box[0].value)
    return boxes[0] < boxes[1]


def arabic_quality(text: str) -> float:
    """Directional evidence per Arabic word; higher means more likely logical order.

    This is a source selector, never an instruction to reverse arbitrary text.
    """
    text = unicodedata.normalize("NFKC", text)
    words = re.findall(r"[ء-ي]+", text)
    if not words:
        return 0.0
    good = sum(w.startswith(("ال", "وال", "بال")) for w in words)
    bad = sum(
        w.endswith("لا")
        or w.startswith(("ة", "ى"))
        or w in {"ىلع", "سفانتملا", "يئادتبالا", "ةيكنبلا"}
        for w in words
    )
    flipped = len(re.findall(r"\)[^()\n]+\(|\][^\[\]\n]+\[", text))
    return (good - 2 * bad - flipped) / len(words)


def _inspector_text(data: bytes, index: int) -> str:
    import pdf_inspector

    result = pdf_inspector.extract_pages_markdown_bytes(data, [index])
    return "\n".join(p.markdown for p in result.pages if p.page == index)


def _pypdf_text(data: bytes, index: int) -> str:
    from pypdf import PdfReader

    return PdfReader(io.BytesIO(data)).pages[index].extract_text() or ""


def _plain_markdown(text: str) -> str:
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "", text)
    text = re.sub(r"!?\[([^]\n]*)\]\([^\n)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*\|?\s*:?-{3,}.*$", "", text)
    return text.replace("**", "").replace("`", "").replace("|", " ")


def select_pdf_text(data: bytes, index: int, text: str, *, inspector=None) -> tuple[str, str]:
    text = unicodedata.normalize("NFKC", text)
    score = arabic_quality(text)
    if score >= 0:
        return text, "pdfium"
    # Prefer inspector's logical reading order. pypdf is a last resort because
    # its line order can be scrambled. Never write decrypted bytes to a path.
    for source, reader in (("pdf-inspector", _inspector_text), ("pypdf", _pypdf_text)):
        try:
            candidate = unicodedata.normalize(
                "NFKC",
                inspector(index)
                if source == "pdf-inspector" and inspector
                else reader(data, index),
            )
            if source == "pdf-inspector":
                candidate = _plain_markdown(candidate)
            if re.search(r"[ء-ي]", candidate) and arabic_quality(candidate) > score:
                return candidate, source
        except Exception:
            continue  # a damaged alternative must not discard pdfium's text
    return text, "pdfium"


@pdfium_locked
def _pdf(data: bytes) -> Extracted:
    pieces, flags, pdf = [], [], None
    sources = {}
    inspector_pages = None

    def inspector(index):
        nonlocal inspector_pages
        if inspector_pages is None:
            import pdf_inspector

            inspector_pages = {}
            result = pdf_inspector.extract_pages_markdown_bytes(data)
            inspector_pages.update({p.page: p.markdown for p in result.pages})
        return inspector_pages.get(index, "")

    try:
        pdf = pdfium.PdfDocument(data)
        pages = len(pdf)
        for i in range(pages):
            page = pdf[i]
            textpage = page.get_textpage()
            selected, sources[i + 1] = select_pdf_text(
                data, i, _page_text(textpage), inspector=inspector
            )
            text = display_text(selected, keep_blanks=True)
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
        return Extracted("pdf", "read", pages, pieces, None, flags, sources)
    status = "partly_read" if pieces else "unreadable"
    return Extracted("pdf", status, pages, pieces, "FILE_SCANNED_PAGES", flags, sources)


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
    if isinstance(value, float):
        return display_number(value)  # as Excel shows it: 4.77, never 4.7699999999999996
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
