from qsone.records import drawings, files
from qsone.records.mapping import store
from tests.samples import sample_pdf
from tests.test_project_map import drain


def test_revision_pairing(rec, monkeypatch):
    from qsone.records.mapping import drawing_map

    first = files.add_file(rec, "first.pdf", sample_pdf([["sample A"]]), actor="engineer")
    second = files.add_file(rec, "second.pdf", sample_pdf([["sample B"]]), actor="engineer")
    sheets = [drawings.Sheet(number="A-101", title="Sample plan", revision="A")]
    monkeypatch.setattr(drawing_map, "read", lambda *args: sheets)
    drain(rec)
    sheets[0].revision = "B"
    # Explicitly refresh the second file after the fake reader changes revision.
    drawing_map.populate(rec, second.id, b"")
    assert store.detail(rec, first.id)["sheets"][0]["number"] == "A-101"
    links = store.entries(rec, "links")["links"]
    assert len(links) == 1
    assert links[0]["kind"] == "revision" and links[0]["by"] == "one"


def test_dwg_fixture_in_map(rec):
    from pathlib import Path

    data = (Path(__file__).parent / "fixtures/drawings/test-plan.dwg").read_bytes()
    f = files.add_file(rec, "sample.dwg", data, actor="engineer")
    drain(rec)
    sheets = store.detail(rec, f.id)["sheets"]
    assert next(s for s in sheets if s["sheet"] == "Model")["counts"]["DOOR"] == 3


def test_scanned_drawing_uses_stored_words(rec, monkeypatch):
    from pathlib import Path

    from qsone.records import ocr

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda *a: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(
        ocr,
        "read_image",
        lambda *a, **kw: ocr.Page(
            [
                ocr.Word("SHEET NO: A-101", [400, 750, 580, 760], 95),
                ocr.Word("TITLE: SAMPLE FLOOR PLAN", [400, 770, 580, 780], 95),
                ocr.Word("SCALE 1:50", [400, 790, 580, 800], 95),
            ],
            False,
        ),
    )
    f = files.add_file(rec, "sample-scan.pdf", sample_pdf([[]]), actor="engineer")
    drain(rec)
    sheet = store.detail(rec, f.id)["sheets"][0]
    assert sheet["number"] == "A-101" and sheet["title"] == "SAMPLE FLOOR PLAN"
    assert sheet["source"]["number"]["box"] == [400, 750, 580, 760]
    assert sheet["source"]["page"] == 1
