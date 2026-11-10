"""A DWG or DXF as pieces for Project Records, with what was not read (`read_report`).

Pieces: one per text (TEXT, MTEXT, attribute, multileader, tolerance, attribute definition),
one per table row, native or an Excel sheet inside the drawing (cells in their columns, an
empty cell kept as an empty place), and one per dimension (the text the sheet shows, else the
override with `<>` as the measurement, else the measurement). Locators keep `{sheet, handle}`;
a table row adds `row` (from 1), a dimension `kind: "DIMENSION"`, other texts their `kind`."""

import json
from pathlib import PurePath

from qsone import copy
from qsone.records.arabic import display_number
from qsone.records.extract import Extracted, Piece
from qsone.records.unread import count, part

_PLAIN_KINDS = {None, "TEXT", "MTEXT", "ATTRIBUTE", "TABLE"}
_NOTES = {
    "not-a-dwg": "FILE_DRAWING_NOT_DWG",
    "unsupported-version": "FILE_DRAWING_TOO_OLD",
    "damaged": "FILE_DRAWING_DAMAGED",
    "too-large": "FILE_DRAWING_TOO_LARGE",
}
_3D = {"3DSOLID", "REGION", "BODY", "SURFACE", "MESH"}
_OWN_PROBLEMS = {
    "output-limit",
    "embedded-cell-limit",
    "embedded-workbook-unreadable",
    "embedded-workbook-too-large",
}
MAX_FILES = 20  # attached files named one by one; the rest are counted


def note_of(reason: str | None) -> str:
    return _NOTES.get(reason or "", "FILE_UNREADABLE")


def _locator(row: dict) -> dict:
    return {"sheet": row.get("layout", "Model"), "handle": row.get("handle")}


def _text_pieces(drawing) -> list[Piece]:
    pieces, seen = [], set()
    for t in drawing.texts:
        if not t.get("text") or "table_cell" in t:
            continue
        locator = _locator(t)
        if t.get("kind") not in _PLAIN_KINDS:
            locator["kind"] = t["kind"]
        seen.add((t.get("handle"), t["text"]))
        pieces.append(Piece(locator, t["text"]))
    for insert in drawing.inserts:
        for a in insert.get("attributes", []):
            handle = a.get("handle") or insert["handle"]
            if a.get("value") and (handle, a["value"]) not in seen:
                pieces.append(
                    Piece({"sheet": insert.get("layout", "Model"), "handle": handle}, a["value"])
                )
    return pieces


def _table_pieces(drawing) -> list[Piece]:
    tables: dict[tuple, dict[int, dict[int, str]]] = {}
    for t in drawing.texts:
        cell = t.get("table_cell")
        if not cell or not isinstance(cell, list) or len(cell) != 2:
            continue
        # a table in a block comes once per insert, `context` naming the insert
        key = (t.get("layout", "Model"), t.get("handle"), t.get("embedded_sheet"), t.get("context"))
        row = tables.setdefault(key, {}).setdefault(int(cell[0]), {})
        text = (t.get("text") or "").strip()
        row[int(cell[1])] = " ".join(filter(None, [row.get(int(cell[1])), text]))
    pieces, shown_tables = [], set()
    for (layout, handle, sheet, _), rows in tables.items():
        same = (layout, handle, sheet, json.dumps(rows, sort_keys=True, ensure_ascii=False))
        if same in shown_tables:  # the same block placed again on this sheet
            continue
        shown_tables.add(same)
        for r in sorted(rows):
            cells = rows[r]
            shown = [cells.get(c, "") for c in range(max(cells) + 1)]
            while shown and not shown[-1]:
                shown.pop()
            if not any(shown):
                continue
            locator = {"sheet": layout, "handle": handle, "row": r + 1}
            if sheet is not None:
                locator["embedded_sheet"] = sheet
            pieces.append(Piece(locator, " | ".join(shown)))
    return pieces


def _measure(d: dict) -> str:
    value = d.get("measured")
    if not isinstance(value, int | float):
        return ""
    factor = d.get("dimlfac")
    return display_number(round(value * factor if isinstance(factor, int | float) else value, 4))


def dimension_text(d: dict) -> str:
    shown = " ".join(s.strip() for s in d.get("shown") or [] if isinstance(s, str) and s.strip())
    if shown:
        return shown
    override = (d.get("text") or "").strip()
    if override and override != "<>":
        return override.replace("<>", _measure(d)).strip()
    return _measure(d)


def _dimension_pieces(drawing) -> list[Piece]:
    pieces = []
    for d in drawing.dimensions:
        text = dimension_text(d)
        if text:
            locator = _locator(d) | {"kind": "DIMENSION"}
            if d.get("kind"):
                locator["dimension"] = d["kind"]
            pieces.append(Piece(locator, text))
    return pieces


def pieces(drawing) -> list[Piece]:
    return _text_pieces(drawing) + _table_pieces(drawing) + _dimension_pieces(drawing)


def _file_name(path) -> str:
    name = PurePath(str(path or "").replace("\\", "/")).name
    return name[:120] or "?"


