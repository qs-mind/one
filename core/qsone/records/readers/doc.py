"""A Word 97-2003 file (.doc) read by ONE itself, in memory, with olefile: its text, tables,
headings and list numbers (doc_document, doc_blocks), the Excel sheets inside it (one piece per
row, by xlrd or openpyxl), hidden text flagged, and the parts it could not read with why.

`extracted(data)` gives None for a file that is not Word 97-2003 (RTF, OpenDocument or a web
page named .doc, a Word 6.0/95 file, other bytes): the caller has LibreOffice try it."""

import io
import zipfile

from qsone.records import hidden, office
from qsone.records.extract import Extracted, Piece
from qsone.records.readers import doc_ole as ole
from qsone.records.readers.doc_document import LOST, Document
from qsone.records.unread import part

MAX_ROWS, MAX_COLUMNS, MAX_CELLS = 4096, 256, 100000


def _row(values: list) -> str:
    shown = ["" if v is None else " ".join(str(v).split()) for v in values]
    while shown and not shown[-1]:
        shown.pop()
    return " | ".join(shown)


def _sheet_rows(found: ole.Embedded):
    """(sheet name, row number, values) of an Excel sheet inside the file."""
    if found.workbook is not None:
        import xlrd

        book = xlrd.open_workbook(file_contents=found.workbook, on_demand=True)
        try:
            for sheet in book.sheets():
                for r in range(min(sheet.nrows, MAX_ROWS)):
                    values = sheet.row_values(r, 0, min(sheet.ncols, MAX_COLUMNS))
                    yield sheet.name, r + 1, values
        finally:
            book.release_resources()
        return
    import openpyxl

    with zipfile.ZipFile(io.BytesIO(found.package)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 4 * ole.WORKBOOK_LIMIT:
            raise ValueError("the sheet inside is too large")
    book = openpyxl.load_workbook(
        io.BytesIO(found.package), read_only=True, data_only=True, keep_links=False
    )
    try:
        for sheet in book:
            rows = sheet.iter_rows(max_row=MAX_ROWS, max_col=MAX_COLUMNS, values_only=True)
            for r, values in enumerate(rows, 1):
                yield sheet.title, r, list(values)
    finally:
        book.close()


def embedded_pieces(objects: list[ole.Embedded]) -> tuple[list[Piece], dict[str, int]]:
    """One piece per row of each Excel sheet inside, `{object, sheet, row}`; and what was not
    read: sheets too large or damaged, rows past the cell limit, other objects."""
    pieces, missed, cells = [], {"sheets": 0, "cells": 0, "others": 0}, 0
    for n, found in enumerate(objects, 1):
        if found.too_large:
            missed["sheets"] += 1
            continue
        if found.workbook is None and found.package is None:
            missed["others"] += 1
            continue
        try:
            for sheet, r, values in _sheet_rows(found):
                text = _row(values)
                if not text:
                    continue
                cells += len(values)
                if cells > MAX_CELLS:
                    missed["cells"] = 1
                    break
                pieces.append(Piece({"object": n, "sheet": sheet, "row": r}, text))
        except Exception:  # xlrd and openpyxl raise many kinds of error on a damaged sheet
            missed["sheets"] += 1
    return pieces, missed


def unread_parts(doc: Document, streams: ole.Streams, missed: dict[str, int]) -> list[dict]:
    from qsone import copy

    parts = []
    if doc.missing or streams.short:
        parts.append(part(copy.UNREAD_DOC_END, copy.UNREAD_WHY_CUT))
    lost = {LOST[i] for i in doc.fib.lost if i in LOST} | doc.notes
    if doc.lists.damaged:
        lost.add("numbering")
    for key in sorted(lost):
        parts.append(part(copy.UNREAD_DOC_LOST[key], copy.UNREAD_WHY_PLAIN))
    for key, what, why in (
        ("deleted", copy.UNREAD_DOC_DELETIONS, copy.UNREAD_WHY_DELETIONS),
        ("forms", copy.UNREAD_DOC_FORMS, copy.UNREAD_WHY_FORMS),
        ("symbols", copy.UNREAD_DOC_SYMBOLS, copy.UNREAD_WHY_SYMBOLS),
    ):
        if doc.counts[key]:
            parts.append(part(copy.fill(what, count=str(doc.counts[key])), why))
    sheets = sum(1 for o in streams.objects if o.workbook is not None or o.package is not None)
    pictures = max(doc.pictures() - sheets - missed["sheets"], missed["others"], 0)
    if pictures:
        what = copy.fill(copy.UNREAD_PICTURES, count=str(pictures))
        parts.append(part(what, copy.UNREAD_WHY_PICTURES))
    if missed["sheets"]:
        what = copy.fill(copy.UNREAD_EMBEDDED_SHEETS, count=str(missed["sheets"]))
        parts.append(part(what, copy.UNREAD_WHY_SHEETS))
    if missed["cells"]:
        parts.append(part(copy.UNREAD_EMBEDDED_CELLS, copy.UNREAD_WHY_SHEETS))
    return parts


def _not_read(e: ole.NotRead, data: bytes) -> Extracted | None:
    if e.reason == ole.LOCKED:
        return Extracted("doc", "unreadable", None, [], "FILE_LOCKED")
    if e.reason == ole.DAMAGED:
        return Extracted("doc", "unreadable", None, [], "FILE_UNREADABLE")
    if e.reason == ole.IS_DOCX:
        from qsone.records.extract import _reader

        x = _reader("docx", data)
        return Extracted("doc", x.status, x.pages, x.pieces, x.note, x.flags)
    if e.reason == ole.TOO_OLD and office.find_soffice() is None:
        return Extracted("doc", "stored", None, [], "FILE_OLD_WORD")
    return None  # RTF, OpenDocument, a web page, Word 6.0/95 or other bytes: LibreOffice tries


def extracted(data: bytes) -> Extracted | None:
    try:
        streams = ole.open_streams(data)
        doc = Document(streams)
        pieces = doc.read()
        flags, vanished = doc.flags()
    except ole.NotRead as e:
        return _not_read(e, data)
    except Exception:  # a damaged file may break any assumption; it is never a crash
        return Extracted("doc", "unreadable", None, [], "FILE_UNREADABLE")
    sheets, missed = embedded_pieces(streams.objects)
    # vanished text is not in the pieces, but is still checked for orders to an AI
    flags += hidden.ai_instruction_flags(vanished)
    unread = unread_parts(doc, streams, missed)
    status, note = ("partly_read", "FILE_PARTLY_READ") if unread else ("read", None)
    return Extracted("doc", status, None, pieces + sheets, note, flags, unread=unread)
