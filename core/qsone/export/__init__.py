"""Exports (Plan 6): Excel, Word and PDF, built in memory from a Deliverable's view. They read the
view only and never compute a number: every value is the ledger's exact decimal string, written
as it is (grouped for reading, never rounded).

    to_xlsx(view)                 a Sheet
    to_docx(view)                 a Document
    to_pdf(view)                  a Sheet or a Document
    review_pdf(report, language)  a Review report (Task 4's `review.review_report`)
    file_name(view, ext)          "<title> - Rev 2.xlsx" / "<title> - مسودة.xlsx"

The helpers below are shared by the three formats."""

import re

from qsone import copy
from qsone.records.project import RecordsError

# Founder defaults, pending his confirmation; each is one switch. Excel always holds plain
# values: the view carries no formulas, and a live Excel formula would compute outside the
# QS Calc Engine.
DRAFT_EXPORTS = True  # a Deliverable may be exported before Sign-off, marked «مسودة — غير معتمد»
WESTERN_DIGITS = True  # numbers in Arabic exports are written 0-9; False writes ٠-٩

FONT = "Arial"  # Excel and Word: on every Windows and Mac machine, Latin and Arabic
DASH = "—"  # a calculated cell with nothing to show: never an invented 0

_DECIMAL = re.compile(r"(-?)(\d+)(?:\.(\d+))?")
_ARABIC_DIGITS = str.maketrans("0123456789.,", "٠١٢٣٤٥٦٧٨٩٫٬")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')  # not allowed in a Windows file name


def say(name: str, language: str, **values) -> str:
    """The export label `name` in `language`, with its {placeholders} filled."""
    return copy.EXPORT_LABELS[name][language].format(**values)


def format_decimal(value: str, places: int = 0, language: str = "en") -> str:
    """An exact decimal string for reading: the whole part grouped by thousands, the decimals
    padded to at least `places` and never cut, so nothing is rounded. Never through `float`."""
    found = _DECIMAL.fullmatch(value)
    if found is None:
        raise ValueError(f"not an exact decimal: {value!r}")
    sign, whole, decimals = found[1], found[2], (found[3] or "").ljust(places, "0")
    out = f"{sign}{int(whole):,}" + (f".{decimals}" if decimals else "")
    return out if WESTERN_DIGITS or language != "ar" else out.translate(_ARABIC_DIGITS)


def isolate(text: str) -> str:
    """`text` as a first-strong bidi isolate (FSI … PDI), for a value set into a line of other
    text: a date after Arabic words would otherwise show as 05-11-2026 (the Unicode rule
    for numbers after Arabic letters), and a Latin phrase would take the line's direction."""
    return f"\u2068{text}\u2069" if text else ""


def places(cell: dict) -> int:
    """Money shows at least two decimals; any other number shows exactly what is stored."""
    return 2 if cell.get("currency") else 0


def check_draft(view: dict) -> None:
    """Refuses a draft export when DRAFT_EXPORTS is off."""
    if not DRAFT_EXPORTS and view.get("status") != "signed_off":
        raise RecordsError(copy.EXPORT_LABELS["needs_signoff"])


def state(view: dict) -> str:
    """«إصدار 2» / "Rev 2" for a signed-off view, else the draft mark."""
    language = view["language"]
    if view.get("status") == "signed_off":
        return say("rev", language, n=view["revision"]["no"])
    return copy.EXPORT_DRAFT_MARK[language]


def marks(view: dict) -> list[str]:
    """The marks every page carries: the draft mark before Sign-off, and «بيانات تجريبية»."""
    language = view["language"]
    out = [] if view.get("status") == "signed_off" else [copy.EXPORT_DRAFT_MARK[language]]
    return out + ([copy.SAMPLE_DATA[language]] if view.get("sample") else [])


def file_name(view: dict, ext: str) -> str:
    """'<title> - Rev 2.<ext>' or '<title> - مسودة.<ext>', in the Deliverable's language, safe
    as a Windows file name."""
    language = view["language"]
    title = " ".join(_UNSAFE.sub(" ", view["title"]).split())[:100].rstrip(". ")
    if view.get("status") == "signed_off":
        tail = say("rev", language, n=view["revision"]["no"])
    else:
        tail = say("draft", language)
    return f"{title or say('deliverable', language)} - {tail}.{ext}"


