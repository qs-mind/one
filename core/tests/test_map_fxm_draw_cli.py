"""Sample-only reproductions of sheet listing and upload-count regressions."""

from qsone.cli.__main__ import human_result, plain
from qsone.records import drawings, files
from qsone.records.mapping import store
from qsone.tools.project_map import MapArgs, drawing_evidence
from tests.samples import sample_pdf


def test_scanned_upload_is_added_and_labelled_files():
    uploads = [{"status": "read"} for _ in range(38)]
    uploads.append({"status": "unread", "note_key": "FILE_SCANNED_PAGES"})
    result = human_result({"uploads": uploads})
    assert result["added"] == 39
    assert result["failed"] == 0
    assert "Files added: 39" in plain(result, "en")
    assert "الملفات المضافة: 39" in plain(result, "ar")


def test_title_field_wins_over_view_label():
    drawing = drawings.Drawing(
        name="EL-000.dxf",
        layouts=[{"name": "PLAN"}],
        inserts=[
            {
                "block": "TITLEBLOCK",
                "layout": "PLAN",
                "x": 0,
                "y": 0,
                "attributes": [
                    {"tag": "TOP-TITLE", "value": "PLAN"},
                    {"tag": "DRAWING_TITLE", "value": "SAMPLE PANEL SCHEDULE"},
                    {"tag": "SHEET_NO", "value": "EL-000"},
                ],
            }
        ],
    )
    sheet = next(s for s in drawings.sheets_from_drawing(drawing) if s.layout == "PLAN")
    assert sheet.title == "SAMPLE PANEL SCHEDULE"


def test_sheet_paging_starts_at_zero_and_retains_model_counts(rec):
    f = files.add_file(rec, "sample.pdf", sample_pdf([["sample"]]), actor="test")
    with rec.write("one") as c:
        for i in reversed(range(18)):
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": f.id,
                    "sheet": f"Layout{i}",
                    "number": f"EL-{i:03}",
                    "title": "Sample schedule",
                    "counts": {},
                },
            )
        store.write(
            c,
            rec,
            "map_sheets",
            {
                "file_id": f.id,
                "sheet": "Model",
                "number": "EL-000",
                "counts": {"MCCB": 3},
            },
        )
    first = drawing_evidence(rec, MapArgs(mode="sheets", limit=10))
    second = drawing_evidence(rec, MapArgs(mode="sheets", limit=10, page=2))
    assert first["total"] == 18
    assert [r["number"] for r in first["sheets"] + second["sheets"]] == [
        f"EL-{i:03}" for i in range(18)
    ]
    assert first["next_page"] == 2 and second["next_page"] is None
    assert drawing_evidence(rec, MapArgs(mode="counts"))["project_total"] == 3


async def test_long_sheet_names_page_without_dispatcher_cut(rec):
    import json

    from qsone.engine.tools import call
    from tests.fakes_tools import tool_ctx

    f = files.add_file(rec, "sample.pdf", sample_pdf([["sample"]]), actor="test")
    with rec.write("one") as c:
        for i in range(18):
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": f.id,
                    "sheet": f"PLAN{i}",
                    "number": f"EL-{i:03}",
                    "title": "جدول عينة " * 40,
                },
            )
    found, page = [], 1
    while page is not None:
        result = await call("project_map", {"mode": "sheets", "page": page}, tool_ctx(rec))
        assert "cut at 8 KB" not in result
        data = json.loads(result[result.index("{") : result.rindex("}") + 1])
        found.extend(r["number"] for r in data["sheets"])
        page = data["next_page"]
    assert found == [f"EL-{i:03}" for i in range(18)]


def test_synthetic_dxf_schedule_title_field():
    from pathlib import Path

    source = (Path(__file__).parent / "fixtures/drawings/title.dxf").read_text()
    # Both attributes belong to the synthetic title block; the top label is a view.
    start = source.index("0\nATTRIB\n5\n29\n")
    end = source.index("0\nATTRIB\n5\n2a\n", start)
    title = source[start:end]
    generic = title.replace("GROUND FLOOR PLAN", "PLAN").replace("2\nTITLE\n", "2\nTOP-TITLE\n")
    explicit = (
        title.replace("5\n29\n", "5\n2f\n")
        .replace("GROUND FLOOR PLAN", "SAMPLE PANEL SCHEDULE")
        .replace("2\nTITLE\n", "2\nDRAWING_TITLE\n")
    )
    data = (source[:start] + generic + explicit + source[end:]).encode()
    sheets = drawings.read_sheets("EL-000.dxf", data)
    paper = next(s for s in sheets if s.layout == "Layout1")
    assert paper.title == "SAMPLE PANEL SCHEDULE"
    assert paper.source["title"]["handle"] == "2F"


def test_file_map_and_file_list_do_not_call_model_a_sheet(rec):
    from qsone.tools.files import _list

    f = files.add_file(rec, "sample.dxf", b"sample", actor="test")
    with rec.write("one") as c:
        for layout, counts in (("Model", {"MCCB": 3}), ("Paper", {})):
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": f.id,
                    "sheet": layout,
                    "number": "EL-000",
                    "counts": counts,
                },
            )
    detail = store.detail(rec, f.id)
    assert [s["sheet"] for s in detail["sheets"]] == ["Paper"]
    assert detail["file_counts"] == {"MCCB": 3}
    assert detail["file_counts_source"] == {"file_id": f.id}
    assert "1 sheets" in _list(rec, False)
