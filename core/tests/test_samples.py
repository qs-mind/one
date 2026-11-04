"""The Plan 6 sample fixtures are what they say: sample numbers, and a client file like Excel's."""

import io
import zipfile

import openpyxl

from qsone.records import ledger
from tests.samples import (
    RATE_ONLY_NOTE,
    SAMPLE_TITLE,
    VBA_PROJECT,
    sample_boq_rows,
    sample_client_xlsx,
    sample_document_blocks,
    sample_source,
)


def items_by_code(rec, rows):
    out = {}
    with rec.read() as c:
        for r in rows:
            if "item_id" in r:
                code, fields = c.execute(
                    "select code, fields from items where id = ?", (r["item_id"],)
                ).fetchone()
                out[code] = (r["item_id"], fields)
    return out


def test_sample_boq_rows_hold_exact_sample_numbers(rec):
    rows = sample_boq_rows(rec)
    assert [r.get("section") for r in rows if "section" in r] == ["أعمال الحفر", "أعمال الخرسانة"]
    items = items_by_code(rec, rows)
    assert list(items) == ["1-1", "1-2", "2-1", "03/02", "2-3", "2-4"]
    numbers = {n.name: n for n in ledger.numbers(rec, items["03/02"][0])}
    assert (str(numbers["quantity"].value), numbers["quantity"].unit) == ("120", "m3")
    rate = numbers["rate"]
    assert (str(rate.value), rate.unit, rate.currency) == ("39850.50", "m3", "EGP")
    with rec.read() as c:
        kind, title = c.execute(
            "select kind, title from sources where id = ?", (rate.source_id,)
        ).fetchone()
    assert (kind, title) == ("sample", SAMPLE_TITLE)
    assert "ـ" in items["1-1"][1]  # tatweel kept
    rate_only = {n.name for n in ledger.numbers(rec, items["2-4"][0])}
    assert rate_only == {"rate"} and RATE_ONLY_NOTE in items["2-4"][1]
    assert {n.unit for n in ledger.numbers(rec, items["2-3"][0])} == {"م2"}


def test_more_rows_go_fifty_to_a_section_and_the_source_is_shared(rec):
    rows = sample_boq_rows(rec, 120)
    assert sum("item_id" in r for r in rows) == 120
    assert sum("section" in r for r in rows) == 2 + 3  # 114 extra items in sections of 50
    sample_boq_rows(rec, 2, with_rate_only=False)
    with rec.read() as c:
        assert c.execute("select count(*) from sources where kind = 'sample'").fetchone()[0] == 1
    assert sample_source(rec) == sample_source(rec)


def test_sample_document_has_one_untraced_run_of_digits():
    blocks = sample_document_blocks("d" * 32)
    assert [b["type"] for b in blocks] == ["h1", "p", "p", "p"]
    refs = [c for b in blocks for c in b["children"] if c.get("type") == "cell"]
    assert refs == [
        {
            "type": "cell",
            "deliverable": "d" * 32,
            "row": "total",
            "column": "amount",
            "children": [{"text": ""}],
        }
    ]
    text = "".join(c.get("text", "") for b in blocks for c in b["children"])
    assert [ch for ch in text if ch.isdigit()] == ["٣", "٠"]
    assert "الأسعار سارية حالياً لمدة ٣٠ يوماً" in text


def test_sample_client_xlsx_is_built_like_excel_and_opens():
    data = sample_client_xlsx()
    z = zipfile.ZipFile(io.BytesIO(data))
    sheet = z.read("xl/worksheets/sheet1.xml")
    assert b'mc:Ignorable="x14ac"' in sheet and b'x14ac:dyDescent="0.25"' in sheet
    assert b'<c r="E12" s="5"/>' in sheet  # a styled empty rate cell
    assert b'<c r="D14" s="4"><v>85.5</v></c><c r="F14"' in sheet  # E14 is missing
    assert b't="shared" ref="F13:F16" si="0"' in sheet
    assert "xl/sharedStrings.xml" in z.namelist() and "xl/media/image1.png" in z.namelist()
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb["BOQ"]
    assert wb.sheetnames == ["BOQ", "ملخص"]
    assert ws.sheet_view.rightToLeft and ws.freeze_panes == "A12"
    assert {str(r) for r in ws.merged_cells.ranges} == {"A1:F1", "A2:F2", "A19:E19"}
    assert ws["F12"].value == "=D12*E12" and ws["F19"].value == "=SUM(F12:F17)"
    assert ws["E12"].value is None and ws["E12"].style_id != 0
    assert ws["A15"].value == "٠٣/٠٢" and ws["D17"].value == RATE_ONLY_NOTE
    assert ws["D15"].value == 120 and ws["B12"].value.endswith("- عينة")
    assert "BOQ_Total" in wb.defined_names and ws.print_area == "'BOQ'!$A$1:$F$19"
    assert str(ws.data_validations.dataValidation[0].sqref) == "E12:E17"
    assert [str(r.sqref) for r in ws.conditional_formatting] == ["F12:F17"]
    assert wb["ملخص"]["B1"].value == "=BOQ!F19"


def test_sample_client_xlsm_carries_its_macros():
    z = zipfile.ZipFile(io.BytesIO(sample_client_xlsx(xlsm=True)))
    assert z.read("xl/vbaProject.bin") == VBA_PROJECT
    assert b"macroEnabled.main+xml" in z.read("[Content_Types].xml")
    wb = openpyxl.load_workbook(io.BytesIO(sample_client_xlsx(xlsm=True)), keep_vba=True)
    assert wb.vba_archive is not None
