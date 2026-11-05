"""The client's own file: read it, map it with a Fill Plan, preview and fill it from a signed-off
Revision, patching only the mapped cells (synthetic «عينة» files only)."""

import io
import json
import re
import zipfile
from decimal import Decimal

import openpyxl
import pytest

from qsone import copy
from qsone.clientfile import patch
from qsone.clientfile.fill import accept_mismatches, fill, preview, read_sheet, save_plan
from qsone.clientfile.patch import Write, patch_xlsx
from qsone.deliverables import review
from qsone.deliverables.store import view
from qsone.records import files, ledger
from qsone.records.project import RecordsError
from tests.samples import (
    CLIENT_FIRST_ROW,
    VBA_PROJECT,
    sample_client_xlsx,
    sample_sheet,
    sample_source,
    sample_xls,
)

SHEET1 = "xl/worksheets/sheet1.xml"
WORKBOOK = "xl/workbook.xml"
_CELL = re.compile(rb'<(?:\w+:)?c r="([A-Z]+[0-9]+)"[^>]*?(?:/>|>.*?</(?:\w+:)?c>)', re.S)

# Helpers ------------------------------------------------------------------------------------


def cells_of(xml: bytes) -> dict[str, bytes]:
    return {m[1].decode(): m[0] for m in _CELL.finditer(xml)}


def cells_except(xml: bytes, refs: set[str]) -> bytes:
    """The sheet's bytes with the given cells cut out."""
    return _CELL.sub(lambda m: b"" if m[1].decode() in refs else m[0], xml)


def part(data: bytes, name: str) -> bytes:
    return zipfile.ZipFile(io.BytesIO(data)).read(name)


def replace_part(data: bytes, name: str, body: bytes) -> bytes:
    a = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as b:
        for info in a.infolist():
            b.writestr(info, body if info.filename == name else a.read(info.filename))
    return out.getvalue()


def load(data: bytes) -> openpyxl.Workbook:
    return openpyxl.load_workbook(io.BytesIO(data))


def text_of(e: pytest.ExceptionInfo) -> dict:
    return e.value.text


def items(v: dict) -> list[dict]:
    return [r for r in v["rows"] if r["kind"] == "item"]


def sign_off(rec, d: str, *, signed_off: bool = True) -> int:
    """The next Revision of the current version: signed off after a Code A check, or only
    issued."""
    if not signed_off:
        return review.issue_revision(rec, d, actor="engineer")
    review.record_check(
        rec,
        d,
        version_n=view(rec, d)["version"],
        code="A",
        checker="model-sample",
        same_provider=False,
        summary="",
        comments=[],
    )
    return review.sign_off(rec, d, actor="engineer")


def client_file(rec, name: str = "جدول كميات العميل - عينة.xlsx", **kw) -> str:
    return files.add_file(rec, name, sample_client_xlsx(**kw), actor="engineer").id


def plan_for(v: dict, **extra) -> dict:
    """Client rows 12-17 hold the sample sheet's six items in order."""
    rows = [{"row": CLIENT_FIRST_ROW + i, "part": r["id"]} for i, r in enumerate(items(v))]
    return {
        "sheet": "BOQ",
        "header_row": 11,
        "columns": {"code": "A", "description": "B", "rate": "E", "amount": "F"},
        "write": ["rate"],
        "rows": rows,
    } | extra


# patch_xlsx: bytes in, bytes out --------------------------------------------------------------


def test_only_mapped_cells_change():
    sample = sample_client_xlsx()
    out = patch_xlsx(
        sample, [Write("BOQ", "E12", Decimal("39850.50")), Write("BOQ", "E13", Decimal("120"))]
    )
    assert out.written == ["E12", "E13"] and out.skipped == []
    a, b = zipfile.ZipFile(io.BytesIO(sample)), zipfile.ZipFile(io.BytesIO(out.data))
    assert a.namelist() == b.namelist()
    touched = {SHEET1, WORKBOOK}
    for name in a.namelist():
        if name not in touched:
            assert a.read(name) == b.read(name), name
    assert cells_except(a.read(SHEET1), {"E12", "E13"}) == cells_except(
        b.read(SHEET1), {"E12", "E13"}
    )
    assert b'mc:Ignorable="x14ac"' in b.read(SHEET1)  # prefixes kept
    assert cells_of(b.read(SHEET1))["E12"] == b'<c r="E12" s="5"><v>39850.5</v></c>'
    ws = load(out.data)["BOQ"]
    assert ws["E12"].value == 39850.5 and ws["E13"].value == 120
    assert ws["E12"].style_id == load(sample)["BOQ"]["E12"].style_id


