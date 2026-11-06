"""What ONE found in a drop of files, said in the project chat without being asked (real walk,
6 Nov 2026: dropping the tender files started nothing). Once per drop, from the core's own
reading, never a model's guess: what each file is, a BOQ's items, sections and its own total with
the sheet, rows and cell they come from, what could not be read, and what a tender still lacks.
Kept as an audit row (`ACTION`), so the chat shows it again after a restart."""

import json
import re
import uuid
from decimal import Decimal

from qsone import copy
from qsone.records import audit, boq
from qsone.records.arabic import clean
from qsone.records.files import read_original
from qsone.records.project import Records, RecordsError, utc_now

ACTION = "files_report"
TABLE = "chats"
ACTOR = "ONE"
FIRST_CHUNKS = 8  # the text a document is sorted by: its name and its first pieces
TENDER = ("boq", "specs", "conditions", "drawings")  # what a tender folder holds

# What a file is, by the words in its name or its first pages (the first that matches).
_WORDS = (
    ("boq", r"مقايس|جدول\s*(?:ال)?كميات|bill\s+of\s+quantit|\bboq\b"),
    ("price_list", r"قائم[ةه]\s*(?:ال)?[اأ]سعار|price\s*list"),
    ("quote", r"عرض\s*(?:ال)?[اأ]?سعار?|quotation|\bquote\b"),
    ("conditions", r"شروط|conditions\s+of\s+contract|general\s+conditions|particular\s+conditions"),
    ("specs", r"مواصفات|specification"),
    ("drawings", r"رسومات|لوحات|\bdrawings?\b|\bdwg\b"),
)
_DRAWING_KINDS = {"dwg", "dxf", "ifc"}
_IMAGE_KINDS = {"png", "jpg", "webp"}


def _sorted_by_words(text: str) -> str | None:
    text = clean(text).casefold()
    return next((label for label, words in _WORDS if re.search(words, text, re.I)), None)


def _boq_sheets(rec: Records, file_id: str, name: str, kind: str) -> tuple[list[dict], bool]:
    """Each sheet Excel shows that reads as a BOQ, with what it holds; and whether a sheet has
    rates but no quantities (a price list)."""
    book = boq.Workbook(file_id, name, kind, read_original(rec, file_id))
    reader = boq._xlsx if kind == "xlsx" else boq._xls
    found, priced = [], False
    listed, _ = reader(book.data, None)
    for sheet, hidden in listed:
        if hidden:
            continue
        ws = reader(book.data, sheet)[1]
        shown = sorted(ws.cells)[: boq.PREVIEW_ROWS]
        header, columns = boq.guess(ws, shown[-1] if shown else 0)
        seen = boq.overview(rec, book, ws, header, columns)
        if seen and seen["items"]:
            found.append({"sheet": ws.name, **seen})
        elif header is not None and "rate" in columns and "quantity" not in columns:
            priced = True
    return found, priced


def _what(rec: Records, f: dict) -> dict:
    """One file: its label and, for a BOQ, its sheets."""
    entry = {"id": f["id"], "name": f["name"], "kind": f["kind"], "status": f["status"]}
    entry["note"] = f["note"]
    if f["status"] == "unreadable" or f["note"] in (
        "FILE_LOCKED",
        "FILE_SHEETS_EMPTY",
        "FILE_LIBREOFFICE_MISSING",
        "FILE_OFFICE_CONVERSION_FAILED",
    ):
        entry["label"] = None
        return entry
    if f["kind"] in boq.KINDS:
        try:
            sheets, priced = _boq_sheets(rec, f["id"], f["name"], f["kind"])
        except (RecordsError, ValueError, KeyError, OSError):
            sheets, priced = [], False
        if sheets:
            entry["label"], entry["sheets"] = "boq", sheets
            return entry
        entry["label"] = "price_list" if priced else (_sorted_by_words(f["name"]) or "sheet")
        return entry
    if f["kind"] in _DRAWING_KINDS:
        entry["label"] = "drawings"
        return entry
    label = _sorted_by_words(f["name"]) or _sorted_by_words(f["text"])
    if label is None and f["kind"] in _IMAGE_KINDS:
        label = "image"
    entry["label"] = label or "document"
    return entry


def _files(conn, ids: list[str]) -> list[dict]:
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT id, name, kind, status, note FROM files WHERE id IN ({marks})"  # noqa: S608
        " AND valid_until IS NULL ORDER BY added_at, rowid",
        ids,
    ).fetchall()
    found = []
    for file_id, name, kind, status, note in rows:
        text = " ".join(
            t
            for (t,) in conn.execute(
                "SELECT text FROM chunks WHERE file_id = ? ORDER BY seq LIMIT ?",
                (file_id, FIRST_CHUNKS),
            )
        )
        found.append(
            {
                "id": file_id,
                "name": name,
                "kind": kind,
                "status": status,
                "note": note,
                "text": text,
            }
        )
    return found


