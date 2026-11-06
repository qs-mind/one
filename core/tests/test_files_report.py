"""The report after a drop (real walk, 6 Nov 2026: dropping the tender files started nothing in
the chat). Sample files here; the real Lahun BOQ in test_tender_files.py."""

import time

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.records import report
from qsone.records.files import add_file
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_xlsx

HEADER = ["البند", "الوصف", "الوحدة", "الكمية", "الفئة", "القيمة"]
BOQ_ROWS = [
    HEADER,
    ["", "أعمال الخرسانة - عينة", "", "", "", ""],
    ["1", "خرسانة عادية للأساسات - عينة", "م3", 12, 900, 10800],
    ["2", "خرسانة مسلحة للأسقف - عينة", "م3", 30, 2500, 75000],
    ["", "أعمال المباني - عينة", "", "", "", ""],
    ["3", "مباني طوب - عينة", "م2", 200, 150, 30000],
    ["", "الإجمالي", "", "", "", 115800],
]


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


def test_a_drop_is_reported_from_the_records(rec):
    boq_id = add_file(
        rec, "مقايسة - عينة.xlsx", sample_xlsx({"BOQ": BOQ_ROWS}), actor="engineer"
    ).id
    specs = sample_pdf([["Technical Specifications - sample", "Clause 1: Concrete"]])
    specs_id = add_file(rec, "كراسة - عينة.pdf", specs, actor="engineer").id
    found = report.make(rec, [boq_id, specs_id])
    lines = [line["en"] for line in found["lines"]]
    assert lines[0] == "ONE read 2 files:"
    assert lines[1].endswith(": BOQ.") and "مقايسة - عينة.xlsx" in lines[1]
    assert lines[2] == (
        "Sheet «BOQ»: 3 items in 2 sections (rows 2–7). Its own total: 115,800 (row 7, column F)."
    )
    assert lines[3].endswith(": Specifications.")
    assert lines[-1] == "Not among the project's files yet: Conditions of contract, Drawings."
    assert found["lines"][2]["ar"] == (
        "شيت «BOQ»: 3 بنود في قسمين (الصفوف 2–7). إجماليه في الملف: 115,800 (صف 7، عمود F)."
    )
    assert report.kept(rec) == [{"id": found["id"], "at": found["at"], "lines": found["lines"]}]


def test_what_could_not_be_read_is_said_and_drawings_need_no_text(rec):
    locked = add_file(rec, "عرض سعر - عينة.xlsx", b"PK\x03\x04 not a zip", actor="engineer")
    dwg = add_file(rec, "لوحات - عينة.dwg", b"AC1032 sample", actor="engineer")
    found = report.make(rec, [locked.id, dwg.id])
    lines = [line["en"] for line in found["lines"]]
    assert lines[1].endswith(getattr(copy, locked.note or "FILE_UNREADABLE")["en"])
    assert lines[2].endswith(": Drawings.")
    assert "Drawings" not in lines[-1] and lines[-1].startswith("Not among")


def test_a_later_drop_counts_what_came_before(rec):
    first = add_file(rec, "مقايسة - عينة.xlsx", sample_xlsx({"BOQ": BOQ_ROWS}), actor="engineer")
    report.make(rec, [first.id])
    specs = add_file(rec, "مواصفات - عينة.pdf", sample_pdf([["عينة"]]), actor="engineer")
    lines = [line["en"] for line in report.make(rec, [specs.id])["lines"]]
    assert lines[-1] == "Not among the project's files yet: Conditions of contract, Drawings."
    assert report.make(rec, []) is None


def test_the_report_comes_in_the_project_chat_at_once_with_no_model(client):
    pid = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    up = client.post(
        f"/projects/{pid}/files",
        params={"name": "مقايسة - عينة.xlsx"},
        content=sample_xlsx({"BOQ": BOQ_ROWS}),
        headers=AUTH,
    ).json()
    started = time.monotonic()
    r = client.post(f"/projects/{pid}/files/report", json={"file_ids": [up["id"]]}, headers=AUTH)
    assert r.status_code == 201 and time.monotonic() - started < 3
    assert r.json()["lines"][2]["en"].startswith("Sheet «BOQ»: 3 items in 2 sections")
    chat = client.get(f"/chat/{pid}/messages", headers=AUTH).json()["messages"]
    said = [m for m in chat if m["role"] == "assistant"]
    assert said[-1]["parts"] == [
        {"type": "data-files_read", "id": r.json()["id"], "data": {"lines": r.json()["lines"]}}
    ]
    nothing = client.post(f"/projects/{pid}/files/report", json={"file_ids": []}, headers=AUTH)
    assert nothing.status_code == 204