def test_zip_entries_keep_their_order_dates_and_compression():
    sample = sample_client_xlsx()
    out = patch_xlsx(sample, [Write("BOQ", "E12", Decimal("1"))]).data
    old, new = (zipfile.ZipFile(io.BytesIO(x)).infolist() for x in (sample, out))
    keep = ("filename", "date_time", "compress_type", "external_attr")
    assert [[getattr(i, k) for k in keep] for i in old] == [
        [getattr(i, k) for k in keep] for i in new
    ]


def test_numbers_go_in_as_exact_decimal_text():
    writes = [
        Write("BOQ", "E12", Decimal("39850.50")),
        Write("BOQ", "E13", Decimal("1234567890.123456789")),
        Write("BOQ", "E15", Decimal("1E+3")),
        Write("BOQ", "E16", Decimal("0.00")),
    ]
    cells = cells_of(part(patch_xlsx(sample_client_xlsx(), writes).data, SHEET1))
    assert b"<v>39850.5</v>" in cells["E12"]
    assert b"<v>1234567890.123456789</v>" in cells["E13"]
    assert b"<v>1000</v>" in cells["E15"] and b"<v>0</v>" in cells["E16"]


def test_client_formulas_are_never_overwritten():
    sample = sample_client_xlsx()
    writes = [Write("BOQ", ref, Decimal("5")) for ref in ("F12", "F13", "F14", "F19")]
    out = patch_xlsx(sample, writes)
    assert out.written == []
    assert out.skipped == [
        ("F12", "formula"),
        ("F13", "formula"),
        ("F14", "formula"),
        ("F19", "formula"),
    ]
    assert part(out.data, SHEET1) == part(sample, SHEET1)


def test_merged_cells_other_than_the_first_are_skipped():
    out = patch_xlsx(
        sample_client_xlsx(), [Write("BOQ", "B1", "x"), Write("BOQ", "A1", "جدول - عينة")]
    )
    assert out.skipped == [("B1", "merged")] and out.written == ["A1"]
    assert load(out.data)["BOQ"]["A1"].value == "جدول - عينة"


def test_full_calc_on_load_is_set():
    sample = sample_client_xlsx()
    out = patch_xlsx(sample, [Write("BOQ", "E12", Decimal("1"))]).data
    before, after = part(sample, WORKBOOK), part(out, WORKBOOK)
    assert b'<calcPr calcId="191029"/>' in before
    assert after == before.replace(
        b'<calcPr calcId="191029"/>', b'<calcPr calcId="191029" fullCalcOnLoad="1"/>'
    )
    assert load(out).calculation.fullCalcOnLoad


def test_full_calc_on_load_replaces_a_zero_and_is_inserted_when_missing():
    sample = sample_client_xlsx()
    wb = part(sample, WORKBOOK)
    zero = replace_part(
        sample, WORKBOOK, wb.replace(b'calcId="191029"', b'calcId="1" fullCalcOnLoad="0"')
    )
    assert b'<calcPr calcId="1" fullCalcOnLoad="1"/>' in part(patch_xlsx(zero, []).data, WORKBOOK)
    none = replace_part(sample, WORKBOOK, wb.replace(b'<calcPr calcId="191029"/>', b""))
    after = part(patch_xlsx(none, []).data, WORKBOOK)
    assert after.endswith(b'</definedNames><calcPr fullCalcOnLoad="1"/></workbook>')
    # in schema order: before a later child such as extLst
    ext = replace_part(sample, WORKBOOK, wb.replace(b'<calcPr calcId="191029"/>', b"<extLst/>"))
    assert b'<calcPr fullCalcOnLoad="1"/><extLst/></workbook>' in part(
        patch_xlsx(ext, []).data, WORKBOOK
    )


