"""Exports: Excel, Word and PDF built in memory from a Deliverable's view (synthetic «عينة» data
only). They read the view and never compute a number."""

import copy as deep
import io
import re
import zipfile
from decimal import Decimal
from string import Formatter

import docx
import openpyxl
import pypdfium2
import pytest
from docx.oxml.ns import qn

import qsone.calc.engine
import qsone.export
from qsone import copy
from qsone.deliverables.store import create, view
from qsone.export import file_name, format_decimal, review_pdf, to_docx, to_pdf, to_xlsx
from qsone.records.project import RecordsError
from tests.samples import SAMPLE_ACTOR, sample_document, sample_sheet

# Helpers ------------------------------------------------------------------------------------


def numbers_in(v: dict) -> list[str]:
    """Every number cell and the total in a Sheet view, as the view holds them."""
    out = [c["value"] for r in v["rows"] for c in r["cells"].values() if "value" in c]
    return out + ([v["total"]["value"]] if v["total"] else [])


def row_by_code(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def signed_off(v: dict, no: int = 2) -> dict:
    """The view as a signed-off Revision's snapshot reads (Task 4 makes the real one)."""
    return v | {"status": "signed_off", "revision": {"no": no, "version": 1, "signed_off": True}}


def pdf_text(data: bytes) -> str:
    pdf = pypdfium2.PdfDocument(data)
    try:
        return "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
    finally:
        pdf.close()


def sheet_xml(data: bytes, n: int = 1) -> str:
    return zipfile.ZipFile(io.BytesIO(data)).read(f"xl/worksheets/sheet{n}.xml").decode()


def tiny_sheet(**over) -> dict:
    """A hand-made English Sheet view: one section with 0.125 and 39850.50, one empty section."""
    num = {"number_id": "n", "source": "s1", "dated": "2026-11-01", "calculated": False}
    columns = [
        {"key": "code", "label": {"en": "Item", "ar": "البند"}, "kind": "text", "frozen": True},
        {"key": "description", "label": {"en": "Description", "ar": "بيان الأعمال"}},
        {"key": "quantity", "label": {"en": "Qty", "ar": "الكمية"}, "kind": "number"},
        {"key": "rate", "label": {"en": "Rate", "ar": "الفئة"}, "kind": "number"},
        {"key": "amount", "label": {"en": "Amount", "ar": "الإجمالي"}, "kind": "calc"},
    ]
    for c in columns:
        c.setdefault("kind", "text")
        c |= {"edit": False, "frozen": c.get("frozen", False), "wrap": False, "width": 90}
    v = {
        "id": "d1",
        "kind": "sheet",
        "variant": "boq",
        "title": "Sample BOQ",
        "language": "en",
        "status": "draft",
        "revision": None,
        "sample": True,
        "columns": columns,
        "rows": [
            {
                "id": "p1",
                "kind": "section",
                "level": 1,
                "title": "Earthworks - sample",
                "cells": {},
            },
            {
                "id": "p2",
                "kind": "item",
                "code": "1-1",
                "cells": {
                    "code": {"text": "1-1"},
                    "description": {"text": "Excavation - sample"},
                    "quantity": num | {"value": "0.125", "unit": "m3"},
                    "rate": num | {"value": "39850.50", "unit": "m3", "currency": "EGP"},
                },
            },
            {"id": "p3", "kind": "section", "level": 1, "title": "Empty - sample", "cells": {}},
        ],
        "total": None,
        "sources": {
            "s1": {
                "kind": "sample",
                "title": "Sample prices",
                "file_name": "prices - sample.pdf",
                "locator": {"page": 3},
                "url": "https://example.com/sample",
                "dated": "2026-11-01",
            },
            "s2": {
                "kind": "calculation",
                "title": "sum(amount)",
                "file_name": None,
                "locator": {"calculation": "c1"},
                "url": None,
                "dated": "2026-11-01",
            },
        },
    }
    return v | over


def sample_report(**over) -> dict:
    """A hand-made Review report in the shape Task 4's `review.review_report` returns."""
    report = {
        "deliverable": {
            "id": "d1",
            "kind": "sheet",
            "title": "جدول الكميات - عينة",
            "language": "ar",
        },
        "revision": {
            "no": 1,
            "version_n": 3,
            "issued_at": "2026-11-05T09:00:00.000000+00:00",
            "issued_by": "engineer",
            "signed_off": True,
        },
        "checks": [
            {
                "id": "k1",
                "version_n": 2,
                "code": "C",
                "checker": "model-x - sample",
                "same_provider": False,
                "summary": "الفئة ناقصة - عينة",
                "at": "2026-11-05T08:00:00.000000+00:00",
            },
            {
                "id": "k2",
                "version_n": 3,
                "code": "B",
                "checker": "model-x - sample",
                "same_provider": True,
                "summary": None,
                "at": "2026-11-05T08:30:00.000000+00:00",
            },
        ],
        "threads": [
            {
                "id": "c1",
                "kind": "review",
                "code": "C",
                "status": "closed",
                "author": "checking_qs",
                "body": "راجع فئة البند 03/02 - عينة",
                "anchor": {"type": "deliverable"},
                "created_at": "2026-11-05T08:00:00.000000+00:00",
                "replies": [
                    {
                        "id": "c2",
                        "body": "اتعدلت - عينة",
                        "author": "engineer",
                        "created_at": "2026-11-05T08:10:00.000000+00:00",
                    }
                ],
            },
            {
                "id": "c3",
                "kind": "note",
                "code": None,
                "status": "open",
                "author": "lead_qs",
                "body": "السعر من عرض المورّد - عينة",
                "anchor": {"type": "deliverable"},
                "created_at": "2026-11-05T07:00:00.000000+00:00",
                "replies": [],
            },
        ],
        "changes": {"accepted": 4, "rejected": 1},
        "signed_off": {"by": "engineer", "at": "2026-11-05T09:00:00.000000+00:00"},
        "sample": True,
    }
    return report | over


# Numbers are written as the view holds them ------------------------------------------------


def test_format_decimal_groups_and_never_rounds():
    assert format_decimal("4782060.00", 2) == "4,782,060.00"
    assert format_decimal("14", 2) == "14.00"
    assert format_decimal("0.125", 2) == "0.125"  # more places than asked: all kept
    assert format_decimal("120") == "120"
    assert format_decimal("-1234.5", 2) == "-1,234.50"
    assert format_decimal("39850.50", 0) == "39,850.50"
    with pytest.raises(ValueError):
        format_decimal("1e3")


def test_founder_switches(rec, monkeypatch):
    monkeypatch.setattr(qsone.export, "WESTERN_DIGITS", False)
    assert format_decimal("39850.50", 2, "ar") == "٣٩٬٨٥٠٫٥٠"
    assert format_decimal("39850.50", 2, "en") == "39,850.50"
    monkeypatch.setattr(qsone.export, "DRAFT_EXPORTS", False)
    with pytest.raises(RecordsError) as e:
        to_xlsx(tiny_sheet())
    assert e.value.text == copy.EXPORT_LABELS["needs_signoff"]
    assert to_xlsx(signed_off(tiny_sheet()))


def test_xlsx_writes_the_views_numbers_exactly_rtl_with_sources(rec):
    v = view(rec, sample_sheet(rec))
    wb = openpyxl.load_workbook(io.BytesIO(to_xlsx(v)))
    ws = wb.worksheets[0]
    assert ws.sheet_view.rightToLeft and ws.freeze_panes
    shown = [c.value for row in ws.iter_rows() for c in row if isinstance(c.value, int | float)]
    assert sorted(Decimal(str(x)) for x in shown) == sorted(Decimal(x) for x in numbers_in(v))
    assert wb.worksheets[1].title == copy.SOURCES_SHEET["ar"]
    assert ws["A1"].value.endswith(copy.SAMPLE_DATA["ar"])
    assert copy.EXPORT_DRAFT_MARK["ar"] in ws["A1"].value
    assert [c.value for c in ws[2]][:2] == ["البند", "بيان الأعمال"]  # labels in Arabic
    assert ws.title == v["title"]


def test_xlsx_xml_holds_exact_text(rec):
    v = view(rec, sample_sheet(rec))
    xml = sheet_xml(to_xlsx(v))
    assert "<v>39850.50</v>" in xml and "<v>4782060.00</v>" in xml
    assert not re.search(r"<v>\d+\.\d*9999", xml)


def test_xlsx_small_and_long_decimals_survive():
    data = to_xlsx(tiny_sheet())
    assert "<v>0.125</v>" in sheet_xml(data) and "<v>39850.50</v>" in sheet_xml(data)
    ws = openpyxl.load_workbook(io.BytesIO(data)).worksheets[0]
    assert {
        Decimal(str(c.value)) for row in ws.iter_rows() for c in row if isinstance(c.value, float)
    } == {Decimal("0.125"), Decimal("39850.50")}
    assert not ws.sheet_view.rightToLeft  # an English Deliverable reads left to right


def test_xlsx_number_formats_show_every_stored_decimal(rec):
    ws = openpyxl.load_workbook(io.BytesIO(to_xlsx(tiny_sheet()))).worksheets[0]
    formats = {
        c.value: c.number_format
        for row in ws.iter_rows()
        for c in row
        if isinstance(c.value, float)
    }
    assert formats == {0.125: "#,##0.000", 39850.5: "#,##0.00"}


def test_xlsx_empty_section_and_missing_amount_show_a_dash(rec):
    v = view(rec, sample_sheet(rec, with_rate_only=True))
    ws = openpyxl.load_workbook(io.BytesIO(to_xlsx(v))).worksheets[0]
    rate_only = next(r for r in ws.iter_rows() if r[0].value == "2-4")
    assert rate_only[-1].value == "—" and rate_only[3].value == "فئة فقط"
    ws = openpyxl.load_workbook(io.BytesIO(to_xlsx(tiny_sheet()))).worksheets[0]
    empty = next(r for r in ws.iter_rows() if r[0].value == "Empty - sample")
    assert empty[-1].value == "—"
    assert not any(c.value == 0 for row in ws.iter_rows() for c in row)  # never an invented 0


def test_xlsx_sources_sheet_has_every_number_with_its_source_and_date(rec):
    v = view(rec, sample_sheet(rec))
    wb = openpyxl.load_workbook(io.BytesIO(to_xlsx(v)))
    src = wb.worksheets[1]
    assert src.sheet_view.rightToLeft
    rows = list(src.iter_rows(min_row=2, values_only=True))
    assert len(rows) == len(numbers_in(v))
    rate = next(r for r in rows if r[0] == "03/02" and r[1] == "الفئة")
    assert Decimal(str(rate[2])) == Decimal("39850.50") and rate[3] == "EGP"
    assert "بيانات تجريبية - عينة" in rate and "2026-11-01" in rate
    total = rows[-1]
    assert total[0] == copy.EXPORT_LABELS["total"]["ar"] and "مجموع الإجمالي" in total
    english = openpyxl.load_workbook(io.BytesIO(to_xlsx(tiny_sheet()))).worksheets[1]
    line = next(english.iter_rows(min_row=2, values_only=True))
    assert {"prices - sample.pdf", "https://example.com/sample", "page 3"} <= set(line)


def test_xlsx_text_from_a_tender_file_never_becomes_a_formula(rec):
    v = deep.deepcopy(view(rec, sample_sheet(rec)))
    row_by_code(v, "03/02")["cells"]["description"] = {"text": '=HYPERLINK("http://x","عينة")'}
    data = to_xlsx(v)
    assert "<f>" not in sheet_xml(data)
    ws = openpyxl.load_workbook(io.BytesIO(data)).worksheets[0]
    assert next(r for r in ws.iter_rows() if r[0].value == "03/02")[1].data_type == "s"


def test_xlsx_sheet_name_is_cut_and_cleaned():
    v = tiny_sheet(title="BOQ [phase 1]: block*A / tower? \\ west wing - sample long")
    ws = openpyxl.load_workbook(io.BytesIO(to_xlsx(v))).worksheets[0]
    assert len(ws.title) <= 31 and not set(ws.title) & set("[]:*?/\\")


# Word ---------------------------------------------------------------------------------------


def test_docx_is_rtl_and_keeps_tanween(rec):
    d = docx.Document(io.BytesIO(to_docx(view(rec, sample_document(rec, sample_sheet(rec))))))
    p = next(p for p in d.paragraphs if "حالياً" in p.text)
    assert p._p.pPr.find(qn("w:bidi")) is not None and "حالياً لمدة" in p.text
    run = p.runs[0]._r.rPr
    assert run.find(qn("w:rtl")) is not None and run.find(qn("w:cs")) is not None
    assert run.find(qn("w:rFonts")).get(qn("w:cs")) == "Arial"
    assert run.find(qn("w:lang")).get(qn("w:bidi")) == "ar-EG"
    assert all(p._p.pPr.find(qn("w:bidi")) is not None for p in d.paragraphs)


def test_docx_refs_show_their_value_and_every_source_stays_visible(rec):
    v = view(rec, sample_document(rec, sample_sheet(rec)))
    d = docx.Document(io.BytesIO(to_docx(v)))
    text = "\n".join(p.text for p in d.paragraphs)
    assert "بإجمالي 5,182,755.00[1]" in text  # the grand total, formatted, with its note mark
    assert copy.EXPORT_LABELS["sources"]["ar"] in text
    [sources] = d.tables
    assert [c.text for c in sources.rows[1].cells][:4] == [
        "[1]",
        "5,182,755.00",
        "EGP",
        "مجموع الإجمالي",
    ]
    assert "2026-11-01" in [c.text for c in sources.rows[1].cells]
    assert sources._tbl.tblPr.find(qn("w:bidiVisual")) is not None
    header = "\n".join(p.text for p in d.sections[0].header.paragraphs)
    assert copy.EXPORT_DRAFT_MARK["ar"] in header and copy.SAMPLE_DATA["ar"] in header


def test_docx_headings_lists_and_tables(rec):
    blocks = [
        {"type": "h2", "children": [{"text": "الشروط - عينة", "bold": True}]},
        {
            "type": "ul",
            "children": [
                {"type": "li", "children": [{"text": "البند الأول - عينة"}]},
                {"type": "li", "children": [{"text": "البند الثاني - عينة", "italic": True}]},
            ],
        },
        {
            "type": "table",
            "children": [
                {
                    "type": "tr",
                    "children": [
                        {
                            "type": "td",
                            "children": [{"type": "p", "children": [{"text": "الكمية"}]}],
                        },
                        {
                            "type": "td",
                            "children": [{"type": "p", "children": [{"text": "120 m³"}]}],
                        },
                    ],
                },
            ],
        },
    ]
    d = create(
        rec,
        kind="document",
        variant="letter",
        title="شروط - عينة",
        language="ar",
        actor=SAMPLE_ACTOR,
        blocks=blocks,
    )
    out = docx.Document(io.BytesIO(to_docx(view(rec, d))))
    styles = [p.style.name for p in out.paragraphs if p.text]
    assert styles[:3] == ["Heading 2", "List Bullet", "List Bullet"]
    assert out.paragraphs[2].runs[0].italic and out.paragraphs[0].runs[0].bold
    [table] = out.tables
    assert table.cell(0, 1).text == "120 m³"
    assert table._tbl.tblPr.find(qn("w:bidiVisual")) is not None


def test_docx_english_is_left_to_right():
    v = {
        "id": "d",
        "kind": "document",
        "title": "Letter - sample",
        "language": "en",
        "status": "draft",
        "revision": None,
        "sample": False,
        "refs": {},
        "sources": {},
        "blocks": [
            {
                "id": "b",
                "version": 1,
                "node": {"type": "p", "children": [{"text": "Dear sir - sample"}]},
            }
        ],
    }
    d = docx.Document(io.BytesIO(to_docx(v)))
    p = next(p for p in d.paragraphs if p.text == "Dear sir - sample")
    assert p._p.pPr is None or p._p.pPr.find(qn("w:bidi")) is None


# PDF ----------------------------------------------------------------------------------------


def test_pdf_arabic_comes_back_in_reading_order(rec):
    text = pdf_text(to_pdf(view(rec, sample_sheet(rec))))
    assert "أعمال الحفر" in text and "03/02" in text and "بيانات تجريبية" in text
    assert "4,782,060.00" in text and copy.EXPORT_DRAFT_MARK["ar"] in text


def test_pdf_sheet_is_right_to_left(rec):
    pdf = pypdfium2.PdfDocument(to_pdf(view(rec, sample_sheet(rec))))
    try:
        page = pdf[0].get_textpage()

        def x_of(needle: str) -> float:
            found = page.search(needle).get_next()
            return page.get_charbox(found[0])[0]

        assert x_of("03/02") > x_of("4,782,060.00")  # the code column sits on the right
    finally:
        pdf.close()


def test_pdf_marks_every_page_and_lists_the_sources(rec):
    v = view(rec, sample_sheet(rec, rows=80))
    pdf = pypdfium2.PdfDocument(to_pdf(v))
    try:
        pages = [pdf[i].get_textpage().get_text_range() for i in range(len(pdf))]
    finally:
        pdf.close()
    assert len(pages) > 2
    assert all(copy.EXPORT_DRAFT_MARK["ar"] in p and copy.SAMPLE_DATA["ar"] in p for p in pages)
    assert all(v["title"] in p for p in pages)
    assert sum("الوحدة" in p for p in pages) >= 2  # the header row repeats on every table page
    text = "\n".join(pages)
    assert (
        copy.EXPORT_LABELS["sources"]["ar"] in text and "محرك الحسابات" in text and "مجموع" in text
    )


def test_pdf_payload_cannot_inject_typst(rec):
    v = view(rec, sample_sheet(rec))
    v = deep.deepcopy(v)
    evil = '#import "x": *  ]) #panic()'
    row_by_code(v, "03/02")["cells"]["description"] = {"text": evil}
    text = pdf_text(to_pdf(v))  # it compiles, so nothing ran
    assert "panic" in text and "import" in text


def test_document_pdf_has_its_refs_and_their_sources(rec):
    v = view(rec, sample_document(rec, sample_sheet(rec)))
    text = pdf_text(to_pdf(v))
    assert "5,182,755.00" in text and "مجموع" in text and "2026-11-01" in text
    assert "الأسعار سارية" in text or "ألسعار سارية" in text  # pdfium splits lam-alef
    assert copy.EXPORT_DRAFT_MARK["ar"] in text


def test_signed_off_export_has_no_draft_mark(rec):
    v = signed_off(view(rec, sample_sheet(rec)))
    a1 = openpyxl.load_workbook(io.BytesIO(to_xlsx(v))).worksheets[0]["A1"].value
    assert copy.EXPORT_DRAFT_MARK["ar"] not in a1 and copy.SAMPLE_DATA["ar"] in a1
    text = pdf_text(to_pdf(v))
    assert copy.EXPORT_DRAFT_MARK["ar"] not in text and "إصدار 2" in text
    doc = signed_off(view(rec, sample_document(rec, sample_sheet(rec))))
    header = docx.Document(io.BytesIO(to_docx(doc))).sections[0].header.paragraphs
    assert copy.EXPORT_DRAFT_MARK["ar"] not in "".join(p.text for p in header)


def test_exports_never_call_the_calc_engine(rec, monkeypatch):
    sheet = sample_sheet(rec)
    sv, dv = view(rec, sheet), view(rec, sample_document(rec, sheet))
    monkeypatch.setattr(qsone.calc.engine, "calculate", lambda *a, **k: pytest.fail("computed"))
    assert to_xlsx(sv) and to_pdf(sv) and to_docx(dv) and to_pdf(dv)


def test_wrong_kind_is_refused():
    with pytest.raises(ValueError):
        to_docx(tiny_sheet())
    with pytest.raises(ValueError):
        to_xlsx({"kind": "document"})


# File names and the Review report ------------------------------------------------------------


def test_file_names_are_safe():
    v = tiny_sheet(title='BOQ: "phase/1"', language="ar")
    assert file_name(v, "xlsx") == "BOQ phase 1 - مسودة.xlsx"
    assert file_name(signed_off(v), "pdf") == "BOQ phase 1 - إصدار 2.pdf"
    assert file_name(tiny_sheet(), "xlsx") == "Sample BOQ - Draft.xlsx"
    assert file_name(signed_off(tiny_sheet()), "docx") == "Sample BOQ - Rev 2.docx"
    assert file_name(tiny_sheet(title="<>|?*. \x07"), "pdf") == "Deliverable - Draft.pdf"
    assert file_name(tiny_sheet(title="report. "), "pdf") == "report - Draft.pdf"
    assert len(file_name(tiny_sheet(title="ب" * 400), "xlsx")) < 140


def test_review_report_pdf_builds():
    text = pdf_text(review_pdf(sample_report(), "ar"))
    assert "جدول الكميات - عينة" in text and "إصدار 1" in text
    assert "راجع فئة البند 03/02 - عينة" in text and "اتعدلت - عينة" in text
    assert "model" in text and copy.SAMPLE_DATA["ar"] in text  # pdfium reverses Latin runs
    assert "2026-11-05" in text  # isolated, so the date is not read as 05-11-2026
    assert copy.EXPORT_DRAFT_MARK["ar"] not in text
    english = pdf_text(review_pdf(sample_report(signed_off=None), "en"))
    assert copy.EXPORT_DRAFT_MARK["en"] in english and "Code C" in english
    assert "model-x - sample" in english and "2026-11-05 08:00 UTC" in english


def test_review_pdf_reads_the_real_review_report(rec):
    from qsone.deliverables import comments, review

    d = sample_sheet(rec)
    review.record_check(
        rec, d, version_n=1, code="B", checker="model-x - sample", same_provider=True,
        summary="الفئات سليمة - عينة",
        comments=[{"anchor": {"type": "deliverable"}, "body": "راجع 03/02 - عينة", "code": "B"}],
    )  # fmt: skip
    [thread] = comments.list_comments(rec, d)
    comments.reply(rec, thread["id"], body="اتراجع - عينة", actor="engineer")
    comments.close(rec, thread["id"], actor="engineer")
    no = review.sign_off(rec, d, actor="engineer")
    report = review.review_report(rec, d, no)
    text = pdf_text(review_pdf(report, "ar"))
    for part in ("جدول الكميات - عينة", "إصدار 1", "راجع 03/02 - عينة", "اتراجع - عينة"):
        assert part in text, part
    assert "الفئات سليمة - عينة" in text and copy.SAMPLE_DATA["ar"] in text
    assert copy.EXPORT_DRAFT_MARK["ar"] not in text  # signed off
    english = pdf_text(review_pdf(report, "en"))
    assert "Code B" in english and "Same-provider check" in english and "Closed" in english


def test_export_labels_have_both_languages():
    """The exports' labels live in copy.py with every other text the engineer reads."""
    assert not hasattr(qsone.export, "LABELS")
    for name, text in copy.EXPORT_LABELS.items():
        assert set(text) == {"en", "ar"} and all(v.strip() for v in text.values()), name
        fields = [{f for _, f, _, _ in Formatter().parse(v) if f} for v in text.values()]
        assert fields[0] == fields[1], name
    assert qsone.export.say("rev", "ar", n=2) == "إصدار 2"
