"""Synthetic revision PDFs only; no AI, external programs or real tender files."""

import numpy as np
import pytest

from qsone.records import files
from qsone.records.compare import compare_files, overlay_pixels, pair_pages


def pdf(pages):
    typst = pytest.importorskip("typst")
    source = "#set page(width: 200pt, height: 200pt, margin: 10pt)\n"
    return typst.compile((source + "\n#pagebreak()\n".join(pages)).encode())


def add(rec, pages, name="sample.pdf"):
    return files.add_file(rec, name, pdf(pages), actor="engineer").id


def test_reordered_revision_changed_word_and_added_page(rec):
    old = add(rec, ["A-101\n\nConcrete grade C30", "S-201\n\nFoundation sample"])
    new = add(
        rec, ["S-201\n\nFoundation sample", "A-101\n\nConcrete grade C40", "A-102\n\nAdded sample"]
    )
    result = compare_files(rec, old, new)
    assert result["unchanged"] == 1
    assert [(p["old"]["page"], p["new"]["page"], p["method"]) for p in result["pairs"]] == [
        (1, 2, "sheet"),
        (2, 1, "sheet"),
    ]
    changed = result["changed"][0]
    assert changed["added"] == ["C40"] and changed["removed"] == ["C30"]
    assert changed["old"]["file_id"] == old and changed["new"]["file_id"] == new
    assert set(changed["summary"]) == {"en", "ar"}
    assert [p["page"] for p in result["unpaired_new"]] == [3]


def test_pairing_title_arabic_and_order():
    old = ["لوحة رقم ١٢\nأساسات", "Sample title\nOld words", ""]
    new = ["Sample title\nNew words", "لوحة رقم ١٢\nأساسات", ""]
    assert pair_pages(old, new) == [(1, 2, "sheet"), (2, 1, "title"), (3, 3, "order")]


def test_overlay_only_colours_changed_pixels():
    old = np.full((30, 30, 4), 255, dtype=np.uint8)
    new = old.copy()
    old[5, 2:20, :3] = 0
    new[8, 2:20, :3] = 0
    old[20, 2:20, :3] = new[20, 2:20, :3] = 0
    overlay, count = overlay_pixels(old, new)
    assert count == 36
    assert np.all(overlay[5, 2:20, :3] == [255, 0, 0])
    assert np.all(overlay[8, 2:20, :3] == [0, 160, 0])
    unchanged = np.all(old == new, axis=2)
    assert np.array_equal(overlay[unchanged], old[unchanged])


def test_drawing_line_change_and_identical(rec):
    old = add(rec, ["A-101\n\nSample drawing\n#line(length: 50pt)"])
    new = add(rec, ["A-101\n\nSample drawing\n#line(length: 80pt)"])
    changed = compare_files(rec, old, new)["changed"][0]
    assert changed["overlay"] and changed["pixels_changed"] > 0
    assert changed["added"] == changed["removed"] == []
    same = compare_files(rec, old, old)
    assert same["unchanged"] == 1 and same["changed"] == []


def test_routes_and_private_overlay(data_dir):
    from fastapi.testclient import TestClient

    from qsone.app import create_app
    from tests.conftest import AUTH, SECRET

    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        project = client.post("/projects", json={"name": "Sample"}, headers=AUTH).json()["id"]
        rec = client.app.state.projects.get(project)
        old = add(rec, ["A-101\n\n#line(length: 50pt)"])
        new = add(rec, ["A-101\n\n#line(length: 80pt)"])
        base = f"/projects/{project}/files/compare"
        args = {"old_file_id": old, "new_file_id": new}
        response = client.post(base, json=args, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["changed"][0]["overlay"]
        params = args | {"old_page": 1, "new_page": 1, "width": 600}
        image = client.get(base + "/overlay", params=params, headers=AUTH)
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
        assert "no-store" in image.headers["cache-control"]
        assert (
            client.get(base + "/overlay", params=params | {"old_page": 8}, headers=AUTH).status_code
            == 404
        )
        assert (
            client.get(base + "/overlay", params=params | {"width": 601}, headers=AUTH).status_code
            == 422
        )
        assert client.post(base, json=args).status_code == 401
        assert (
            client.post(base, json=args | {"old_file_id": "missing"}, headers=AUTH).status_code
            == 404
        )


@pytest.mark.anyio
async def test_lead_tool_is_cited_and_in_documents(rec):
    from qsone.engine.agents import lead_spec
    from qsone.engine.tool_groups import group_of
    from qsone.engine.tools import call
    from tests.fakes_tools import tool_ctx

    old = add(rec, ["Sample specification\n\nGrade C30"])
    new = add(rec, ["Sample specification\n\nGrade C40"])
    assert "compare_files" in lead_spec().tools
    assert group_of("compare_files") == "documents"
    result = await call("compare_files", {"old_file_id": old, "new_file_id": new}, tool_ctx(rec))
    assert old in result and new in result and "C40" in result
    assert '"page": 1' in result


def test_generated_overlay_changes_only_at_the_extended_line():
    from qsone.records.compare import _images

    old = pdf(["#place(top + left, dx: 20pt, dy: 80pt, line(length: 50pt))"])
    new = pdf(["#place(top + left, dx: 20pt, dy: 80pt, line(length: 80pt))"])
    overlay, count, drawing = _images(old, new, 1, 1, 600)
    green = np.all(overlay[:, :, :3] == [0, 160, 0], axis=2)
    red = np.all(overlay[:, :, :3] == [255, 0, 0], axis=2)
    ys, xs = np.where(green)
    assert drawing and count == np.count_nonzero(green)
    assert not np.any(red)
    # 10pt page margin + placed origin + old/new lengths, at 3px/pt.
    assert xs.min() >= 239 and xs.max() <= 330
    assert ys.min() >= 268 and ys.max() <= 272
    same, count, _ = _images(new, new, 1, 1, 600)
    assert count == 0
    assert np.array_equal(same[~green], overlay[~green])


def test_titles_duplicates_order_and_removed_page(rec):
    assert pair_pages(["Same", "Same"], ["Same", "Same"]) == [(1, 1, "order"), (2, 2, "order")]
    old = add(rec, ["A-101\n\nSample one", "S-201\n\nSample two"])
    new = add(rec, ["S-201\n\nSample two"], "other-sample.pdf")
    result = compare_files(rec, old, new)
    assert result["unchanged"] == 1 and result["changed"] == []
    assert result["unpaired_old"][0]["page"] == 1
    assert result["unpaired_new"] == []


def test_non_pdf_and_missing_files_are_refused(rec):
    from qsone.records.project import RecordsError

    text = files.add_file(rec, "sample.txt", b"Sample", actor="engineer").id
    with pytest.raises(RecordsError) as error:
        compare_files(rec, text, text)
    assert error.value.status == 409
    with pytest.raises(RecordsError) as error:
        compare_files(rec, "missing", text)
    assert error.value.status == 404


def test_page_box_alignment_does_not_stretch_the_drawing():
    from qsone.records.compare import _images

    drawing = "#place(top + left, dx: 20pt, dy: 80pt, line(length: 50pt))"
    old = pdf([drawing])
    new = pdf(["#set page(width: 300pt, height: 250pt)\n" + drawing])
    overlay, count, _ = _images(old, new, 1, 1, 600)
    assert overlay.shape == (500, 600, 4)
    assert count == 0  # same drawing in a larger blank page box, no stretching
