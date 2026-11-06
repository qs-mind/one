"""Synthetic drawing evidence only; no model providers."""

from pathlib import Path

import pytest

from qsone.records import drawings

FIXTURES = Path(__file__).parent / "fixtures" / "drawings"


def test_missing_reader(monkeypatch):
    monkeypatch.setattr(drawings, "find_binary", lambda: None)
    assert drawings.read_sheets("sample.dwg", b"AC1032") == []
    result = drawings.read_drawing("sample.dwg", b"AC1032")
    assert result.note == "FILE_DRAWINGS_MISSING"


def test_sample_dwg():
    sheets = drawings.read_sheets("test-plan.dwg", (FIXTURES / "test-plan.dwg").read_bytes())
    model = next(s for s in sheets if s.layout == "Model")
    assert model.counts == {"DOOR": 3, "WINDOW": 5, "COLUMN": 6}
    assert model.scale == "1:100"
    assert {r.name for r in model.rooms} >= {"LIVING", "BEDROOM", "KITCHEN"}
    assert model.source["scale"]["handle"]


def test_pdf_words():
    sheet = drawings.read_pdf_sheet(
        [
            {"text": "SHEET NO: A-101", "x0": 700, "top": 520, "x1": 790, "bottom": 530},
            {"text": "TITLE: GROUND FLOOR PLAN", "x0": 700, "top": 540, "x1": 790, "bottom": 550},
            {"text": "SCALE 1:50", "x0": 700, "top": 560, "x1": 790, "bottom": 570},
        ],
        (800, 600),
    )
    assert (sheet.number, sheet.title, sheet.scale) == ("A-101", "GROUND FLOOR PLAN", "1:50")
    assert sheet.source["number"]["box"] == [700, 520, 790, 530]
    assert sheet.rooms == []


def test_arabic_words():
    s = drawings.read_pdf_sheet(
        [
            {"text": "لوحة رقم: م-٢٠٣", "x0": 700, "top": 520, "x1": 790, "bottom": 530},
            {"text": "مقياس الرسم: ١:١٠٠", "x0": 700, "top": 540, "x1": 790, "bottom": 550},
        ],
        (800, 600),
    )
    assert s.number == "م-203"
    assert s.scale == "1:100"


def test_unknown_units_no_area():
    s = drawings.sheets_from_drawing(
        drawings.Drawing(
            texts=[{"text": "ROOM", "x": 1, "y": 1, "layout": "Model", "handle": "1"}],
            closed=[
                {"vertices": [[0, 0], [4, 0], [4, 3], [0, 3]], "layout": "Model", "handle": "2"}
            ],
        )
    )[0]
    assert s.rooms[0].area_m2 is None
    s = drawings.sheets_from_drawing(
        drawings.Drawing(
            units=6,
            texts=[{"text": "ROOM", "x": 1, "y": 1, "layout": "Model", "handle": "1"}],
            closed=[
                {"vertices": [[0, 0], [4, 0], [4, 3], [0, 3]], "layout": "Model", "handle": "2"}
            ],
        )
    )[0]
    assert s.rooms[0].area_m2 == pytest.approx(12)


@pytest.mark.parametrize(
    "name,number,scale", [("title.dxf", "A-101", "1:50"), ("arabic.dxf", "م-203", "1:100")]
)
def test_dxf_title(name, number, scale):
    s = next(s for s in drawings.read_sheets(name, (FIXTURES / name).read_bytes()) if s.number)
    assert s.number == number and s.scale == scale
    if name == "title.dxf":
        assert (s.title, s.revision, s.date) == ("GROUND FLOOR PLAN", "B", "2026-10-01")
        assert s.discipline_hint == "architecture"
        room = next(r for r in s.rooms if r.name == "OFFICE")
        assert room.area_m2 == pytest.approx(12)


def test_damaged_drawing():
    result = drawings.read_drawing("damaged.dxf", (FIXTURES / "damaged.dxf").read_bytes())
    assert result.problems or result.note


def test_upload_search_and_report(rec):
    import json

    from qsone.records import report
    from qsone.records.files import add_file

    for name in ("test-plan.dwg", "title.dxf"):
        info = add_file(rec, name, (FIXTURES / name).read_bytes(), actor="engineer")
        assert info.kind in ("dwg", "dxf") and info.pages >= 1
        assert info.status in ("read", "partly_read")
        with rec.read() as conn:
            rows = conn.execute(
                "SELECT text, locator FROM chunks WHERE file_id = ?", (info.id,)
            ).fetchall()
        assert rows
        assert all(
            "handle" in json.loads(locator) and "sheet" in json.loads(locator)
            for _, locator in rows
        )
        found = report.make(rec, [info.id])
        assert any("Drawing," in line["en"] for line in found["lines"])


