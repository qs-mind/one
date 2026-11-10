"""Reading a file completely (Phase 1, C9): drawings that say why they could not be read and
what they did not read; a drawing's tables a row at a time and its dimensions as drawn; Word
97-2003 files read by ONE itself; `unread` on a file's JSON and at the end of the Lead's
`files_read` and `files_list`.

Fakes only: a fake drawing reader prints the JSON the real one would; every .doc is made here
by tests/doc_writer.py; every text is sample data."""

import json
import sys
import time

import pytest

from qsone import copy
from qsone.engine.tools import call
from qsone.records import drawings as drawings_module
from qsone.records import files, unread
from qsone.records.extract import extract
from qsone.records.readers import doc_props
from qsone.records.readers.dwg import dimension_text
from qsone.tools import files as files_tools  # noqa: F401 - registers the files tools
from tests.doc_writer import biff_workbook, word_doc, xlsx_package
from tests.fakes_tools import fake_services, tool_ctx

MIB = 1024 * 1024


@pytest.fixture
def fake_reader(tmp_path, monkeypatch):
    """A drawing reader that prints `answer` and exits with `code`, as the real one does."""

    def use(answer: dict, code: int = 0):
        out = tmp_path / "answer.json"
        out.write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        script = tmp_path / "reader"
        script.write_text(
            f"#!{sys.executable}\nimport sys\nsys.stdin.buffer.read()\n"
            f"sys.stdout.write(open({str(out)!r}, encoding='utf-8').read())\nsys.exit({code})\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        monkeypatch.setenv("QSONE_DRAWINGS", str(script))

    return use


def drawing(**more) -> dict:
    base = {"format": "dwg", "texts": [], "inserts": [], "layouts": [{"name": "Model"}]}
    found = base | {"stats": {"decoded": 10, "skipped": 0}} | more
    for row in found["texts"] + found.get("dimensions", []):
        row.setdefault("x", 0.0)
        row.setdefault("y", 0.0)
    return found


def test_a_drawing_that_cannot_be_read_says_why(fake_reader):
    for reason, note in (
        ("not-a-dwg", "FILE_DRAWING_NOT_DWG"),
        ("unsupported-version", "FILE_DRAWING_TOO_OLD"),
        ("damaged", "FILE_DRAWING_DAMAGED"),
        ("too-large", "FILE_DRAWING_TOO_LARGE"),
    ):
        fake_reader({"reason": reason, "file_version": "", "problems": ["x"]}, code=1)
        x = extract("مسقط - عينة.dwg", b"AC1032" + b"\0" * 64)
        assert (x.status, x.note, x.pieces) == ("unreadable", note, [])
        assert getattr(copy, note)["en"] and getattr(copy, note)["ar"]


def test_the_reader_has_more_time_for_a_bigger_drawing():
    assert drawings_module.timeout_for(b"AC1032") == 30
    assert drawings_module.timeout_for(b"\0" * (5 * MIB)) == 40


def test_what_a_drawing_did_not_read_is_listed_with_why(fake_reader):
    fake_reader(
        drawing(
            texts=[{"text": "غرفة - عينة", "handle": "1A"}],
            omitted={"texts": 3, "blocks": 2, "segments": 900},
            traversal_limited=True,
            stats={"decoded": 10, "skipped": 4},
            unread_kinds={"ACAD_PROXY_ENTITY": 2, "3DSOLID": 1, "REGION": 1, "WIPEOUT": 5},
            xrefs=[{"path": "C:\\sample\\grid.dwg"}],
            references=[
                {"kind": "IMAGE", "path": "site.jpg"},
                {"kind": "PDFUNDERLAY", "path": "a.pdf"},
            ],
            embedded=[{"streams": ["CONTENTS"]}, {"streams": ["Workbook"], "too_large": True}],
        ),
        code=2,
    )
    x = extract("مسقط - عينة.dwg", b"AC1032" + b"\0" * 64)
    assert (x.status, x.note) == ("partly_read", "FILE_PARTLY_READ")
    said = [(p["part"]["en"], p["why"]["en"]) for p in x.unread]
    assert ("3 texts", copy.UNREAD_WHY_TOO_MANY["en"]) in said
    assert ("2 objects", copy.UNREAD_WHY_TOO_MANY["en"]) in said  # blocks; geometry never counts
    assert ("Blocks inside blocks", copy.UNREAD_WHY_NESTED["en"]) in said
    assert ("Drawing records: 4", copy.UNREAD_WHY_DAMAGED["en"]) in said
    assert ("Objects from CAD add-ons: 2", copy.UNREAD_WHY_KIND["en"]) in said
    assert ("WIPEOUT objects: 5", copy.UNREAD_WHY_KIND["en"]) in said
    assert ("3D objects: 2", copy.UNREAD_WHY_KIND["en"]) in said
    assert ("Attached drawing «grid.dwg»", copy.UNREAD_WHY_OTHER_FILE["en"]) in said
    assert ("Picture «site.jpg»", copy.UNREAD_WHY_OTHER_FILE["en"]) in said
    assert ("Underlay «a.pdf»", copy.UNREAD_WHY_OTHER_FILE["en"]) in said
    assert ("Pictures or objects inside: 1", copy.UNREAD_WHY_PICTURES["en"]) in said
    assert ("Excel sheets inside: 1", copy.UNREAD_WHY_SHEETS["en"]) in said
    assert all(p["part"]["ar"] and p["why"]["ar"] for p in x.unread)


def test_a_drawing_read_whole_has_nothing_unread(fake_reader):
    fake_reader(drawing(texts=[{"text": "A-101", "handle": "1"}], omitted={"segments": 50}))
    x = extract("مسقط - عينة.dwg", b"AC1032" + b"\0" * 64)
    assert (x.status, x.note, x.unread) == ("read", None, [])


def test_tables_come_a_row_at_a_time_and_dimensions_as_drawn(fake_reader):
    cell = {"kind": "TABLE", "handle": "T1", "layout": "Model"}
    fake_reader(
        drawing(
            texts=[
                cell | {"text": "البند - عينة", "table_cell": [0, 0]},
                cell | {"text": "الكمية", "table_cell": [0, 2]},
                cell | {"text": "خرسانة", "table_cell": [1, 0]},
                cell | {"text": "12.50", "table_cell": [1, 2]},
                {"kind": "MLEADER", "text": "عمود C1 - عينة", "handle": "L1"},
                {"text": "{hgs", "raw_text": "{hgs", "font_file": "arabic.shx", "handle": "K1"},
            ],
            dimensions=[
                {"handle": "D1", "kind": "ALIGNED", "measured": 5.0, "text": ""},
                {"handle": "D2", "kind": "LINEAR", "measured": 2.5, "text": "<> م"},
                {"handle": "D3", "kind": "LINEAR", "measured": 9.0, "shown": ["٩٫٠٠ م"]},
            ],
        )
    )
    x = extract("جدول - عينة.dwg", b"AC1032" + b"\0" * 64)
    by = {json.dumps(p.locator, ensure_ascii=False): p.text for p in x.pieces}
    assert by['{"sheet": "Model", "handle": "T1", "row": 1}'] == "البند - عينة |  | الكمية"
    assert by['{"sheet": "Model", "handle": "T1", "row": 2}'] == "خرسانة |  | 12.50"
    assert by['{"sheet": "Model", "handle": "L1", "kind": "MLEADER"}'] == "عمود C1 - عينة"
    dims = [p.text for p in x.pieces if p.locator.get("kind") == "DIMENSION"]
    assert dims == ["5", "2.5 م", "٩٫٠٠ م"]
    # a keyboard-mapped Arabic SHX keeps every letter, «{» included
    assert by['{"sheet": "Model", "handle": "K1"}'] == "جالس"


def test_a_dimension_text_override_names_the_measurement():
    assert dimension_text({"measured": 1200.0, "text": "<> mm", "dimlfac": 1}) == "1200 mm"
    assert dimension_text({"measured": 3.0, "text": "TYP."}) == "TYP."
    assert dimension_text({"measured": 3.0, "text": "<>"}) == "3"


def doc_text(data: bytes) -> list[tuple[dict, str]]:
    return [(p.locator, p.text) for p in extract("مواصفات - عينة.doc", data).pieces]


def test_word_97_text_tables_and_headings_are_read_without_libreoffice(monkeypatch):
    monkeypatch.setattr("qsone.records.office.find_soffice", lambda: None)
    data = word_doc(
        [
            ("h", "الشروط العامة - عينة"),
            ("p", 'يلتزم المقاول FIELD(HYPERLINK "x"|بالمواصفات) - عينة'),
            ("table", [["م", "البيان", "", "الكمية"], ["1", "", "م٣", ""]]),
        ]
    )
    x = extract("مواصفات - عينة.doc", data)
    assert (x.kind, x.status, x.note, x.unread) == ("doc", "read", None, [])
    got = [(p.locator, p.text) for p in x.pieces]
    heading = {"heading": "الشروط العامة - عينة"}
    assert got[1] == ({"paragraph": 2} | heading, "يلتزم المقاول بالمواصفات - عينة")
    # every cell keeps its column; an empty cell is an empty place
    assert got[2] == ({"table": 1, "row": 1}, "م | البيان |  | الكمية")
    assert got[3] == ({"table": 1, "row": 2}, "1 |  | م٣")


def test_word_97_and_docx_give_the_same_rows():
    import io

    import docx

    rows = [["م", "البيان", "", "الكمية"], ["1", "", "م٣", ""], ["", "", "", ""]]
    d = docx.Document()
    table = d.add_table(rows=len(rows), cols=4)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    out = io.BytesIO()
    d.save(out)

    def rows_of(name, data):
        return [p.text for p in extract(name, data).pieces if "table" in p.locator]

    expected = ["م | البيان |  | الكمية", "1 |  | م٣"]
    assert rows_of("a.docx", out.getvalue()) == expected
    assert rows_of("a.doc", word_doc([("table", rows)])) == expected


def test_word_97_list_numbers_are_shown():
    data = word_doc([("li", "first", 0), ("li", "second", 0), ("li", "sub", 1), ("li", "third", 0)])
    assert [t for _, t in doc_text(data)] == ["1. first", "2. second", "2.1 sub", "3. third"]
    arabic = word_doc([("li", "أول", 0), ("li", "ثاني", 0)], nfc=46)
    assert [t for _, t in doc_text(arabic)] == ["أ. أول", "ب. ثاني"]


def test_word_97_excel_sheets_inside_are_read_a_row_at_a_time():
    sheet = [["البند", "", "الكمية"], ["خرسانة - عينة", "", 12.5]]
    data = word_doc(
        [("p", "جدول الكميات - عينة")],
        objects=[{"Workbook": biff_workbook(sheet)}, {"Package": xlsx_package(sheet)}],
    )
    got = doc_text(data)
    assert ({"object": 1, "sheet": "Sheet1", "row": 2}, "خرسانة - عينة |  | 12.5") in got
    assert ({"object": 2, "sheet": "Sheet", "row": 1}, "البند |  | الكمية") in got


def test_word_97_says_what_it_did_not_read():
    data = word_doc(
        [("p", "نص HIDE(مخفي) DEL(ممسوح) SYM(ab) - عينة FIELD(FORMCHECKBOX|)")],
        objects=[{"CONTENTS": b"picture"}],
    )
    x = extract("مواصفات - عينة.doc", data)
    assert (x.status, x.note) == ("partly_read", "FILE_PARTLY_READ")
    said = [p["part"]["en"] for p in x.unread]
    assert "Tracked deletions: 5 characters" in said
    assert "Symbol characters: 2" in said
    assert "Form fields: 1" in said
    assert "Pictures or objects inside: 1" in said
    assert [f.kind for f in x.flags] == ["invisible_text"]
    assert x.pieces[0].text == "نص - عينة"


def test_word_97_that_is_locked_damaged_or_not_word_says_so(monkeypatch):
    locked = word_doc([("p", "سري - عينة")], encrypted=True)
    assert extract("a.doc", locked).note == "FILE_LOCKED"
    assert extract("a.doc", word_doc([("p", "x")])[:1536]).status == "unreadable"
    monkeypatch.setattr("qsone.records.office.find_soffice", lambda: None)
    assert extract("a.doc", b"plain words, sample").note == "FILE_LIBREOFFICE_MISSING"


def test_word_97_work_grows_with_the_file_not_with_its_tables():
    hidden_runs = " ".join(f"word{i} HIDE(h{i})" for i in range(5000))
    data = word_doc([("p", hidden_runs)])
    start = time.perf_counter()
    x = extract("a.doc", data)
    assert time.perf_counter() - start < 1.0
    assert x.flags[0].count > 5000
    # hidden runs that are also white and tiny: each is matched to its hidden span by bisect
    runs = " ".join(f"word{i} HIDEWHITE(h{i})" for i in range(20000))
    start = time.perf_counter()
    x = extract("a.doc", word_doc([("p", runs)]))
    assert time.perf_counter() - start < 1.0
    assert [f.kind for f in x.flags] == ["invisible_text"]
    assert [f.kind for f in extract("a.doc", word_doc([("p", "a WHITE(w)")])).flags] == [
        "white_text"
    ]
    # a page named 50,000 times in the property table is read once
    repeated = word_doc([("p", "HIDE(h) sample")], chp_repeat=50000)
    start = time.perf_counter()
    assert doc_text(repeated) == [({"paragraph": 1}, "sample")]
    assert time.perf_counter() - start < 1.0


def test_the_property_pages_are_read_once_each():
    class Fib:
        lost: set = set()

        def blob(self, table, index):
            return table

    n = 1000
    plc = b"".join(i.to_bytes(4, "little") for i in range(n + 1)) + (7).to_bytes(4, "little") * n
    assert doc_props._pages(Fib(), plc, 0) == [7]


@pytest.fixture
def partly_read_dwg(rec, fake_reader):
    fake_reader(drawing(texts=[{"text": "A-101", "handle": "1"}], omitted={"texts": 3}), code=2)
    return files.add_file(rec, "مسقط - عينة.dwg", b"AC1032" + b"\0" * 64, actor="engineer")


def test_a_files_json_says_what_was_not_read(rec, partly_read_dwg):
    from qsone.projects import _file

    found = _file(partly_read_dwg, rec)["unread"]
    assert found == [
        {
            "part": copy.counted(3, copy.UNREAD_DRAWING_ROWS["texts"]),
            "why": copy.UNREAD_WHY_TOO_MANY,
        }
    ]


def test_the_live_file_event_says_what_was_not_read(rec, partly_read_dwg, monkeypatch):
    from qsone.deliverables import events
    from qsone.projects import _file
    from qsone.records.mapping import worker

    told = []
    monkeypatch.setattr(events, "publish", lambda pid, event: told.append((pid, event)))
    worker._file_changed(rec, partly_read_dwg.id)
    [(pid, event)] = told
    assert (pid, event["type"]) == (rec.id, "file")
    assert event["file"]["unread"] == _file(partly_read_dwg, rec)["unread"] != []


def test_a_file_kept_unread_is_one_part_with_its_note(rec):
    info = files.add_file(rec, "a.zzz", b"sample bytes", actor="engineer")
    assert unread.of(rec, info) == [{"part": copy.UNREAD_WHOLE_FILE, "why": copy.FILE_NOT_READ_YET}]


@pytest.mark.anyio
async def test_the_lead_reads_what_was_not_read_at_the_end(rec, partly_read_dwg):
    ctx = tool_ctx(rec, services=fake_services())
    out = await call("files_read", {"file_id": partly_read_dwg.id}, ctx)
    lines = out.rstrip().splitlines()
    assert lines[-1].startswith("<</data")  # the result is fenced as data: the end is inside
    assert lines[-2] == f"not read: 3 texts: {copy.UNREAD_WHY_TOO_MANY['en']}"
    listed = await call("files_list", {}, ctx)
    assert f"  not read: 3 texts: {copy.UNREAD_WHY_TOO_MANY['en']}" in listed


def test_picture_text_is_read(rec, monkeypatch, tmp_path):
    """A picture dropped into the project is read by the text reader for pictures when it is
    added: the map worker runs ONE's own pipeline on scripted detector and recogniser sessions,
    keeps each word with its box, and the words can be searched. Nothing is spent."""
    from qsone.records import search
    from qsone.records.mapping import store, worker
    from tests import ocr_fakes

    recogniser = ocr_fakes.FakeRecogniser(["sample site notice concrete works"])
    ocr_fakes.install(monkeypatch, tmp_path, recogniser=recogniser)
    image = ocr_fakes.picture(400, 200)
    info = files.add_file(rec, "site photo.png", image, actor="engineer")
    current = worker.FilePass()
    while worker.step(rec, original=current):
        pass
    row = store.detail(rec, info.id)
    assert row["local_state"] == "done" and row["ocr_done_pages"] == [1]
    with rec.read() as conn:
        chunks = [
            (json.loads(loc), text)
            for loc, text in conn.execute(
                "SELECT locator, text FROM chunks WHERE file_id=? ORDER BY seq", (info.id,)
            )
        ]
        assert unread.parts_of(conn, files.file_info(rec, info.id)) == []
    assert [t for _, t in chunks] == ["sample", "site", "notice", "concrete", "works"]
    assert all(loc["read_by"] == "ppocr-v5" and len(loc["box"]) == 4 for loc, _ in chunks)
    assert recogniser.calls  # read by the recogniser, not by a stand-in for the whole page
    assert any(h.file_id == info.id for h in search.search(rec, "concrete").hits)
