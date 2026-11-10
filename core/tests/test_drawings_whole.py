"""A drawing is read whole or says what it did not read: a damaged Excel sheet inside, two
different sheets inside, a table in a block placed twice, texts cut short, rows not kept.

Fakes only: the fake drawing reader prints the JSON the real one would; every text is sample
data."""

import io
import json
import zipfile

from qsone import copy
from qsone.records.extract import extract
from tests import test_readers_phase1 as phase1
from tests.test_readers_phase1 import drawing

fake_reader = phase1.fake_reader  # the fixture

DWG = b"AC1032" + b"\0" * 64


def xlsx(rows: list[list]) -> bytes:
    import openpyxl

    book = openpyxl.Workbook()
    for row in rows:
        book.active.append(row)
    data = io.BytesIO()
    book.save(data)
    return data.getvalue()


def broken_xml(package: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as old, zipfile.ZipFile(out, "w") as new:
        for item in old.infolist():
            body = b"<workbook><sheets" if item.filename == "xl/workbook.xml" else old.read(item)
            new.writestr(item, body)
    return out.getvalue()


def said(x) -> list[tuple[str, str]]:
    return [(p["part"]["en"], p["why"]["en"]) for p in x.unread]


def by_locator(x) -> dict[str, str]:
    return {json.dumps(p.locator, ensure_ascii=False): p.text for p in x.pieces}


def test_a_damaged_excel_sheet_inside_is_named_not_a_crash(fake_reader):
    damaged_cfb = bytes.fromhex("d0cf11e0a1b11ae1") + b"\x07" * 1024
    fake_reader(
        drawing(
            texts=[{"text": "A-101 - sample", "handle": "1"}],
            embedded=[
                {"handle": "E1", "streams": ["Workbook"], "compound_hex": damaged_cfb.hex()},
                {
                    "handle": "E2",
                    "streams": ["Package"],
                    "package_hex": broken_xml(xlsx([["Door", 1]])).hex(),
                },
            ],
        )
    )
    x = extract("plan - sample.dwg", DWG)
    assert (x.status, x.note) == ("partly_read", "FILE_PARTLY_READ")
    assert ("Excel sheets inside: 2", copy.UNREAD_WHY_SHEETS["en"]) in said(x)
    assert [p.text for p in x.pieces] == ["A-101 - sample"]


def test_two_different_excel_sheets_inside_keep_every_cell(fake_reader):
    header = ["Door", "Qty", "Unit"]
    ground = xlsx([header, ["D1", 4, "No."]])
    first = xlsx([header, ["D7", 4, "No."]])
    place = {"layout": "Layout1", "streams": ["Package"], "x": 0, "y": 0}
    fake_reader(
        drawing(
            embedded=[
                place | {"handle": "A", "package_hex": ground.hex()},
                place | {"handle": "B", "package_hex": first.hex()},
                place | {"handle": "C", "package_hex": ground.hex()},  # the same sheet again
            ]
        )
    )
    x = extract("doors - sample.dwg", DWG)
    got = by_locator(x)
    row = '{{"sheet": "Layout1", "handle": "{}", "row": {}, "embedded_sheet": "Sheet"}}'
    assert got[row.format("A", 1)] == "Door | Qty | Unit"
    assert got[row.format("A", 2)] == "D1 | 4 | No."
    assert got[row.format("B", 1)] == "Door | Qty | Unit"
    assert got[row.format("B", 2)] == "D7 | 4 | No."
    assert not any('"handle": "C"' in k for k in got)
    assert x.unread == []


def test_a_table_in_a_block_placed_twice_shows_each_cell_once(fake_reader):
    cell = {"kind": "TABLE", "handle": "T1", "layout": "Model", "block": "FRAME"}
    texts = [
        cell | {"context": context, "text": text, "table_cell": at}
        for context in ("/FRAME:1A", "/FRAME:2B")
        for text, at in (("Rev", [0, 0]), ("Date", [0, 1]), ("B", [1, 0]), ("2026-11-01", [1, 1]))
    ]
    fake_reader(drawing(texts=texts))
    x = extract("frames - sample.dwg", DWG)
    rows = [p.text for p in x.pieces if p.locator.get("handle") == "T1"]
    assert rows == ["Rev | Date", "B | 2026-11-01"]


def test_a_text_cut_short_and_sheets_not_kept_are_named(fake_reader):
    fake_reader(
        drawing(
            texts=[{"text": "GENERAL NOTES - sample", "handle": "1"}],
            cut_texts=2,
            omitted={"embedded": 1},
            problems=[{"code": "output-limit"}],
        ),
        code=2,
    )
    x = extract("notes - sample.dwg", DWG)
    assert (x.status, x.note) == ("partly_read", "FILE_PARTLY_READ")
    assert ("Long texts cut short: 2", copy.UNREAD_WHY_CUT_SHORT["en"]) in said(x)
    assert ("Pictures or Excel sheets inside: 1", copy.UNREAD_WHY_TOO_MANY["en"]) in said(x)
    assert all(p["part"]["ar"] and p["why"]["ar"] for p in x.unread)