def test_reader_env_and_timeout(monkeypatch, tmp_path):
    import subprocess

    executable = tmp_path / "reader"
    executable.write_text("fixture")
    executable.chmod(0o755)
    monkeypatch.setenv("QSONE_DRAWINGS", str(executable))
    assert drawings.find_binary() == executable

    def timeout(*args, **kwargs):
        assert kwargs["input"] == b"AC1032"
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(drawings.subprocess, "run", timeout)
    assert drawings.read_drawing("sample.dwg", b"AC1032").note == "FILE_UNREADABLE"


def test_layer_discipline_and_separate_title_labels():
    d = drawings.Drawing(
        layers=[{"name": "E-LIGHTING"}],
        texts=[
            {"text": "SHEET NO", "x": 250, "y": 20, "height": 2, "handle": "1"},
            {"text": "E-101", "x": 275, "y": 20, "height": 2, "handle": "2"},
        ],
        layouts=[{"name": "Model", "paper_size": [297, 210]}],
    )
    s = drawings.sheets_from_drawing(d)[0]
    assert s.number == "E-101"
    assert s.discipline_hint == "electrical"


def test_layer_only_hint():
    d = drawings.Drawing(
        texts=[{"text": "NOTE", "x": 0, "y": 0, "layer": "S-COLUMNS", "handle": "A"}]
    )
    s = drawings.sheets_from_drawing(d)[0]
    assert s.discipline_hint == "structure"
    assert s.source["discipline_hint"]["handle"] == "A"


def test_split_title_label():
    s = drawings.read_pdf_sheet(
        [
            {"text": "TITLE", "x0": 700, "top": 520, "x1": 730, "bottom": 530},
            {"text": "GROUND FLOOR PLAN", "x0": 700, "top": 535, "x1": 790, "bottom": 545},
        ],
        (800, 600),
    )
    assert s.title == "GROUND FLOOR PLAN"
    assert s.source["title"]["box"] == [700, 535, 790, 545]


def test_drawing_is_found_in_word_search(rec):
    from qsone.records.files import add_file
    from qsone.records.search import search

    info = add_file(rec, "sample.dwg", (FIXTURES / "test-plan.dwg").read_bytes(), actor="engineer")
    found = search(rec, "LIVING")
    assert any(h.file_id == info.id and h.locator.get("handle") for h in found.hits)


def test_room_uses_smallest_outline_and_pdf_vectors():
    sheet = drawings.read_pdf_sheet(
        [{"text": "OFFICE", "x0": 10, "top": 10, "x1": 20, "bottom": 20}],
        (800, 600),
        closed=[
            {
                "vertices": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "page": 1,
                "box": [0, 0, 100, 100],
            },
            {"vertices": [[0, 0], [40, 0], [40, 30], [0, 30]], "page": 1, "box": [0, 0, 40, 30]},
        ],
        metres_per_unit=0.1,
    )
    assert sheet.rooms[0].area_m2 == pytest.approx(12)
    assert sheet.rooms[0].source["outline"]["box"] == [0, 0, 40, 30]


def test_pdf_arabic_word_order():
    sheet = drawings.read_pdf_sheet(
        [
            {"text": "لوحة", "x0": 760, "top": 520, "x1": 790, "bottom": 530},
            {"text": "رقم", "x0": 735, "top": 520, "x1": 755, "bottom": 530},
            {"text": "م-٢٠٣", "x0": 700, "top": 520, "x1": 730, "bottom": 530},
        ],
        (800, 600),
    )
    assert sheet.number == "م-203"


def test_pdf_vector_source_is_kept_without_explicit_box():
    s = drawings.read_pdf_sheet(
        [{"text": "ROOM", "x0": 10, "top": 10, "x1": 20, "bottom": 20}],
        (800, 600),
        closed=[{"vertices": [[0, 0], [40, 0], [40, 30], [0, 30]]}],
    )
    assert s.rooms[0].source["outline"] == {"page": 1, "box": [0, 0, 40, 30]}