def test_missing_cell_is_inserted_in_column_order():
    sample = sample_client_xlsx()
    assert "E14" not in cells_of(part(sample, SHEET1))
    out = patch_xlsx(sample, [Write("BOQ", "E14", Decimal("2750"))])
    xml = part(out.data, SHEET1)
    d14, e14, f14 = (xml.index(f'<c r="{ref}"'.encode()) for ref in ("D14", "E14", "F14"))
    assert d14 < e14 < f14
    assert cells_of(xml)["E14"] == b'<c r="E14" s="5"><v>2750</v></c>'  # its column's style
    assert cells_except(xml, {"E14"}) == part(sample, SHEET1)
    ws = load(out.data)["BOQ"]
    assert ws["E14"].value == 2750 and ws["E14"].style_id == ws["E13"].style_id


def test_cells_go_in_at_the_end_of_a_row_and_into_an_empty_row():
    sample = sample_client_xlsx()
    sheet = part(sample, SHEET1).replace(b'<row r="4"', b'<row r="3"/><row r="4"')
    sample = replace_part(sample, SHEET1, sheet)
    out = patch_xlsx(
        sample,
        [Write("BOQ", "H12", "ملاحظة - عينة"), Write("BOQ", "C3", "ب"), Write("BOQ", "A3", "أ")],
    )
    xml = part(out.data, SHEET1)
    assert b'<row r="3"><c r="A3" t="inlineStr">' in xml and b'</c></row><row r="4"' in xml
    assert xml.index(b'<c r="A3"') < xml.index(b'<c r="C3"')
    row12 = xml[xml.index(b'<row r="12"') : xml.index(b'<row r="13"')]
    assert row12.index(b'<c r="F12"') < row12.index(b'<c r="H12"') < row12.index(b"</row>")


def test_missing_row_is_refused():
    with pytest.raises(RecordsError) as e:
        patch_xlsx(sample_client_xlsx(), [Write("BOQ", "E999", Decimal("1"))])
    assert text_of(e) == copy.fill(copy.FILL_ROW_MISSING, row=999)


def test_unknown_sheet_is_refused():
    with pytest.raises(RecordsError) as e:
        patch_xlsx(sample_client_xlsx(), [Write("ورقة - عينة", "E12", Decimal("1"))])
    assert text_of(e) == copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet="ورقة - عينة")


def test_text_goes_in_as_inline_string():
    sample = sample_client_xlsx()
    out = patch_xlsx(sample, [Write("BOQ", "C12", "م3 <عينة> & ك")])
    cell = cells_of(part(out.data, SHEET1))["C12"]
    assert (
        cell
        == (
            '<c r="C12" s="3" t="inlineStr"><is><t xml:space="preserve">م3 &lt;عينة&gt; &amp; ك</t>'
            "</is></c>"
        ).encode()
    )
    assert part(out.data, "xl/sharedStrings.xml") == part(sample, "xl/sharedStrings.xml")
    assert load(out.data)["BOQ"]["C12"].value == "م3 <عينة> & ك"


def test_a_prefixed_sheet_keeps_its_prefix():
    sample = sample_client_xlsx()
    xml = part(sample, SHEET1)
    xml = re.sub(rb"<(/?)(?![?/])([A-Za-z])", rb"<\1x:\2", xml).replace(b'xmlns="', b'xmlns:x="')
    out = patch_xlsx(
        replace_part(sample, SHEET1, xml),
        [Write("BOQ", "E12", Decimal("14")), Write("BOQ", "E14", Decimal("2750"))],
    )
    got = part(out.data, SHEET1)
    assert b'<x:c r="E12" s="5"><x:v>14</x:v></x:c>' in got
    assert b'<x:c r="E14" s="5"><x:v>2750</x:v></x:c><x:c r="F14"' in got
    assert out.skipped == []


def test_xlsm_keeps_its_macros():
    sample = sample_client_xlsx(xlsm=True)
    out = patch_xlsx(sample, [Write("BOQ", "E12", Decimal("1"))])
    assert part(out.data, "xl/vbaProject.bin") == VBA_PROJECT == part(sample, "xl/vbaProject.bin")


