"""Synthetic PDF BOQs; Typst renders complete Arabic runs, never separate letters."""

import io
import json

import pdfplumber
import pytest

from qsone.clientfile import imported
from qsone.records import boq
from qsone.records.files import add_file
from qsone.tools import boq as boq_tools  # noqa: F401
from tests.fakes_tools import tool_ctx


def pdf(ar=False, multipage=False):
    typst = pytest.importorskip("typst")
    header = (
        ["البند", "الوصف", "الوحدة", "الكمية", "الفئة", "الإجمالي"]
        if ar
        else ["Item", "Description", "Unit", "Quantity", "Rate", "Amount"]
    )
    description = "خرسانة مسلحة" if ar else "Concrete sample"
    section = "أعمال خرسانة" if ar else "Concrete works sample"
    carried = "مرحل" if ar else "Carried forward"

    def table(rows):
        return (
            "#table(columns: (45pt, 170pt, 45pt, 70pt, 70pt, 80pt), inset: 6pt, "
            + ", ".join("[" + cell + "]" for row in [header, *rows] for cell in row)
            + ")"
        )

    source = "#set page(width: 650pt, height: 500pt, margin: 30pt)\n"
    source += '#set text(font: "DejaVu Sans", size: 10pt)\n'
    source += table(
        [
            ["", section, "", "", "", ""],
            ["1", description, "m3", "١٢٫٥٠" if ar else "12.50", "20.00", "250.00"],
            ["", carried, "", "", "", "250.00"],
        ]
    )
    if multipage:
        source += "\n#pagebreak()\n" + table([["2", description, "m3", "2.00", "30.00", "60.00"]])
    return typst.compile(source.encode())


@pytest.mark.parametrize("ar", [False, True])
def test_pdf_import_and_cell_sources(rec, ar):
    data = pdf(ar, multipage=True)
    f = add_file(rec, "BOQ sample.pdf", data, actor="engineer").id
    book = boq.workbook(rec, f)
    names, sheet = boq.read(book, None)
    assert len(names) == 1
    header, columns = boq.guess(sheet, sheet.last_row)
    assert set(columns) == set(boq.FIELDS) - {"description_2"}
    assert sheet.last_row == 5  # repeated page header removed
    for row in sheet.cells.values():
        for cell in row.values():
            assert cell.locator["page"] in (1, 2)
            x0, y0, x1, y1 = cell.locator["box"]
            assert 0 <= x0 < x1 <= 650 and 0 <= y0 < y1 <= 500
    with pdfplumber.open(io.BytesIO(data)) as original:
        cell = sheet.cells[5][4]
        region = original.pages[1].crop(tuple(cell.locator["box"]))
        assert region.extract_text() == "2.00"
    ctx = tool_ctx(
        rec, answers={"rows": json.dumps({"choice": "keep", "answers": {}, "rows_ok": []})}
    )
    args = boq_tools.ImportArgs(
        file_id=f, sheet=sheet.name, header_row=header, columns=columns, currency="EGP"
    )
    plan = boq.plan_sheet(rec, book, sheet, header_row=header, columns=columns)
    assert plan.items == 2 and plan.headings == 2
    boq_tools._write(ctx, rec, args, plan)
    view = imported.sheet(rec, f)
    assert len(view["rows"]) == 4
    first, second = [r for r in view["rows"] if r["kind"] == "item"]
    assert first["cells"]["description"]["text"] == ("خرسانة مسلحة" if ar else "Concrete sample")
    for row, values, page in [
        (first, ["12.50", "20.00", "250.00"], 1),
        (second, ["2.00", "30.00", "60.00"], 2),
    ]:
        for field, value in zip(boq.NUMBERS, values, strict=True):
            cell = row["cells"][field]
            assert cell["value"] == value
            source = view["sources"][cell["source"]]
            assert source["file_id"] == f
            assert source["locator"]["page"] == page
            assert len(source["locator"]["box"]) == 4


def test_scan_reports_needs_reading(rec):
    typst = pytest.importorskip("typst")
    data = typst.compile(b"#rect(width: 100pt, height: 100pt)")
    f = add_file(rec, "scan sample.pdf", data, actor="engineer").id
    from qsone import copy
    from qsone.records.project import RecordsError

    with pytest.raises(RecordsError) as error:
        boq.preview(rec, f, None)
    assert error.value.text == copy.BOQ_SCAN_NEEDS_READING
    assert "files_read" in error.value.text["en"]
    assert "ocr=true" in error.value.text["ar"]


def test_source_ref_keeps_pdf_box():
    from qsone.tools.cite import SourceRef, source_line

    ref = SourceRef(
        ref="file:f#page=2",
        title="sample",
        read="2026-11-06",
        locator={"page": 2, "box": [1.25, 2.5, 30.75, 40.0]},
    )
    assert '"box": [1.25, 2.5, 30.75, 40.0]' in source_line(ref)


@pytest.mark.parametrize(
    "box", [[0, 0, 1], [0, 0, float("nan"), 1], [2, 0, 1, 1], [False, 0, 1, 1]]
)
def test_invalid_box_rejected(box):
    from qsone.engine.tools_records import _place
    from qsone.records.project import RecordsError

    with pytest.raises(RecordsError):
        _place({"page": 1, "box": box})


