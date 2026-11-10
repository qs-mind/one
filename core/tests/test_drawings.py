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
    executable.write_text("fixture", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("QSONE_DRAWINGS", str(executable))
    assert drawings.find_binary() == executable

    def timeout(*args, **kwargs):
        assert kwargs["input"] == b"AC1032"
        assert kwargs["timeout"] == 30
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(drawings.subprocess, "run", timeout)
    assert drawings.read_drawing("sample.dwg", b"AC1032").note == "FILE_DRAWING_TIMEOUT"


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


def test_title_rejects_product_time_and_long_revision():
    assert drawings._value("number", "RJ-45") is None
    assert drawings._value("scale", "11:07") is None
    assert drawings._value("scale", "NTS") == "NTS"
    assert drawings._value("revision", "PROJECT NAME") is None


def test_keyboard_font_decoding_is_style_scoped():
    from qsone.records.drawings.arabic import decode_text

    row = {"text": "Hgfdf", "raw_text": "Hgfdf", "font_file": "arabic.shx"}
    assert decode_text(row)["text"] == "البيب"
    assert decode_text({**row, "font_file": "arial.ttf"})["text"] == "Hgfdf"
    assert decode_text({**row, "font_file": "simplex.shx"})["text"] == "Hgfdf"
    inline = decode_text(
        {
            "text": "x",
            "raw_text": r"{\Farabic.shx;Hgfdf} {\FArial;ABC}",
            "font_file": "arial.ttf",
        }
    )
    assert inline["text"] == "البيب ABC"
    assert inline["raw_text"].startswith("{")


def test_room_requires_one_room_name_and_deduplicates():
    outline = {"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]], "handle": "1"}

    def sheet(texts, outlines=None):
        return drawings.sheets_from_drawing(
            drawings.Drawing(
                texts=[{"text": t, "x": x, "y": y} for t, x, y in texts],
                closed=outlines or [outline],
            )
        )[0]

    assert sheet([("RJ-45", 1, 1), ("D1", 2, 2), ("NOTE PROVIDE CABLE", 3, 3)]).rooms == []
    assert sheet([("OFFICE", 1, 1), ("KITCHEN", 2, 2)]).rooms == []
    assert len(sheet([("OFFICE", 1, 1)], [outline, dict(outline)]).rooms) == 1
    assert sheet([("OFFICE", 1, 1)], [{**outline, "layer": "TITLE-FRAME"}]).rooms == []


def test_frame_text_outside_global_corner_and_named_counts():
    d = drawings.Drawing(
        texts=[
            {"text": "SHEET NO", "x": 10, "y": 50, "height": 2, "block": "TITLE_A2"},
            {"text": "A-210", "x": 30, "y": 50, "height": 2, "block": "TITLE_A2"},
            {"text": "TITLE", "x": 10, "y": 40, "height": 2, "block": "TITLE_A2"},
            {"text": "SAMPLE PLAN", "x": 10, "y": 35, "height": 2, "block": "TITLE_A2"},
            {"text": "NOTE", "x": 10000, "y": 10000},
        ],
        inserts=[
            {"block": "TITLE_A2", "x": 0, "y": 0},
            {"block": "*U1", "x": 1, "y": 1},
            {"block": "SOCKET", "x": 2, "y": 2, "container": "LEGEND"},
            {"block": "SOCKET", "x": 3, "y": 3},
        ],
    )
    s = drawings.sheets_from_drawing(d)[0]
    assert (s.number, s.title) == ("A-210", "SAMPLE PLAN")
    assert s.counts == {"SOCKET": 1}


def test_clean_filename_number_fallback(monkeypatch):
    monkeypatch.setattr(drawings, "read_drawing", lambda *a: drawings.Drawing())
    s = drawings.read_sheets("EL-021.dwg", b"synthetic")[0]
    assert s.number == "EL-021"
    assert s.source["number"] == {"source": "file name", "name": "EL-021.dwg"}
    assert drawings.read_sheets("RJ-45.dwg", b"synthetic")[0].number is None


def test_embedded_excel_keeps_cell_source():
    import io

    import xlwt

    book = xlwt.Workbook()
    table = book.add_sheet("Synthetic schedule")
    table.write(0, 0, "SAMPLE LOAD")
    table.write(0, 1, 123)
    data = io.BytesIO()
    book.save(data)
    d = drawings.Drawing(
        embedded=[
            {
                "compound_hex": data.getvalue().hex(),
                "handle": "ABC",
                "layout": "Layout1",
                "x": 10,
                "y": 20,
            }
        ]
    )
    drawings._embedded_texts(d)
    assert [t["text"] for t in d.texts] == ["SAMPLE LOAD", "123.0"]
    assert drawings._source(d.texts[1])["table_cell"] == [0, 1]
    assert drawings._source(d.texts[1])["embedded_sheet"] == "Synthetic schedule"


def test_outline_larger_than_extents_is_not_room():
    d = drawings.Drawing(
        extents=[0, 0, 10, 10],
        texts=[{"text": "OFFICE", "x": 1, "y": 1}],
        closed=[{"vertices": [[-100, -100], [100, -100], [100, 100], [-100, 100]]}],
    )
    assert drawings.sheets_from_drawing(d)[0].rooms == []


def test_count_uses_effective_parent_and_excludes_legend_region():
    d = drawings.Drawing(
        inserts=[
            {"block": "*U99", "effective_name": "SAMPLE_SOCKET", "x": 20, "y": 20},
            {"block": "SAMPLE_SOCKET", "x": 3, "y": 3},
        ],
        texts=[{"text": "LEGEND", "x": 1, "y": 8}],
        closed=[{"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
    )
    s = drawings.sheets_from_drawing(d)[0]
    assert s.counts == {"SAMPLE_SOCKET": 1}
    assert s.source["counts"][0]["x"] == 20


def test_decoding_is_idempotent_and_bigfont_does_not_change_ascii():
    from qsone.records.drawings.arabic import decode_text

    row = {"text": "Hgfdf", "raw_text": "Hgfdf", "font_file": "xarb.shx"}
    decoded = decode_text(row)
    assert decode_text(decoded) == decoded
    normal = {"text": "BY CONTRACTOR", "font_file": "romans.shx", "big_font_file": "hassano.shx"}
    assert decode_text(normal)["text"] == "BY CONTRACTOR"


def test_xlsx_package_and_scale_in_cell_are_not_sheet_scale():
    import io

    import openpyxl

    book = openpyxl.Workbook()
    book.active["A1"] = "SAMPLE 01:03 INDEX"
    data = io.BytesIO()
    book.save(data)
    d = drawings.Drawing(
        embedded=[{"package_hex": data.getvalue().hex(), "handle": "1", "x": 0, "y": 0}]
    )
    drawings._embedded_texts(d)
    assert d.texts[0]["text"] == "SAMPLE 01:03 INDEX"
    assert drawings.sheets_from_drawing(d)[0].scale is None


def test_unnamed_border_frame_and_cell_blocks_cross_cell_value():
    rows = [
        {"text": "SHEET NO", "x": 5, "y": 10, "height": 1, "block": "BORDER_SAMPLE"},
        {"text": "A-211", "x": 15, "y": 10, "height": 1, "block": "BORDER_SAMPLE"},
    ]
    d = drawings.Drawing(
        texts=rows,
        inserts=[{"block": "BORDER_SAMPLE", "x": 0, "y": 0, "bounds": [0, 0, 100, 100]}],
        layouts=[{"name": "Model", "paper_size": [100, 100]}],
        closed=[{"vertices": [[0, 0], [10, 0], [10, 20], [0, 20]]}],
    )
    assert drawings.sheets_from_drawing(d)[0].number is None
    d.closed = []
    assert drawings.sheets_from_drawing(d)[0].number == "A-211"


def test_title_value_cannot_cross_frame_grid_line():
    d = drawings.Drawing(
        texts=[
            {"text": "SHEET NO", "x": 5, "y": 10, "height": 1, "block": "TITLE_SAMPLE"},
            {"text": "A-211", "x": 15, "y": 10, "height": 1, "block": "TITLE_SAMPLE"},
        ],
        inserts=[{"block": "TITLE_SAMPLE", "x": 0, "y": 0}],
        segments=[{"start": [10, 0], "end": [10, 20]}],
    )
    assert drawings.sheets_from_drawing(d)[0].number is None


def test_non_plan_room_labels_are_not_rooms():
    d = drawings.Drawing(
        texts=[
            {"text": "OFFICE", "x": 1, "y": 1},
            {"text": "DRAWING TITLE: SAMPLE RISER DIAGRAM", "x": 90, "y": 5},
        ],
        closed=[{"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
    )
    assert drawings.sheets_from_drawing(d)[0].rooms == []


def test_truncated_evidence_does_not_claim_complete_counts():
    d = drawings.Drawing(
        omitted={"inserts": 1, "closed": 1},
        inserts=[{"block": "DOOR", "x": 1, "y": 1}],
        texts=[{"text": "OFFICE", "x": 1, "y": 1}],
        closed=[{"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
    )
    sheet = drawings.sheets_from_drawing(d)[0]
    assert sheet.counts_complete is False
    assert sheet.rooms_complete is False
    assert sheet.rooms == []


def test_keyboard_font_preserves_cad_controls():
    from qsone.records.drawings.arabic import decode_text

    row = {"text": "%%UHgfdf%%U %%c12", "font_file": "xarb.shx"}
    assert decode_text(row)["text"] == "البيب Ø12"


def test_decoded_text_reaches_search_and_report(rec, monkeypatch):
    import json
    import subprocess

    from qsone.records import report
    from qsone.records.files import add_file
    from qsone.records.search import search

    raw = {
        "format": "dxf",
        "texts": [
            {
                "text": "l;jF",
                "raw_text": "l;jF",
                "font_file": "xarb.shx",
                "handle": "AA",
                "x": 1,
                "y": 1,
                "block": "TITLE_SAMPLE",
            }
        ],
        "inserts": [
            {
                "block": "TITLE_SAMPLE",
                "handle": "BB",
                "x": 0,
                "y": 0,
                "attributes": [{"tag": "TITLE", "value": "l;jF", "handle": "AA"}],
            }
        ],
    }
    monkeypatch.setattr(drawings, "find_binary", lambda: Path("/synthetic-reader"))
    monkeypatch.setattr(
        drawings.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, json.dumps(raw).encode(), b""),
    )
    info = add_file(rec, "A-212.dxf", (FIXTURES / "title.dxf").read_bytes(), actor="engineer")
    hits = search(rec, "مكتب").hits
    assert any(h.file_id == info.id for h in hits)
    rendered = json.dumps(report.make(rec, [info.id]), ensure_ascii=False)
    assert "مكتب" in rendered
    assert "l;jF" not in rendered


def test_embedded_workbook_repeats_do_not_exhaust_cell_budget():
    import io

    import openpyxl

    book = openpyxl.Workbook()
    book.active["A1"] = "SAMPLE SCHEDULE"
    stream = io.BytesIO()
    book.save(stream)
    d = drawings.Drawing(
        embedded=[
            {
                "package_hex": stream.getvalue().hex(),
                "handle": str(i),
                "layout": "Model",
                "x": 0,
                "y": 0,
            }
            for i in range(2)
        ]
    )
    drawings._embedded_texts(d)
    assert len(d.texts) == 1


def test_diagram_file_does_not_claim_room_count():
    d = drawings.Drawing(
        name="SAMPLE RISER DIAGRAM.dwg",
        texts=[{"text": "OFFICE", "x": 1, "y": 1}],
        closed=[{"vertices": [[0, 0], [10, 0], [10, 10], [0, 10]]}],
    )
    assert drawings.sheets_from_drawing(d)[0].rooms == []


def test_dynamic_wrapper_and_repeated_instances_count_once():
    inserts = [
        dict(block="BREAKER", effective_name="BREAKER", handle="1", x=0, y=0),
        dict(block="A$C09D76011", container="BREAKER", context="/BREAKER:1", handle="2", x=0, y=0),
        dict(block="BREAKER", effective_name="BREAKER", handle="3", x=0, y=0),
    ]
    sheet = drawings.sheets_from_drawing(drawings.Drawing(inserts=inserts))[0]
    assert sheet.counts == {"BREAKER": 2}


def test_duplicate_insert_rows_keep_effective_name_and_context_instances():
    rows = [
        dict(block="A$C123", handle="1", instance="Model:1", effective_name="BREAKER", x=0, y=0),
        dict(block="A$C123", handle="1", instance="Model:1", x=0, y=0),
        dict(block="DOOR", handle="2", context="/ROOM:A", x=0, y=0),
        dict(block="DOOR", handle="2", context="/ROOM:B", x=0, y=0),
    ]
    assert drawings.sheets_from_drawing(drawings.Drawing(inserts=rows))[0].counts == {
        "BREAKER": 1,
        "DOOR": 2,
    }