def test_a_damaged_file_or_a_huge_part_is_refused(monkeypatch):
    with pytest.raises(RecordsError) as e:
        patch_xlsx(b"PK\x03\x04 not a zip", [])
    assert text_of(e) == copy.FILE_UNREADABLE
    monkeypatch.setattr(patch, "MAX_PART_BYTES", 1024)  # the 64 MB zip-bomb guard, made small
    with pytest.raises(RecordsError) as e:
        patch_xlsx(sample_client_xlsx(), [])
    assert text_of(e) == copy.FILE_UNREADABLE


# The Fill Plan, preview and fill --------------------------------------------------------------


def test_read_sheet_is_paged_with_cell_letters(rec):
    f = client_file(rec)
    page = read_sheet(rec, f, start_row=11, limit=5)
    assert page["sheets"] == ["BOQ", "ملخص"] and page["sheet"] == "BOQ"
    assert [r["row"] for r in page["rows"]] == [11, 12, 13, 14, 15] and page["next"] == 16
    row15 = page["rows"][4]["cells"]
    assert row15["A"] == "٠٣/٠٢" and row15["B"] == "خرسانة مسلحة للأسقـــف - عينة"  # as written
    assert row15["D"] == "120" and row15["E"] is None and row15["F"] == "=D15*E15"
    assert page["rows"][3]["cells"]["D"] == "85.5"
    rest = read_sheet(rec, f, start_row=16)
    assert [r["row"] for r in rest["rows"]] == [16, 17, 19] and rest["next"] is None  # 18 is empty
    assert read_sheet(rec, f, sheet="ملخص")["rows"][0]["cells"]["B"] == "=BOQ!F19"
    with pytest.raises(RecordsError) as e:
        read_sheet(rec, f, sheet="لا يوجد")
    assert text_of(e) == copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet="لا يوجد")


def test_xls_is_refused_in_plain_words(rec):
    d = sample_sheet(rec)
    xls = files.add_file(rec, "جدول - عينة.xls", sample_xls({"BOQ": [["1-1"]]}), actor="engineer")
    csv = files.add_file(rec, "جدول - عينة.csv", "1-1,حفر\n".encode(), actor="engineer")
    for f in (xls.id, csv.id):
        with pytest.raises(RecordsError) as e:
            save_plan(rec, d, f, plan_for(view(rec, d)), actor="lead_qs")
        assert text_of(e) == copy.FILL_XLS_NOT_SUPPORTED and e.value.status == 422
        with pytest.raises(RecordsError):
            read_sheet(rec, f)


@pytest.mark.parametrize(
    ("change", "text", "field"),
    [
        (
            lambda p: p | {"sheet": "ورقة"},
            copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet="ورقة"),
            "sheet",
        ),
        (
            lambda p: p | {"columns": p["columns"] | {"rate": "XFE"}},
            copy.FILL_COLUMN_LETTER,
            "columns.rate",
        ),
        (lambda p: p | {"write": ["rate", "floor"]}, copy.COLUMN_NOT_ALLOWED, "write[1]"),
        (lambda p: p | {"write": ["quantity"]}, copy.COLUMN_NOT_ALLOWED, "write[0]"),  # unmapped
        (
            lambda p: p | {"rows": [*p["rows"], {"row": 12, "part": p["rows"][1]["part"]}]},
            copy.fill(copy.FILL_ROW_TWICE, row=12),
            "rows[6].row",
        ),
        (
            lambda p: p | {"rows": [*p["rows"], {"row": 19, "part": p["rows"][0]["part"]}]},
            copy.fill(copy.FILL_ROW_TWICE, row=19),
            "rows[6].part",
        ),
        (
            lambda p: p | {"rows": [*p["rows"], {"row": 18, "part": "nope"}]},
            copy.ROW_NOT_FOUND,
            "rows[6].part",
        ),
    ],
)
def test_save_plan_checks_the_plan(rec, change, text, field):
    d = sample_sheet(rec)
    with pytest.raises(RecordsError) as e:
        save_plan(rec, d, client_file(rec), change(plan_for(view(rec, d))), actor="lead_qs")
    assert (text_of(e), e.value.field) == (text, field)