def test_mixed_pdf_reports_unread_pages(rec):
    typst = pytest.importorskip("typst")
    # Append a blank page to a real table without introducing an OCR dependency.
    import pypdfium2 as pdfium

    original = pdfium.PdfDocument(pdf())
    blank = pdfium.PdfDocument(typst.compile(b"#rect(width: 100pt, height: 100pt)"))
    original.import_pages(blank)
    out = io.BytesIO()
    original.save(out)
    original.close()
    blank.close()
    f = add_file(rec, "mixed sample.pdf", out.getvalue(), actor="engineer").id
    assert boq.preview(rec, f, None)["needs_reading"] == [2]


def test_merged_section_uses_excel_merge_rules(rec):
    typst = pytest.importorskip("typst")
    source = """#set page(width: 600pt, margin: 20pt)
#table(columns: (40pt, 180pt, 40pt, 70pt),
[Item], [Description], [Unit], [Quantity],
table.cell(colspan: 4)[Concrete works sample],
[1], [Concrete sample], [m3], [12.50])"""
    f = add_file(rec, "merged sample.pdf", typst.compile(source.encode()), actor="engineer").id
    book = boq.workbook(rec, f)
    _, sheet = boq.read(book, None)
    header, columns = boq.guess(sheet, sheet.last_row)
    plan = boq.plan_sheet(rec, book, sheet, header_row=header, columns=columns)
    assert plan.headings == 1
    assert plan.rows[0].description == "Concrete works sample"


def test_borderless_table_uses_same_columns(rec):
    typst = pytest.importorskip("typst")
    source = """#set page(width: 600pt, margin: 20pt)
#table(stroke: none, columns: (40pt, 180pt, 50pt, 80pt),
[Item], [Description], [Unit], [Quantity],
[1], [Concrete sample], [m3], [12.50],
[2], [Masonry sample], [m2], [20.00])"""
    f = add_file(rec, "borderless sample.pdf", typst.compile(source.encode()), actor="engineer").id
    preview = boq.preview(rec, f, None)
    assert preview["overview"]["items"] == 2
    assert preview["columns_guess"] == {
        "code": "A",
        "description": "B",
        "unit": "C",
        "quantity": "D",
    }


def test_bilingual_cell_preserves_english_word_order():
    typst = pytest.importorskip("typst")
    from qsone.records.boq_pdf import cell_text

    data = typst.compile('#set text(font: "DejaVu Sans")\nخرسانة مسلحة Concrete sample'.encode())
    with pdfplumber.open(io.BytesIO(data)) as doc:
        text = cell_text(doc.pages[0].chars)
    assert "خرسانة مسلحة" in text
    assert "Concrete sample" in text


def test_continuation_without_header_and_small_page_offset(rec):
    typst = pytest.importorskip("typst")
    source = """#set page(width: 600pt, margin: 20pt)
#table(columns: (40pt, 180pt, 40pt, 70pt),
[Item], [Description], [Unit], [Quantity],
[1], [Concrete sample], [m3], [12.50])
#pagebreak()
#pad(left: 0.5pt)[
#table(columns: (40pt, 180pt, 40pt, 70pt),
[2], [Masonry sample], [m2], [20.00])]
"""
    f = add_file(rec, "continued sample.pdf", typst.compile(source.encode()), actor="engineer").id
    preview = boq.preview(rec, f, None)
    assert len(preview["sheets"]) == 1
    assert preview["overview"]["items"] == 2


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1,250.00", "1250.00"),
        ("١٬٢٥٠٫٥٠", "1250.50"),
        ("1 250,50", "1250.50"),
        ("1.250,50", "1250.50"),
    ],
)
def test_grouped_pdf_rate_and_amount_import(rec, text, expected):
    typst = pytest.importorskip("typst")
    source = "#set page(width: 650pt, height: 500pt, margin: 30pt)\n"
    source += '#set text(font: "DejaVu Sans", size: 10pt)\n'
    cells = [
        "Item",
        "Description",
        "Unit",
        "Quantity",
        "Rate",
        "Amount",
        "1",
        "Concrete sample",
        "m3",
        "1",
        text,
        text,
    ]
    source += "#table(columns: (45pt,170pt,45pt,70pt,70pt,80pt), inset: 6pt, "
    source += ", ".join("[" + c + "]" for c in cells) + ")"
    f = add_file(rec, "Grouped sample.pdf", typst.compile(source.encode()), actor="engineer").id
    preview = boq.preview(rec, f, None)
    p = boq.plan(
        rec,
        f,
        sheet=preview["sheet"],
        header_row=preview["header_guess"],
        columns=preview["columns_guess"],
    )
    ctx = tool_ctx(rec)
    args = boq_tools.ImportArgs(
        file_id=f, sheet=p.sheet, header_row=p.header_row, columns=p.columns, currency="EGP"
    )
    boq_tools._write(ctx, rec, args, p)
    row = imported.sheet(rec, f)["rows"][0]
    assert row["cells"]["rate"]["value"] == expected
    assert row["cells"]["amount"]["value"] == expected


