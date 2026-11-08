"""Generated sample photos and plans; no private tender inputs."""

import io
from pathlib import Path

import pytest
from PIL import Image

from qsone import workspace
from qsone.records import files, ocr, regions
from qsone.records.mapping import store
from tests.samples import sample_pdf
from tests.test_project_map import drain


def sample_plan(*, prose=False, clustered=False):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    words = (
        ["Sample running text with many words in a complete sentence " * 3]
        if prose
        else ["ROOM A", "3000", "ROOM B", "4500", "1200"]
    )
    reader = PdfReader(io.BytesIO(sample_pdf([words])))
    writer = PdfWriter()
    page = writer.add_page(reader.pages[0])
    page.mediabox.upper_right = (1200, 800)
    stream = DecodedStreamObject()
    stream.set_data(
        page.get_contents().get_data()
        + (
            b""
            if clustered
            else b"\nq 1 0 0 1 500 -300 cm\n" + page.get_contents().get_data() + b"\nQ\n"
        )
        + b"\n"
        + b"\n".join(f"{i * 10} 100 m {i * 10} 600 l S".encode() for i in range(80))
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize("extension", ["png", "jpeg"])
def test_photo_is_read_and_has_preview(rec, monkeypatch, extension):
    out = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(out, format=extension.upper())
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda *a: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(
        ocr,
        "read_image",
        lambda *a, **kw: ocr.Page([ocr.Word("Sample", [1, 2, 30, 12], 95)], False),
    )
    f = files.add_file(rec, "sample." + extension, out.getvalue(), actor="engineer")
    drain(rec)
    assert files.file_info(rec, f.id).status == "read"
    assert store.detail(rec, f.id)["read_how"] == "ocr"
    assert workspace.page_count(rec, f.id) == 1
    assert ocr.png_size(workspace.page_image(rec, f.id, 1, 240)) == (240, 160)
    assert regions.page_boxes(rec, f.id, 1)["width"] == 120
    with rec.read() as c:
        assert (
            '"box": [1, 2, 30, 12]'
            in c.execute("SELECT locator FROM chunks WHERE file_id=?", (f.id,)).fetchone()[0]
        )


def test_vector_plan_without_title_block_is_drawing(rec):
    data = sample_plan()
    f = files.add_file(rec, "sample-plan.pdf", data, actor="engineer")
    # Inspect directly: generated vector plans need no fake OCR or network.
    from qsone.records.mapping import drawing_map

    with rec.write("one") as c:
        store.write(c, rec, "map_files", {"file_id": f.id, "scanned_pages": []})
    drawing_map.populate(rec, f.id, data)
    assert store.detail(rec, f.id)["ai_kind"] == "drawing"
    assert len(store.detail(rec, f.id)["sheets"]) == 1


def test_prose_on_large_sheet_is_not_a_drawing(rec):
    from qsone.records.mapping import drawing_map

    data = sample_plan(prose=True)
    f = files.add_file(rec, "sample-prose.pdf", data, actor="engineer")
    with rec.write("one") as c:
        store.write(c, rec, "map_files", {"file_id": f.id, "scanned_pages": []})
    assert drawing_map.read(rec, files.file_info(rec, f.id), data) == []


def test_drop_report_uses_local_drawing_detection(rec):
    from qsone.records import report

    f = files.add_file(rec, "sample-plan.pdf", sample_plan(), actor="engineer")
    with rec.read() as c:
        row = report._files(c, [f.id])[0]
    assert report._what(rec, row)["label"] == "drawings"


def test_document_with_one_diagram_keeps_document_kind(rec):
    from pypdf import PdfReader, PdfWriter

    from qsone.records import report
    from qsone.records.mapping import drawing_map

    writer = PdfWriter()
    writer.append(
        PdfReader(
            io.BytesIO(
                sample_pdf(
                    [
                        ["Sample specifications running text in complete sentences " * 4],
                        ["Sample conditions running text in complete sentences " * 4],
                    ]
                )
            )
        )
    )
    writer.append(PdfReader(io.BytesIO(sample_plan())))
    out = io.BytesIO()
    writer.write(out)
    f = files.add_file(rec, "sample-specifications.pdf", out.getvalue(), actor="engineer")
    drawing_map.populate(rec, f.id, out.getvalue())
    assert store.detail(rec, f.id)["ai_kind"] != "drawing"
    with rec.read() as c:
        row = report._files(c, [f.id])[0]
    assert report._what(rec, row)["label"] == "specs"


def test_title_block_words_in_running_text_are_not_a_drawing(rec):
    from qsone.records.mapping import drawing_map

    data = sample_pdf(
        [
            [
                "SHEET NO: A-101",
                "TITLE: SAMPLE SPECIFICATIONS",
                "This is sample running prose in a technical specification paragraph " * 4,
            ]
        ]
    )
    f = files.add_file(rec, "sample.pdf", data, actor="engineer")
    assert drawing_map.read(rec, files.file_info(rec, f.id), data) == []


def test_short_labels_clustered_in_one_corner_are_not_a_drawing(rec):
    from qsone.records.mapping import drawing_map

    data = sample_plan(clustered=True)
    f = files.add_file(rec, "sample-table.pdf", data, actor="engineer")
    assert drawing_map.read(rec, files.file_info(rec, f.id), data) == []


def test_locally_identified_boq_page_is_not_a_drawing(rec):
    from qsone.records.mapping import drawing_map

    data = sample_plan()
    f = files.add_file(rec, "sample-boq.pdf", data, actor="engineer")
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_tables",
            {
                "file_id": f.id,
                "locator": {"page": 1},
                "header": ["Quantity", "Rate"],
                "row_count": 5,
                "looks_like_boq": 1,
                "column_guess": {"quantity": "A", "rate": "B"},
            },
        )
    assert drawing_map.read(rec, files.file_info(rec, f.id), data) == []


def test_a3_vector_heavy_plan_with_clustered_labels_is_drawing(rec):
    import pdfplumber
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, NameObject

    from qsone.records.mapping import drawing_map

    # Sample A3 portrait: thousands of paths and only ~113 text characters,
    # with all 29 short labels in one narrow corner column.
    reader = PdfReader(io.BytesIO(sample_pdf([[f"R{n:03}" for n in range(29)]])))
    writer = PdfWriter()
    page = writer.add_page(reader.pages[0])
    page.mediabox.upper_right = (842, 1191)
    stream = DecodedStreamObject()
    paths = []
    for n in range(3000):
        x, y = 40 + n % 60 * 12, 200 + n // 60 * 14
        paths.append(f"{x} {y} m {x + 8} {y + 5} l S".encode())
    stream.set_data(page.get_contents().get_data() + b"\n" + b"\n".join(paths))
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    data = out.getvalue()
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        measured = pdf.pages[0]
        assert (measured.width, measured.height) == (842, 1191)
        assert len(measured.lines) == 3000
        assert len(measured.extract_text_lines()) == 29
        assert len(measured.chars) == 116
        assert max(w["x1"] for w in measured.extract_words()) < measured.width * 0.25

    f = files.add_file(rec, "sample-a3-plan.pdf", data, actor="engineer")
    assert len(drawing_map.read(rec, files.file_info(rec, f.id), data)) == 1
    drawing_map.populate(rec, f.id, data)
    detail = store.detail(rec, f.id)
    assert len(detail["sheets"]) == 1
    assert detail["ai_kind"] == "drawing"
