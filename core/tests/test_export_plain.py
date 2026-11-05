"""Exports speak plain words (tender day, 5 Nov 2026): the «المصادر» sheet and the PDF sources page
showed «column E، dated_how received», «boq», «quantity * rate» and «sum(amount)»; text in an
empty neighbour cell ran over, so rows looked shifted; the PDF had no header. Synthetic «عينة»
data only."""

import io

import openpyxl
import pypdfium2

from qsone.export import formula_words, to_pdf, to_xlsx
from tests.test_export import tiny_sheet

BOQ = "01 المقايسة - عينة.xlsx"


def tender_sheet(language: str = "ar") -> dict:
    v = tiny_sheet(language=language)
    v["sources"]["s1"] = {
        "kind": "boq",
        "title": BOQ,
        "file_name": BOQ,
        "locator": {"sheet": "المقايسة", "row": 40, "column": "E", "dated_how": "received"},
        "url": None,
        "dated": "2026-11-05",
    }
    v["sources"]["s2"]["title"] = "quantity * rate"
    row = v["rows"][1]
    row["cells"]["amount"] = {
        "number_id": "n2", "source": "s2", "dated": "2026-11-05", "calculated": True,
        "value": "4.98", "currency": "EGP",
    }  # fmt: skip
    return v


def source_rows(v: dict) -> list[tuple]:
    ws = openpyxl.load_workbook(io.BytesIO(to_xlsx(v))).worksheets[1]
    return [tuple(c for c in r) for r in ws.iter_rows(min_row=2)]


def test_formulas_read_in_words():
    assert formula_words("quantity * rate", "ar") == "الكمية × الفئة"
    assert formula_words("sum(amount)", "ar") == "مجموع الإجمالي"
    assert formula_words("quantity * rate", "en") == "Quantity × Rate"
    assert formula_words("sum(amount)", "en") == "Sum of Amount"


def test_the_sources_sheet_is_in_plain_words():
    rows = source_rows(tender_sheet())
    values = [[c.value for c in r] for r in rows]
    text = " ".join(str(x) for r in values for x in r if x is not None)
    for raw in ("dated_how", "column", "boq", "quantity", "sum("):
        assert raw not in text
    qty = next(r for r in values if r[1] == "الكمية")
    assert qty[6] == "ورقة المقايسة، صف 40، عمود E"
    assert qty[8] == "2026-11-01 (تاريخ الاستلام)" and qty[9] == "مقايسة"
    assert qty[4] is None and qty[5] == BOQ  # the file is named once
    amount = next(r for r in values if r[1] == "الإجمالي")
    assert amount[4] == "الكمية × الفئة" and amount[9] == "محرك الحسابات"


def test_every_source_cell_stays_in_its_column():
    for row in source_rows(tender_sheet()):
        assert all(c.alignment.wrap_text for c in row)


def test_the_pdf_opens_with_a_header_block():
    v = tender_sheet() | {"head": {"project": "مدرسة - عينة", "client": "هيئة - عينة",
                                   "date": "2026-11-05"}}  # fmt: skip
    pdf = pypdfium2.PdfDocument(to_pdf(v))
    try:
        first = pdf[0].get_textpage().get_text_range()
    finally:
        pdf.close()
    assert "مدرسة - عينة" in first and "هيئة - عينة" in first and "2026-11-05" in first
    assert "ONE" in first and "باستخدام" in first
    for raw in ("dated_how", "quantity"):
        assert raw not in first


def test_the_export_route_fills_the_header_from_the_project(rec, monkeypatch):
    from qsone.deliverables import api
    from tests.samples import sample_sheet

    monkeypatch.setattr(api, "_cairo_today", lambda: "2026-11-05")
    d = sample_sheet(rec)
    v = api._with_head(rec, api.current_view(rec, d))
    assert v["head"] == {"project": "مشروع - عينة", "date": "2026-11-05"}  # no client fact yet
    pdf = pypdfium2.PdfDocument(api._export(rec, d, "pdf", None).body)
    try:
        assert "مشروع - عينة" in pdf[0].get_textpage().get_text_range()
    finally:
        pdf.close()