def _amount(value: str) -> str:
    return f"{Decimal(value):,}"


def _sheet_line(s: dict) -> dict:
    sections = copy.counted(s["sections_count"], copy.SECTIONS)
    line = copy.fill(
        copy.REPORT_BOQ_SHEET,
        sheet=s["sheet"],
        items=copy.counted(s["items"], copy.ITEMS),
        sections=sections,
        first=s["first_row"],
        last=s["last_row"],
    )
    total = s["total"]
    if total is None:
        more = copy.REPORT_NO_TOTAL
    else:
        more = copy.fill(
            copy.REPORT_TOTAL,
            total=_amount(total["value"]),
            row=total["row"],
            column=total["column"],
        )
    return {lang: f"{line[lang]} {more[lang]}" for lang in line}


def _lines(entries: list[dict], missing: list[str]) -> list[dict]:
    lines = [copy.fill(copy.REPORT_HEAD, files=copy.counted(len(entries), copy.FILES))]
    for e in entries:
        name = copy.file_name(e["name"])
        if e["label"] is None:
            note = getattr(copy, e["note"] or "FILE_UNREADABLE")
            lines.append(copy.fill(copy.REPORT_NOT_READ, name=name, note=note))
            continue
        label = copy.REPORT_LABELS[e["label"]]
        lines.append(copy.fill(copy.REPORT_FILE, name=name, label=label))
        for s in e.get("sheets", [])[:10]:
            lines.append(_sheet_line(s))
        if (
            e["note"] in ("FILE_SCANNED_PAGES", "FILE_LIBREOFFICE_MISSING")
            or e["status"] == "stored"
        ):
            lines.append(getattr(copy, e["note"] or "FILE_NOT_READ_YET"))
    if missing:
        what = [copy.REPORT_LABELS[m] for m in missing]
        lines.append(
            copy.fill(
                copy.REPORT_MISSING,
                missing={lang: copy.listed([w[lang] for w in what])[lang] for lang in ("en", "ar")},
            )
        )
    return lines


def _labels_before(conn) -> dict[str, str]:
    """The files sorted by earlier reports of this project."""
    labels: dict[str, str] = {}
    for (after,) in conn.execute(
        "SELECT after FROM audit WHERE action = ? ORDER BY id", (ACTION,)
    ).fetchall():
        for f in json.loads(after or "{}").get("files", []):
            if f.get("label"):
                labels[f["id"]] = f["label"]
    return labels


def make(rec: Records, file_ids: list[str]) -> dict | None:
    """The report of the files `file_ids` (one drop), kept for the project chat; None when none
    of them is a current file of the project. {"id", "at", "lines": [{en, ar}], "files"}."""
    ids = list(dict.fromkeys(file_ids))[:5000]
    if not ids:
        return None
    with rec.read() as conn:
        dropped = _files(conn, ids)
        before = _labels_before(conn)
        others = [
            {"id": i, "name": n, "kind": k}
            for i, n, k in conn.execute(
                "SELECT id, name, kind FROM files WHERE valid_until IS NULL"
            ).fetchall()
        ]
    if not dropped:
        return None
    entries = [_what(rec, f) for f in dropped]
    have = {e["label"] for e in entries}
    mine = {e["id"] for e in entries}
    for o in others:
        if o["id"] in mine:
            continue
        label = before.get(o["id"])
        if label is None:
            label = "drawings" if o["kind"] in _DRAWING_KINDS else _sorted_by_words(o["name"])
        have.add(label)
    missing = [m for m in TENDER if m not in have]
    lines = _lines(entries, missing)
    report_id, at = uuid.uuid4().hex, utc_now()
    kept = [
        {"id": e["id"], "label": e["label"], **({"sheets": e["sheets"]} if "sheets" in e else {})}
        for e in entries
    ]
    with rec.write(ACTOR) as conn:
        audit.record(
            conn,
            at=at,
            actor=ACTOR,
            action=ACTION,
            table=TABLE,
            row_id=report_id,
            before=None,
            after={"lines": lines, "files": kept, "missing": missing},
        )
    return {"id": report_id, "at": at, "lines": lines, "files": kept, "missing": missing}


def kept(rec: Records) -> list[dict]:
    """Every report of the project, oldest first: {"id", "at", "lines"}."""
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT row_id, at, after FROM audit WHERE action = ? ORDER BY at, id", (ACTION,)
        ).fetchall()
    return [{"id": i, "at": at, "lines": json.loads(after)["lines"]} for i, at, after in rows]