def _references(drawing) -> list[dict]:
    found = []
    for x in drawing.xrefs:
        found.append(
            copy.fill(copy.UNREAD_XREF_FILE, name=_file_name(x.get("path") or x.get("name")))
        )
    for r in drawing.references:
        text = copy.UNREAD_PICTURE_FILE if r.get("kind") == "IMAGE" else copy.UNREAD_UNDERLAY_FILE
        found.append(copy.fill(text, name=_file_name(r.get("path"))))
    unique = list({p["en"]: p for p in found}.values())
    parts = [part(p, copy.UNREAD_WHY_OTHER_FILE) for p in unique[:MAX_FILES]]
    if len(unique) > MAX_FILES:
        more = copy.fill(copy.UNREAD_MORE_FILES, count=str(len(unique) - MAX_FILES))
        parts.append(part(more, copy.UNREAD_WHY_OTHER_FILE))
    return parts


def _problems(drawing) -> tuple[int, dict[str, int]]:
    """Damage the reader repaired, and Python's own problems with sheets inside, by code."""
    repaired, own = 0, {}
    for p in drawing.problems:
        code = p.get("code") if isinstance(p, dict) else None
        if code in _OWN_PROBLEMS:
            own[code] = own.get(code, 0) + 1
        else:
            repaired += 1
    return repaired, own


def read_report(drawing) -> list[dict]:
    """Each part of a read drawing that ONE did not read, with why: rows the reader did not keep,
    damaged records, objects it does not read inside, other files the drawing names, pictures
    and Excel sheets inside it."""
    parts, rows = [], copy.UNREAD_DRAWING_ROWS
    omitted = drawing.omitted if isinstance(drawing.omitted, dict) else {}
    for key in ("texts", "inserts", "dimensions", "tables", "references"):
        if omitted.get(key):
            parts.append(part(count(rows[key], int(omitted[key])), copy.UNREAD_WHY_TOO_MANY))
    other = sum(
        int(v)
        for k, v in omitted.items()
        if k in ("blocks", "layers", "layouts", "xrefs", "styles")
    )
    if other:
        parts.append(part(count(rows["objects"], other), copy.UNREAD_WHY_TOO_MANY))
    if omitted.get("embedded"):
        what = copy.fill(copy.UNREAD_EMBEDDED_LEFT, count=str(int(omitted["embedded"])))
        parts.append(part(what, copy.UNREAD_WHY_TOO_MANY))
    if isinstance(drawing.cut_texts, int) and drawing.cut_texts > 0:
        what = copy.fill(copy.UNREAD_DRAWING_CUT, count=str(drawing.cut_texts))
        parts.append(part(what, copy.UNREAD_WHY_CUT_SHORT))
    if drawing.traversal_limited:
        parts.append(part(copy.UNREAD_DRAWING_NESTED, copy.UNREAD_WHY_NESTED))
    skipped = int((drawing.stats or {}).get("skipped") or 0)
    repaired, own = _problems(drawing)
    if skipped:
        n = str(skipped)
        parts.append(part(copy.fill(copy.UNREAD_DRAWING_RECORDS, count=n), copy.UNREAD_WHY_DAMAGED))
    elif repaired:
        n = str(repaired)
        parts.append(
            part(copy.fill(copy.UNREAD_DRAWING_REPAIRED, count=n), copy.UNREAD_WHY_REPAIRED)
        )
    kinds = drawing.unread_kinds if isinstance(drawing.unread_kinds, dict) else {}
    solids = sum(int(v) for k, v in kinds.items() if k in _3D)
    for kind, n in sorted(kinds.items()):
        if kind in _3D:
            continue
        if kind == "ACAD_PROXY_ENTITY":
            what = copy.fill(copy.UNREAD_DRAWING_PROXY, count=str(n))
        else:
            what = copy.fill(copy.UNREAD_DRAWING_KIND, kind=str(kind)[:60], count=str(n))
        parts.append(part(what, copy.UNREAD_WHY_KIND))
    if solids:
        parts.append(
            part(copy.fill(copy.UNREAD_DRAWING_3D, count=str(solids)), copy.UNREAD_WHY_KIND)
        )
    parts += _references(drawing)
    pictures = sum(1 for e in drawing.embedded if not _workbook(e))
    if pictures:
        parts.append(
            part(copy.fill(copy.UNREAD_PICTURES, count=str(pictures)), copy.UNREAD_WHY_PICTURES)
        )
    sheets = sum(1 for e in drawing.embedded if _workbook(e) and e.get("too_large"))
    sheets += own.get("embedded-workbook-unreadable", 0) + own.get("embedded-workbook-too-large", 0)
    if sheets:
        what = copy.fill(copy.UNREAD_EMBEDDED_SHEETS, count=str(sheets))
        parts.append(part(what, copy.UNREAD_WHY_SHEETS))
    if own.get("embedded-cell-limit"):
        parts.append(part(copy.UNREAD_EMBEDDED_CELLS, copy.UNREAD_WHY_TOO_MANY))
    return parts


def _workbook(embedded: dict) -> bool:
    streams = [s.lower() for s in embedded.get("streams") or [] if isinstance(s, str)]
    return "workbook" in streams or "book" in streams or "package" in streams


def extracted(name: str, data: bytes) -> Extracted:
    from qsone.records.drawings import read_drawing, sheets_from_drawing

    drawing = read_drawing(name, data)
    kind = name.rsplit(".", 1)[-1].lower()
    if drawing.note and not drawing.repaired:
        status = "stored" if drawing.note == "FILE_DRAWINGS_MISSING" else "unreadable"
        return Extracted(kind, status, None, [], drawing.note)
    sheets = sheets_from_drawing(drawing)
    unread = read_report(drawing)
    note = "FILE_PARTLY_READ" if unread else None
    status = "partly_read" if unread else "read"
    return Extracted(kind, status, len(sheets), pieces(drawing), note, unread=unread)