def test_the_report_of_the_real_lahun_boq_and_momah_specs(rec):
    from tests.test_tender_files import LAHUN, MOMAH, real

    lahun = add_file(rec, "boq-priced.xlsx", real(LAHUN), actor="engineer").id
    momah = add_file(rec, "road-specs.pdf", real(MOMAH), actor="engineer").id
    lines = [line["en"] for line in report.make(rec, [lahun, momah])["lines"]]
    assert lines[1].endswith(": BOQ.")
    assert lines[2].startswith("Sheet «مقايسة »: 54 items in 4 sections (rows ")
    assert lines[2].endswith("Its own total: 640,983.35 (row 66, column H).")
    assert lines[3].endswith(": Specifications.")
    assert lines[-1] == "Not among the project's files yet: Conditions of contract, Drawings."


@pytest.mark.parametrize(
    "pages, missing",
    [
        ([["Specifications sample"], [], []], [2, 3]),
        ([[], []], [1, 2]),
        ([["Specifications sample"]], []),
    ],
)
def test_pdf_report_names_pages_without_text(rec, pages, missing):
    f = add_file(rec, "Specifications sample.pdf", sample_pdf(pages), actor="engineer")
    found = report.make(rec, [f.id])
    detail = found["files"][0]["pdf"]
    assert detail == {"pages": len(pages), "needs_reading": missing, "boq_rows": None}
    for lang in ("en", "ar"):
        said = " ".join(line[lang] for line in found["lines"])
        assert str(len(pages)) in said
        assert all(str(p) in said for p in missing)
    if missing:
        assert "No text on pages: " + ", ".join(map(str, missing)) in " ".join(
            line["en"] for line in found["lines"]
        )
    assert report.kept(rec)[0]["lines"] == found["lines"]


def test_pdf_report_counts_boq_rows_using_pdf_import(rec):
    from tests.test_boq_pdf import pdf

    f = add_file(rec, "BOQ sample.pdf", pdf(multipage=True), actor="engineer")
    found = report.make(rec, [f.id])
    assert found["files"][0]["pdf"] == {"pages": 2, "needs_reading": [], "boq_rows": 2}
    assert any("2 BOQ rows" in line["en"] and "2" in line["ar"] for line in found["lines"])


def test_pdf_page_report_survives_a_table_reader_failure(rec, monkeypatch):
    f = add_file(rec, "Specifications sample.pdf", sample_pdf([["sample"], []]), actor="engineer")

    def failed(data):
        raise ValueError("sample unsupported table")

    monkeypatch.setattr(report.boq_pdf, "sheets", failed)
    found = report.make(rec, [f.id])
    assert found["files"][0]["pdf"] == {"pages": 2, "needs_reading": [2], "boq_rows": None}
    assert any("No text on pages: 2" in line["en"] for line in found["lines"])


def test_boq_sheet_reader_dispatches_pdf_to_pdf_reader(rec):
    from tests.test_boq_pdf import pdf

    f = add_file(rec, "BOQ sample.pdf", pdf(), actor="engineer")
    sheets, priced = report._boq_sheets(rec, f.id, "BOQ sample.pdf", "pdf")
    assert len(sheets) == 1 and sheets[0]["items"] == 1
    assert not priced


def test_report_says_when_excel_reader_cannot_read(rec, monkeypatch):
    from xlrd import XLRDError

    f = add_file(rec, "BOQ sample.xlsx", sample_xlsx({"BOQ": BOQ_ROWS}), actor="engineer")

    def failed(*args):
        raise XLRDError("sample bad workbook")

    monkeypatch.setattr(report.boq, "_xlsx", failed)
    found = report.make(rec, [f.id])
    assert found["files"][0]["label"] is None
    assert copy.FILE_UNREADABLE["en"] in found["lines"][1]["en"]


@pytest.mark.parametrize("wrapped", [False, True])
def test_report_says_when_pdf_table_reader_cannot_read(rec, monkeypatch, wrapped):
    from pdfminer.pdfparser import PDFSyntaxError
    from pdfplumber.utils.exceptions import PdfminerException

    f = add_file(rec, "BOQ sample.pdf", sample_pdf([["sample"]]), actor="engineer")

    def failed(*args):
        raise (PdfminerException if wrapped else PDFSyntaxError)("sample bad table")

    monkeypatch.setattr(report.boq_pdf, "sheets", failed)
    found = report.make(rec, [f.id])
    assert found["files"][0]["pdf"]["pages"] == 1
    assert found["files"][0]["pdf"]["boq_rows"] is None
    assert any("could not read the tables" in line["en"] for line in found["lines"])