def who(actor: str | None, language: str) -> str:
    """An actor id as a reader would say it: «المهندس», «مهندس المراجعة», …"""
    known = {
        "engineer": copy.EXPORT_LABELS["engineer"],
        "lead_qs": copy.ROLE_LEAD,
        "checking_qs": copy.ROLE_CHECKER,
        "calc_engine": copy.EXPORT_LABELS["calc_engine"],
    }
    return known[actor][language] if actor in known else actor or ""


def source_kind(kind: str, language: str) -> str:
    """Who or what entered a number, from its source kind."""
    known = {
        "engineer": copy.ENTERED_BY_ENGINEER,
        "calculation": copy.EXPORT_LABELS["calc_engine"],
        "sample": copy.SAMPLE_DATA,
    }
    return known[kind][language] if kind in known else kind


def place(locator: dict, language: str) -> str:
    """Where in its file a source stands: «صفحة 3», «ورقة BOQ، صف 12»."""
    parts = []
    for key, value in locator.items():
        if key == "calculation":
            continue  # a calculation's place is its formula, already the source's title
        label = say(key, language) if key in {"page", "sheet", "row", "cell"} else key
        parts.append(f"{label} {value}")
    return ("، " if language == "ar" else ", ").join(parts)


def shown_numbers(view: dict):
    """Every number a Sheet view shows, in reading order: (where, column label, cell). `where`
    is the item code, the section title or the grand total's label."""
    language = view["language"]
    columns = view["columns"]
    for row in view["rows"]:
        where = row.get("code") if row["kind"] == "item" else row.get("title")
        for column in columns:
            cell = row["cells"].get(column["key"])
            if cell and "value" in cell:
                yield where or "", column["label"][language], cell
    if view.get("total"):
        total = next((c for c in columns if c["kind"] == "calc"), columns[-1])
        yield say("total", language), total["label"][language], view["total"]


def source_line(view: dict, cell: dict) -> dict:
    """A number's source as the sources list shows it."""
    language = view["language"]
    source = view["sources"].get(cell.get("source"), {})
    return {
        "unit": cell.get("currency") or cell.get("unit") or "",
        "title": source.get("title") or "",
        "file": source.get("file_name") or "",
        "place": place(source.get("locator") or {}, language),
        "link": source.get("url") or "",
        "dated": cell.get("dated") or source.get("dated") or "",
        "kind": source_kind(source.get("kind", ""), language),
    }


def layout(view: dict) -> list[dict]:
    """A Sheet view's rows as the exports lay them out: [{"kind": "item" | "section" | "total",
    "cells": [{"span": n, "text": str} | {"span": 1, "number": cell}]}], one entry per column
    (or per span). A section's title, and the total's label, span the text columns before the
    first number column. A calculated cell with nothing to show is a dash."""
    language = view["language"]
    columns = view["columns"]
    lead = next((i for i, c in enumerate(columns) if c["kind"] != "text"), len(columns)) or 1

    def show(column: dict, cell: dict | None) -> dict:
        if cell and "value" in cell:
            return {"span": 1, "number": cell}
        if cell and "text" in cell:
            return {"span": 1, "text": cell["text"]}
        return {"span": 1, "text": DASH if column["kind"] == "calc" else ""}

    def headed(label: str, cells: dict) -> list[dict]:
        """A section or the total: its label, then only the calculated cells."""
        out = [{"span": lead, "text": label}]
        for column in columns[lead:]:
            calc = column["kind"] == "calc"
            out.append(show(column, cells.get(column["key"])) if calc else {"span": 1, "text": ""})
        return out

    rows = []
    for row in view["rows"]:
        if row["kind"] == "section":
            rows.append({"kind": "section", "cells": headed(row.get("title", ""), row["cells"])})
        else:
            cells = [show(c, row["cells"].get(c["key"])) for c in columns]
            rows.append({"kind": "item", "cells": cells})
    total = view.get("total")
    label = say("total", language) + (
        f" ({total['currency']})" if total and total.get("currency") else ""
    )
    calc_key = next((c["key"] for c in columns if c["kind"] == "calc"), None)
    rows.append({"kind": "total", "cells": headed(label, {calc_key: total} if total else {})})
    return rows


from qsone.export.docx import to_docx  # noqa: E402
from qsone.export.pdf import review_pdf, to_pdf  # noqa: E402
from qsone.export.xlsx import to_xlsx  # noqa: E402

__all__ = ["file_name", "format_decimal", "review_pdf", "to_docx", "to_pdf", "to_xlsx"]