def test_save_plan_refuses_a_section_row_and_a_row_not_in_the_sheet(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    section = next(r["id"] for r in v["rows"] if r["kind"] == "section")
    p = plan_for(v)
    with pytest.raises(RecordsError) as e:
        save_plan(rec, d, client_file(rec), p | {"rows": [{"row": 12, "part": section}]}, actor="x")
    assert text_of(e) == copy.ROW_NOT_FOUND
    p["rows"][0]["row"] = 18  # an empty row Excel never wrote
    with pytest.raises(RecordsError) as e:
        save_plan(rec, d, client_file(rec), p, actor="lead_qs")
    assert text_of(e) == copy.fill(copy.FILL_ROW_MISSING, row=18) and e.value.field == "rows[0].row"


def test_preview_needs_a_signed_off_revision(rec):
    d = sample_sheet(rec)
    plan = save_plan(rec, d, client_file(rec), plan_for(view(rec, d)), actor="lead_qs")
    for _ in range(2):
        with pytest.raises(RecordsError) as e:
            preview(rec, plan)
        assert text_of(e) == copy.FILL_NEEDS_SIGNOFF
        sign_off(rec, d, signed_off=False)  # a Revision issued but not signed off is not enough


def test_preview_flags_code_mismatch_and_lists_what_is_left_out(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    p = plan_for(v, write=["rate", "amount"])
    p["rows"][0]["part"], p["rows"][1]["part"] = p["rows"][1]["part"], p["rows"][0]["part"]
    left_out = p["rows"].pop()  # row 17, the rate-only item 2-4
    plan = save_plan(rec, d, client_file(rec), p, actor="lead_qs")
    rev = sign_off(rec, d)
    out = preview(rec, plan)
    assert out["revision"] == rev
    assert [(m["row"], m["code_ours"], m["code_theirs"]) for m in out["mismatches"]] == [
        (12, "1-2", "1-1"),
        (13, "1-1", "1-2"),
    ]  # row 15: «٠٣/٠٢» is our 03/02
    assert out["mismatches"][0]["text"] == copy.fill(
        copy.FILL_CODE_MISMATCH, row=12, theirs="1-1", ours="1-2"
    )
    e15 = next(w for w in out["writes"] if w["cell"] == "E15")
    assert e15 == {
        "cell": "E15",
        "row": 15,
        "column": "rate",
        "before": None,
        "after": "39850.50",
        "code_ours": "03/02",
        "code_theirs": "٠٣/٠٢",
        "client_text": "خرسانة مسلحة للأسقـــف - عينة",
    }
    assert [w["cell"] for w in out["writes"]] == ["E12", "E13", "E14", "E15", "E16"]
    assert out["skipped"] == [
        {"cell": f"F{n}", "reason": "formula"} for n in range(12, 17)
    ]  # the client's own amounts stay his formulas
    assert out["unmapped_rows"] == [17, 19] and out["unmapped_items"] == [
        {"part": left_out["part"], "code": "2-4"}
    ]


def test_fill_refuses_mismatches_until_the_engineer_accepts_them(rec):
    d = sample_sheet(rec)
    p = plan_for(view(rec, d))
    p["rows"][0]["part"], p["rows"][1]["part"] = p["rows"][1]["part"], p["rows"][0]["part"]
    plan = save_plan(rec, d, client_file(rec), p, actor="lead_qs")
    sign_off(rec, d)
    with pytest.raises(RecordsError) as e:
        fill(rec, plan, actor="engineer")
    assert text_of(e) == copy.fill(copy.FILL_CODE_MISMATCH, row=12, theirs="1-1", ours="1-2")
    assert e.value.field == "rows[0]"
    out = accept_mismatches(rec, plan, [12], actor="engineer")
    assert [m["accepted"] for m in out["mismatches"]] == [True, False]
    out = accept_mismatches(rec, plan, [13], actor="engineer")
    assert all(m["accepted"] for m in out["mismatches"])
    data, _, report = fill(rec, plan, actor="engineer")
    assert report["accepted_mismatches"] == [12, 13]
    assert load(data)["BOQ"]["E12"].value == 22.5  # the 1-2 rate, as the engineer accepted


def test_fill_end_to_end_from_a_signed_off_revision(rec):
    d = sample_sheet(rec)
    f = client_file(rec)
    plan = save_plan(rec, d, f, plan_for(view(rec, d), write=["rate", "amount"]), actor="lead_qs")
    rev = sign_off(rec, d)
    rate = next(r for r in items(view(rec, d)) if r["code"] == "03/02")["cells"]["rate"]
    ledger.correct_number(  # a move after sign-off does not reach the client's file
        rec,
        rate["number_id"],
        value="40000",
        reason="عرض جديد - عينة",
        source_id=sample_source(rec),
        dated="2026-11-04",
        actor="estimator",
    )
    data, name, report = fill(rec, plan, actor="engineer")
    assert name == "جدول كميات العميل - عينة - QS Mind ONE.xlsx"
    assert report["revision"] == rev
    assert report["written"] == ["E12", "E13", "E14", "E15", "E16", "E17"]
    assert report["skipped"] == [{"cell": f"F{n}", "reason": "formula"} for n in range(12, 17)]
    wb = load(data)
    ws = wb["BOQ"]
    assert [ws[f"E{n}"].value for n in range(12, 18)] == [14, 22.5, 2750, 39850.5, 95, 120]
    assert ws["F12"].value == "=D12*E12" and ws["F19"].value == "=SUM(F12:F17)"
    assert wb.calculation.fullCalcOnLoad and "BOQ_Total" in wb.defined_names
    original = files.read_original(rec, f)
    for name_ in zipfile.ZipFile(io.BytesIO(original)).namelist():
        if name_ not in {SHEET1, WORKBOOK}:
            assert part(data, name_) == part(original, name_), name_


def test_an_xlsm_comes_back_as_xlsm(rec):
    d = sample_sheet(rec)
    f = client_file(rec, "boq - عينة.xlsm", xlsm=True)
    plan = save_plan(rec, d, f, plan_for(view(rec, d)), actor="lead_qs")
    sign_off(rec, d)
    data, name, _ = fill(rec, plan, actor="engineer")
    assert (
        name == "boq - عينة - QS Mind ONE.xlsm" and part(data, "xl/vbaProject.bin") == VBA_PROJECT
    )


def test_a_plan_is_kept_with_its_audit_row(rec):
    d = sample_sheet(rec)
    f = client_file(rec)
    plan = save_plan(rec, d, f, plan_for(view(rec, d)), actor="lead_qs")
    with rec.read() as c:
        row = c.execute(
            "SELECT deliverable_id, file_id, plan, created_by FROM fill_plans WHERE id = ?", (plan,)
        ).fetchone()
        audited = c.execute(
            "SELECT actor FROM audit WHERE table_name = 'fill_plans' AND row_id = ?", (plan,)
        ).fetchall()
    assert row[:2] == (d, f) and json.loads(row[2])["sheet"] == "BOQ" and row[3] == "lead_qs"
    assert audited == [("lead_qs",)]


def test_unknown_plans_and_files_are_not_found(rec):
    d = sample_sheet(rec)
    for call in (lambda: preview(rec, "nope"), lambda: fill(rec, "f" * 32, actor="engineer")):
        with pytest.raises(RecordsError) as e:
            call()
        assert (text_of(e), e.value.status) == (copy.FILL_PLAN_NOT_FOUND, 404)
    with pytest.raises(RecordsError) as e:
        save_plan(rec, d, "f" * 32, plan_for(view(rec, d)), actor="lead_qs")
    assert (text_of(e), e.value.status, e.value.field) == (copy.FILE_NOT_IN_PROJECT, 404, "file_id")
    with pytest.raises(RecordsError) as e:
        read_sheet(rec, "f" * 32)
    assert e.value.status == 404
    plan = save_plan(rec, d, client_file(rec), plan_for(view(rec, d)), actor="lead_qs")
    with pytest.raises(RecordsError) as e:
        accept_mismatches(rec, plan, "12", actor="engineer")  # rows are a list
    assert e.value.field == "rows"
