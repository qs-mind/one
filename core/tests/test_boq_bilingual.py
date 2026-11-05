"""A bilingual BOQ with a two-row merged header, as the tender day's (5 Nov 2026): «الوصف /
Description» over «عربي» and «English», «سعر الوحدة» over «رقماً» and «كتابةً». The guess reads
the merged header; an item whose description is only in English is an item; the rows card lets the
engineer set what each column holds. Synthetic «عينة» workbooks only; scripted hosts only."""

import io
import json

import openpyxl

from qsone import copy
from qsone.engine.tools import call
from qsone.records import boq
from qsone.records.files import add_file
from qsone.tools import boq as boq_tools  # noqa: F401 - registers boq_preview and boq_import
from tests.fakes_tools import tool_ctx

GUESS = {
    "code": "A",
    "description": "B",
    "description_2": "C",
    "unit": "D",
    "quantity": "E",
    "rate": "F",
    "amount": "H",
}


def bilingual() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "المقايسة"
    ws.merge_cells("A1:H1")
    ws["A1"] = "مقايسة مبنى إداري - عينة"
    ws.merge_cells("A3:A4")
    ws["A3"] = "رقم البند\nItem No."
    ws.merge_cells("B3:C3")
    ws["B3"] = "الوصف / Description"
    ws["B4"], ws["C4"] = "عربي", "English"
    ws.merge_cells("D3:D4")
    ws["D3"] = "الوحدة\nUnit"
    ws.merge_cells("E3:E4")
    ws["E3"] = "الكمية\nQty"
    ws.merge_cells("F3:G3")
    ws["F3"] = "سعر الوحدة (ج.م) / Rate (EGP)"
    ws["F4"], ws["G4"] = "رقماً", "كتابةً"
    ws.merge_cells("H3:H4")
    ws["H3"] = "الإجمالي (ج.م)\nAmount"
    ws.merge_cells("A5:H5")
    ws["A5"] = "القسم 01: أعمال الحفر - عينة / Division 01: Earthworks - sample"
    rows = [
        ("01-01-001", "حفر - عينة", "Excavation - sample", "م3", 725),
        ("01-01-002", None, "Backfill - sample", "م3", 310.5),  # English only
        ("01-01-003", "نقل مخلفات - عينة", None, "م3", 120),  # Arabic only
        ("01-01-004", None, None, "م3", 12),  # a code and a quantity: still an item
    ]
    for r, (code, ar, en, unit, qty) in enumerate(rows, start=6):
        ws.cell(r, 1, code)
        ws.cell(r, 2, ar)
        ws.cell(r, 3, en)
        ws.cell(r, 4, unit)
        ws.cell(r, 5, qty)
        ws.cell(r, 8, f"=E{r}*F{r}")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_the_guess_reads_a_two_row_merged_header(rec):
    f = add_file(rec, "مقايسة - عينة.xlsx", bilingual(), actor="engineer").id
    p = boq.preview(rec, f, None)
    assert p["header_guess"] == 4 and p["columns_guess"] == GUESS


def test_an_item_in_any_language_is_an_item(rec):
    f = add_file(rec, "مقايسة - عينة.xlsx", bilingual(), actor="engineer").id
    plan = boq.plan(rec, f, sheet="المقايسة", header_row=4, columns=GUESS)
    items = [r for r in plan.rows if r.kind == boq.ITEM]
    assert [(r.code, r.description, r.description_2) for r in items] == [
        ("01-01-001", "حفر - عينة", "Excavation - sample"),
        ("01-01-002", "Backfill - sample", None),
        ("01-01-003", "نقل مخلفات - عينة", None),
        ("01-01-004", "", None),
    ]
    assert plan.skipped == []
    assert plan.sheet_columns["B"]["header"] == "الوصف / Description · عربي"
    assert plan.sheet_columns["A"]["header"] == "رقم البند\nItem No."


def _import_args(f: str, columns: dict) -> dict:
    return {
        "file_id": f,
        "sheet": "المقايسة",
        "header_row": 4,
        "columns": columns,
        "currency": "EGP",
    }


async def test_the_rows_card_sets_each_columns_meaning(rec):
    f = add_file(rec, "مقايسة - عينة.xlsx", bilingual(), actor="engineer").id
    wrong = {"description": "B", "unit": "C", "quantity": "D"}  # tender day's first guess
    fixed = {letter: "none" for letter in "ABCDEFGH"}
    fixed |= {"A": "code", "B": "description", "C": "description_2", "D": "unit", "E": "quantity"}
    answer = json.dumps({"choice": "keep", "answers": fixed, "rows_ok": []})
    ctx = tool_ctx(rec, answers={"rows": answer})
    out = await call("boq_import", _import_args(f, wrong), ctx)
    (card,) = ctx.host.cards
    meanings = [m["key"] for m in card.payload["meanings"]]
    assert meanings == [*boq.FIELDS, "none"]
    by_letter = {r["column"]: r["meaning"] for r in card.payload["rows"]}
    assert by_letter == {"A": "none", "B": "description", "C": "unit", "D": "quantity"} | {
        letter: "none" for letter in "EFGH"
    }
    assert [q["id"] for q in card.payload["questions"]] == list("ABCDEFGH")
    assert "tick" not in card.payload
    assert '"items": 4' in out
    with rec.read() as c:
        rows = c.execute("SELECT code, fields FROM items WHERE kind = 'boq_item'").fetchall()
    found = {code: json.loads(fields) for code, fields in rows}
    assert found["01-01-002"]["description"] == "Backfill - sample"
    assert found["01-01-001"]["description_2"] == "Excavation - sample"


async def test_a_meaning_set_twice_imports_nothing(rec):
    f = add_file(rec, "مقايسة - عينة.xlsx", bilingual(), actor="engineer").id
    twice = {letter: "none" for letter in "ABCDEFGH"}
    twice |= {"B": "description", "C": "description", "D": "unit", "E": "quantity"}
    ctx = tool_ctx(rec, answers={"rows": json.dumps({"choice": "keep", "answers": twice})})
    out = await call("boq_import", _import_args(f, GUESS), ctx)
    assert out.startswith("not done: ") and copy.BOQ_MEANING_TWICE["en"].split("{")[0] in out
