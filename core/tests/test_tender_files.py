"""The real tender files of the QS's walk (6 Nov 2026), read as dropped: Lahun's priced BOQ
(Arabic, a sheet named «مقايسة » with a trailing space, build-up sheets hidden), the SGH
fit-out BOQ (English, hidden rows) and the ministry's road specs PDF (806 pages, Arabic).

The files live in the private docs repo (`docs/test-files/`), never in this public one: each
test is skipped where they are not. They are read, never changed; no AI and no web here."""

import os
import warnings
from pathlib import Path

import pytest

from qsone.records import boq
from qsone.records.files import add_file


def _test_files() -> Path | None:
    if os.environ.get("QSONE_TEST_FILES"):
        return Path(os.environ["QSONE_TEST_FILES"])
    for parent in Path(__file__).resolve().parents:
        found = parent / "docs" / "test-files"
        if found.is_dir():
            return found
    return None


FILES = _test_files()


def real(path: str) -> bytes:
    if FILES is None or not (FILES / path).is_file():
        pytest.skip(f"the real file {path} is not on this computer")
    return (FILES / path).read_bytes()


LAHUN = "egypt/lahun-medical-center/boq-priced.xlsx"
SGH = "saudi/sgh-makkah-opd-fitout/sgh-makkah-opd-fitout-boq.xlsx"
MOMAH = "saudi/momah-road-specs/road-general-specs-part2-structures.pdf"


@pytest.fixture(autouse=True)
def _quiet():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # openpyxl on SGH's print area
        yield


def test_lahun_sheet_with_a_trailing_space_is_found(rec):
    f = add_file(rec, "boq-priced.xlsx", real(LAHUN), actor="engineer").id
    p = boq.preview(rec, f, "مقايسة")  # as a tool sends it: trimmed
    assert p["sheet"] == "مقايسة "


def test_lahun_overview_reads_the_whole_sheet(rec):
    f = add_file(rec, "boq-priced.xlsx", real(LAHUN), actor="engineer").id
    o = boq.preview(rec, f, None)["overview"]
    assert o["items"] == 54 and o["sections_count"] == 4
    assert o["total"] == {
        "value": "640983.35",
        "row": 66,
        "column": "H",
        "label": o["total"]["label"],
    }


def test_lahun_columns_are_the_total_quantity_and_the_amount(rec):
    f = add_file(rec, "boq-priced.xlsx", real(LAHUN), actor="engineer").id
    p = boq.preview(rec, f, None)
    assert p["header_guess"] == 3
    assert p["columns_guess"] == {
        "code": "A",
        "description": "B",
        "unit": "C",
        "quantity": "F",  # «اجمالي كميات المقايسة والزيادة», not D (the original quantity)
        "rate": "G",
        "amount": "H",  # «اجمالي مقايسة»
    }


@pytest.mark.parametrize("sheet", ["Electrical", "Low Current", "Medical Gases"])
def test_sgh_columns_stay_as_they_were(rec, sheet):
    f = add_file(rec, "sgh-boq.xlsx", real(SGH), actor="engineer").id
    p = boq.preview(rec, f, sheet)
    assert p["header_guess"] == 3
    assert p["columns_guess"] == {
        "code": "A",
        "description": "B",
        "unit": "C",
        "quantity": "D",
        "rate": "E",
        "amount": "F",
    }
