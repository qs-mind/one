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
    detail = store.detail(rec, f.id)
    assert all(s["sheet"] != "Model" for s in detail["sheets"])
    assert detail["file_counts"]["DOOR"] == 3


def test_scanned_drawing_uses_stored_words(rec, monkeypatch):

    from qsone.records import ocr

    monkeypatch.setattr(ocr, "ready", lambda: True)
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


async def test_drawing_read_tools_surface_local_map(rec):
    from pathlib import Path

    from qsone.engine.map_digest import digest
    from qsone.engine.tools import call
    from tests.fakes_tools import tool_ctx

    f = files.add_file(
        rec,
        "sample.dwg",
        (Path(__file__).parent / "fixtures/drawings/test-plan.dwg").read_bytes(),
        actor="engineer",
    )
    with rec.write("one") as c:
        store.write(
            c,
            rec,
            "map_sheets",
            {
                "file_id": f.id,
                "sheet": "SampleLayout1",
                "number": "E-201",
                "title": "Sample main single line diagram",
                "revision": "A",
                "scale": "NTS",
                "counts": {"BREAKER": 214},
            },
        )
        chunk = c.execute("SELECT id FROM chunks WHERE file_id=? LIMIT 1", (f.id,)).fetchone()[0]
    ctx = tool_ctx(rec)
    for name, args in (("files_read", {"file_id": f.id}), ("read_chunk", {"chunk_id": chunk})):
        answer = await call(name, args, ctx)
        assert "E-201" in answer and "Sample main single line diagram" in answer
        assert "BREAKER × 214" in answer and "SampleLayout1" in answer and "sample.dwg" in answer
    assert "1 sheets" in await call("files_list", {}, ctx)
    assert "E-201" in digest(rec) and "Sample main single line diagram" in digest(rec)


def test_drawing_header_pages_before_original_text(rec):
    from pathlib import Path

    from qsone.tools.files import PART_BYTES, ReadArgs, _render, _select

    f = files.add_file(
        rec,
        "sample.dxf",
        (Path(__file__).parent / "fixtures/drawings/title.dxf").read_bytes(),
        actor="engineer",
    )
    with rec.write("one") as c:
        for i in range(40):
            store.write(
                c,
                rec,
                "map_sheets",
                {
                    "file_id": f.id,
                    "sheet": f"SampleLayout{i}",
                    "number": f"E-{201 + i}",
                    "title": "Sample diagram",
                    "counts": {"BREAKER": i + 1},
                },
            )
    args = ReadArgs(file_id=f.id)
    sel = _select(rec, f, args)
    result = _render(rec, f, args, sel, [])
    assert "part 1 of" in result and "call files_read" in result
    assert len(result.encode()) < PART_BYTES + 2048
    gathered = [result]
    while "call files_read" in gathered[-1]:
        args = ReadArgs(file_id=f.id, part=len(gathered) + 1)
        gathered.append(_render(rec, f, args, sel, []))
        assert len(gathered) < 100
    joined = "\n".join(gathered)
    assert "E-240" in joined and "BREAKER × 820" in joined
    with rec.read() as c:
        text = c.execute(
            "SELECT text FROM chunks WHERE file_id=? ORDER BY seq LIMIT 1", (f.id,)
        ).fetchone()[0]
    assert " ".join(text.split()) in joined
