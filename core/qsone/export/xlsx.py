"""A Sheet to Excel (openpyxl), in memory: the view's values as exact decimals, right to left for
an Arabic Deliverable, frozen header and code column, and a «المصادر» sheet listing each number's
source and date."""

import io
import re
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from qsone import copy
from qsone.export import FONT, check_draft, layout, say, shown_numbers, source_line, state

COPPER, STONE, SLATE = "FFA6491B", "FFF2EEE7", "FF6E6A64"
HEADER = 2  # row 1 holds the title and the marks; the column labels are row 2
_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")


def _font(**kw) -> Font:
    return Font(name=FONT, **kw)


def _number(target, cell: dict) -> None:
    """Writes a view number into an Excel cell as its exact text. openpyxl would write a Decimal
    through "%.16g" (a float); this keeps the ledger's digits in <v>, and Excel reads it as a
    number. The format shows every stored decimal (money at least two)."""
    text = format(Decimal(cell["value"]), "f")
    target.value = Decimal(text)  # a number cell (t="n")
    target._value = text  # what <v> holds, digit for digit
    decimals = len(text.partition(".")[2])
    if cell.get("currency"):
        decimals = max(decimals, 2)
    target.number_format = "#,##0" + ("." + "0" * decimals if decimals else "")


def _text(target, value: str | None) -> None:
    """Writes text as text: one starting with "=" stays a string, never a formula, so a
    description from a tender file cannot run in Excel."""
    target.value = value or None
    if target.data_type == "f":
        target.data_type = "s"


def _sheet_title(title: str) -> str:
    return _SHEET_NAME.sub("", title).strip().strip("'")[:31].strip() or "Sheet"


def to_xlsx(view: dict) -> bytes:
    """A Sheet view as an .xlsx file."""
    if view.get("kind") != "sheet":
        raise ValueError("only a Sheet exports to Excel")
    check_draft(view)
    language = view["language"]
    columns = view["columns"]
    wb = Workbook()
    ws = wb.active
    ws.title = _sheet_title(view["title"])
    ws.sheet_view.rightToLeft = language == "ar"

    sample = [copy.SAMPLE_DATA[language]] if view.get("sample") else []
    head = ws.cell(1, 1)
    _text(head, " · ".join([view["title"], state(view), *sample]))
    head.font = _font(bold=True, size=12, color=COPPER)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns))
    for i, column in enumerate(columns, 1):
        label = ws.cell(HEADER, i, column["label"][language])
        label.font = _font(bold=True)
        label.fill = PatternFill("solid", fgColor=STONE)
        label.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = round(column["width"] / 7, 1)

    wrap = {i for i, c in enumerate(columns) if c.get("wrap")}
    for r, row in enumerate(layout(view), HEADER + 1):
        bold = row["kind"] != "item"
        c = 1
        for shown in row["cells"]:
            target = ws.cell(r, c)
            if "number" in shown:
                _number(target, shown["number"])
            else:
                _text(target, shown["text"])
            target.font = _font(bold=bold)
            wrapped = c - 1 in wrap or shown["span"] > 1
            target.alignment = Alignment(vertical="top", wrap_text=wrapped)
            if shown["span"] > 1:
                ws.merge_cells(
                    start_row=r, start_column=c, end_row=r, end_column=c + shown["span"] - 1
                )
            c += shown["span"]
    ws.freeze_panes = f"{get_column_letter(_frozen(columns) + 1)}{HEADER + 1}"

    _sources(wb.create_sheet(copy.SOURCES_SHEET[language]), view)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _frozen(columns: list[dict]) -> int:
    """How many leading columns are frozen (the code column)."""
    count = 0
    for column in columns:
        if not column.get("frozen"):
            break
        count += 1
    return count


_SOURCE_COLUMNS = [
    ("src_where", 14),
    ("src_column", 14),
    ("src_value", 16),
    ("src_unit", 12),
    ("src_title", 36),
    ("src_file", 24),
    ("src_place", 16),
    ("src_link", 28),
    ("src_dated", 12),
    ("src_kind", 18),
]


def _sources(ws, view: dict) -> None:
    """One row per number shown: where, column, value, unit or currency, source, file, place,
    link, date and who entered it."""
    language = view["language"]
    ws.sheet_view.rightToLeft = language == "ar"
    for i, (name, width) in enumerate(_SOURCE_COLUMNS, 1):
        label = ws.cell(1, i, say(name, language))
        label.font = _font(bold=True)
        label.fill = PatternFill("solid", fgColor=STONE)
        ws.column_dimensions[get_column_letter(i)].width = width
    for r, (where, column, cell) in enumerate(shown_numbers(view), 2):
        line = source_line(view, cell)
        values = [
            where,
            column,
            None,
            line["unit"],
            line["title"],
            line["file"],
            line["place"],
            line["link"],
            line["dated"],
            line["kind"],
        ]
        for i, value in enumerate(values, 1):
            target = ws.cell(r, i)
            _text(target, value)
            target.font = _font(color=SLATE) if i > 4 else _font()
        _number(ws.cell(r, 3), cell)
    ws.freeze_panes = "A2"