@pytest.mark.parametrize("unit", ["م3", "م.ط", "كجم/سم2"])
def test_arabic_units_stay_whole(unit):
    import typst

    from qsone.records.boq_pdf import cell_text

    data = typst.compile(('#set text(font: "DejaVu Sans")\n' + unit).encode())
    with pdfplumber.open(io.BytesIO(data)) as doc:
        assert cell_text(doc.pages[0].chars) == unit


def test_cropbox_number_matches_regions(rec):
    import typst
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import RectangleObject

    from qsone.records import boq_pdf, regions

    data = typst.compile(
        b"#set page(width: 420pt, height: 200pt, margin: 30pt)\n"
        b"#table(columns: (50pt, 150pt, 80pt), [Item], [Description], "
        b"[Quantity], [1], [Sample], [12.50])"
    )
    writer = PdfWriter()
    page = writer.add_page(PdfReader(io.BytesIO(data)).pages[0])
    page.cropbox = RectangleObject([20, 0, 400, 180])
    out = io.BytesIO()
    writer.write(out)
    fid = add_file(rec, "cropped sample.pdf", out.getvalue(), actor="engineer").id
    sheets, _ = boq_pdf.sheets(out.getvalue())
    number = next(c for row in sheets[0].cells.values() for c in row.values() if c.value == "12.50")
    assert number.locator["box"] == pytest.approx(
        regions.page_boxes(rec, fid, 1, "12.50")["boxes"][0], abs=0.01
    )


@pytest.mark.parametrize("ruled", [True, False])
def test_scanned_table_reads_stored_ocr_words(rec, ruled):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject, RectangleObject

    from qsone.records import boq_pdf
    from qsone.records.extract import Piece
    from qsone.records.files import add_ocr_pages

    writer = PdfWriter()
    page = writer.add_blank_page(420, 180)
    page.cropbox = RectangleObject([20, 0, 400, 180])
    stream = DecodedStreamObject()
    # A synthetic scan's table ruling, with no PDF text objects.
    commands = [f"{x} 70 m {x} 160 l S" for x in (30, 80, 240, 300, 390)]
    commands += [f"30 {y} m 390 {y} l S" for y in (70, 100, 130, 160)]
    stream.set_data("\n".join(commands if ruled else []).encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    file_id = add_file(rec, "Scanned sample.pdf", out.getvalue(), actor="engineer").id
    pieces = []
    for y, texts in (
        (25, ["Item", "Description", "Unit", "Quantity"]),
        (55, ["1", "Concrete", "م3", "12.50"]),
        (85, ["2", "Concrete", "م3", "20.00"]),
    ):
        for x, text in zip((15, 65, 225, 285), texts, strict=True):
            pieces.append(Piece({"page": 1, "box": [x, y, x + 40, y + 10]}, text))
    add_ocr_pages(rec, file_id, {1: pieces}, read_by="tesseract", actor="engineer")
    names, sheet = boq_pdf.read_stored(rec, file_id, "PDF 1.1")
    assert names == [("PDF 1.1", False)]
    row = next(row for row in sheet.cells.values() if row.get(4) and row[4].value == "12.50")
    assert row[3].value == "م3"
    # read from the page's picture on this computer: the number stays unchecked
    assert row[4].locator == {"page": 1, "box": [285, 55, 325, 65], "read_by": "tesseract"}
    header, columns = boq.guess(sheet, sheet.last_row)
    plan = boq.plan_sheet(
        rec, boq.workbook(rec, file_id), sheet, header_row=header, columns=columns
    )
    assert plan.items == 2
    assert sheet.needs_reading == []
    preview = boq.preview(rec, file_id, None)
    assert preview["overview"]["items"] == 2
    names, loaded = boq.read(boq.workbook(rec, file_id), None)
    assert loaded.cells == sheet.cells
    plan = boq.plan(
        rec,
        file_id,
        sheet=preview["sheet"],
        header_row=preview["header_guess"],
        columns=preview["columns_guess"],
    )
    args = boq_tools.ImportArgs(
        file_id=file_id, sheet=plan.sheet, header_row=plan.header_row, columns=plan.columns
    )
    from qsone.records.project import RecordsError

    with pytest.raises(RecordsError):  # numbers read here are unchecked until the AI reads them
        boq_tools._write(tool_ctx(rec), rec, args, plan)
    text = "Item Description Unit Quantity\n1 Concrete م3 12.50\n2 Concrete م3 20.00"
    add_ocr_pages(rec, file_id, {1: text}, read_by="sample-vision", actor="engineer")
    boq_tools._write(tool_ctx(rec), rec, args, plan)
    view = imported.sheet(rec, file_id)
    for row, value, y in zip(view["rows"], ("12.50", "20.00"), (55, 85), strict=True):
        cell = row["cells"]["quantity"]
        assert cell["value"] == value
        source = view["sources"][cell["source"]]
        assert source["file_id"] == file_id
        assert source["locator"]["page"] == 1
        assert source["locator"]["box"] == [285, y, 325, y + 10]
