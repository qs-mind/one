import datetime as dt
import io

import openpyxl
import xlwt

from qsone.records.extract import Piece, chunk, extract
from tests.samples import sample_pdf, sample_xls, sample_xlsx

BOQ = {
    "BOQ": [
        ["أعمال الخرسانة"],
        ["03/02", "خرسانة مسلحة للأسقف", "م3", 120, 39850.5],
        [],
        ["08/22", "بردورة خرسانية", "م.ط", 5193.0, dt.date(2026, 11, 2)],
    ]
}


def test_pdf_arabic_comes_out_in_reading_order_with_digits_kept():
    # glyphs in visual order, as on the page; pypdfium2 gives logical order back
    x = extract(
        "مواصفات - عينة.pdf",
        sample_pdf([["ط.م ٥١٩٣ ةناسرخ"], ["Sub-Clause 14.2 Advance Payment"]]),
    )
    assert x.status == "read" and x.pages == 2
    assert x.pieces[0] == Piece({"page": 1}, "خرسانة ٥١٩٣ م.ط")
    assert x.pieces[1].locator == {"page": 2}


def test_pdf_arabic_clause_numbers_keep_their_order():
    # real walk, momah p358: «-٢-١-١٢تعاريف» for clause ١٢-١-٢; a dash does not join
    # Arabic-Indic digits, so pdfium gives each number as it is seen, left to right
    lines = ["فيراعت-٢-١-١٢", "مسقلا :٢", "Clause 12-1-2 rev 3"]
    x = extract("مواصفات - عينة.pdf", sample_pdf([lines]))
    assert x.pieces[0].text.split("\n") == ["١٢-١-٢-تعاريف", "٢: القسم", "Clause 12-1-2 rev 3"]


def test_pdf_numbers_joined_by_a_dot_or_slash_are_left_as_they_are():
    # «٣٫٥», «١٠:٣٠» and «٢٠٢٦/١١/٠٦» show as one number each: pdfium keeps their order
    lines = ["ةعاسلا ١٠:٣٠", "خيراتب ٢٠٢٦/١١/٠٦", "مس ٣.٥-٤.٥ كمس"]
    text = extract("مواصفات - عينة.pdf", sample_pdf([lines])).pieces[0].text
    assert "١٠:٣٠" in text and "٢٠٢٦/١١/٠٦" in text and "٣.٥-٤.٥" in text


def test_scanned_page_is_named():
    x = extract("عينة.pdf", sample_pdf([["Page one text"], []]))
    assert x.status == "partly_read" and x.note == "FILE_SCANNED_PAGES"
    x = extract("عينة.pdf", sample_pdf([[], []]))
    assert x.status == "unreadable" and x.note == "FILE_SCANNED_PAGES" and x.pieces == []


def test_xlsx_row_per_item_with_its_heading():
    data = sample_xlsx(
        {"BOQ": [["أعمال الخرسانة"], ["03/02", "خرسانة مسلحة للأسقف", "م3", 120, 39850.5]]}
    )
    x = extract("جدول الكميات - عينة.xlsx", data)
    assert x.pieces[-1] == Piece(
        {"sheet": "BOQ", "row": 2},
        "أعمال الخرسانة | 03/02 | خرسانة مسلحة للأسقف | م3 | 120 | 39850.5",
    )


def test_xls_reads_like_xlsx():
    xls = extract("جدول الكميات - عينة.xls", sample_xls(BOQ))
    xlsx = extract("جدول الكميات - عينة.xlsx", sample_xlsx(BOQ))
    assert (xls.kind, xls.status, xls.pages) == ("xls", "read", 1)
    assert xls.pieces == xlsx.pieces
    assert xls.pieces[-1] == Piece(
        {"sheet": "BOQ", "row": 4},
        "أعمال الخرسانة | 08/22 | بردورة خرسانية | م.ط | 5193 | 2026-11-02",
    )


def test_broken_pdf_is_unreadable():
    x = extract("عينة.pdf", b"%PDF-1.7 garbage")
    assert (x.status, x.note, x.pieces) == ("unreadable", "FILE_UNREADABLE", [])


def test_unknown_kind_is_stored():
    x = extract("نموذج - عينة.rvt", b"\xd0\xcf\x11\xe0 sample")
    assert (x.kind, x.status, x.note, x.pieces) == ("other", "stored", "FILE_NOT_READ_YET", [])


def test_extension_must_match_content():
    x = extract("عينة.pdf", sample_xlsx(BOQ))
    assert x.status == "stored" and x.note == "FILE_NOT_READ_YET"


def test_csv_and_txt_one_piece_per_row_or_line():
    csv = extract("عينة.csv", "\ufeff03/02,خرسانة مسلحة,م3\n\n05/01,عزل,م2\n".encode())
    assert csv.status == "read"
    assert csv.pieces == [
        Piece({"line": 1}, "03/02 | خرسانة مسلحة | م3"),
        Piece({"line": 3}, "05/01 | عزل | م2"),
    ]
    txt = extract("عينة.txt", "سطر أول\r\n\r\nسطر ثالث".encode("cp1256"))
    assert txt.pieces == [Piece({"line": 1}, "سطر أول"), Piece({"line": 3}, "سطر ثالث")]


def test_chunk_splits_long_pages_and_keeps_the_locator():
    text = "خرسانة مسلحة للأسقف " * 50  # about 1,000 characters, sample text
    parts = chunk([Piece({"page": 3}, text.strip()), Piece({"page": 4}, "قصير")], max_chars=300)
    assert all(len(p.text) <= 300 for p in parts)
    assert [p.locator for p in parts] == [{"page": 3}] * 4 + [{"page": 4}]
    assert " ".join(p.text for p in parts[:4]) == text.strip()
    assert all(not p.text.endswith(" ") and not p.text.startswith(" ") for p in parts)
    assert chunk([Piece({"line": 1}, "x" * 10)], max_chars=4) == [
        Piece({"line": 1}, "xxxx"),
        Piece({"line": 1}, "xxxx"),
        Piece({"line": 1}, "xx"),
    ]


NOTE = "ملحوظة:-\n1- يتم اعتماد الرسومات التنفيذية قبل البدء - عينة\n2- " + "شرط طويل " * 20


def _merged_note_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append(["أعمال النجارة"])
    ws.append([NOTE])
    ws.merge_cells("A2:F2")
    for n in range(1, 6):
        ws.append([f"12-{n}", "باب خشب - عينة", "عدد", n, 4700])
    ws.append(["Supply and install access control - sample"])
    ws.append(["Supply and install access control - sample", "Each", 3])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _merged_note_xls() -> bytes:
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("BOQ")
    ws.write(0, 0, "أعمال النجارة")
    ws.write_merge(1, 1, 0, 5, NOTE)
    for n in range(1, 6):
        for c, v in enumerate([f"12-{n}", "باب خشب - عينة", "عدد", n, 4700]):
            ws.write(1 + n, c, v)
    ws.write(7, 0, "Supply and install access control - sample")
    for c, v in enumerate(["Supply and install access control - sample", "Each", 3]):
        ws.write(8, c, v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_a_long_merged_note_is_read_once_not_carried_as_a_heading():
    for name, data in [("عينة.xlsx", _merged_note_xlsx()), ("عينة.xls", _merged_note_xls())]:
        x = extract(name, data)
        texts = [p.text for p in x.pieces]
        assert sum("يتم اعتماد الرسومات" in t for t in texts) == 1, name
        # the items keep the section heading above the note
        assert texts[2] == "أعمال النجارة | 12-1 | باب خشب - عينة | عدد | 1 | 4700", name
        # a heading is not repeated in a row that already holds it
        assert texts[-1] == "Supply and install access control - sample | Each | 3", name


def test_reversed_arabic_quality_and_page_selection(rec, monkeypatch):
    from qsone.records import extract as reader
    from qsone.records import files, search

    bad = "ىلع سفانتملا ميدقت نامضلا يئادتبالا ةبسنب 1 ةئاملاب )11( ةيكنبلا"
    good = "على المتنافس تقديم الضمان الابتدائي بنسبة 1 بالمائة (11) البنكية"
    assert reader.arabic_quality(good) > reader.arabic_quality(bad)
    monkeypatch.setattr(reader, "_page_text", lambda _: bad)
    from types import SimpleNamespace

    monkeypatch.setattr(
        "pdf_inspector.extract_pages_markdown_bytes",
        lambda *_: SimpleNamespace(pages=[SimpleNamespace(page=0, markdown="# " + good)]),
    )
    result = reader.extract("sample.pdf", sample_pdf([["Sample"]]))
    assert result.pieces == [Piece({"page": 1}, good)]
    assert result.page_sources == {1: "pdf-inspector"}
    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample"]]), actor="engineer")
    assert search.search(rec, "الضمان الابتدائي").hits[0].file_id == f.id


def test_reversed_arabic_pypdf_fallback(monkeypatch):
    from qsone.records import extract as reader

    monkeypatch.setattr(reader, "_inspector_text", lambda *_: "")
    monkeypatch.setattr(reader, "_pypdf_text", lambda *_: "ﻋﻠﻰ المتنافس تقديم الضمان الابتدائي")
    text, source = reader.select_pdf_text(b"sample", 0, "ىلع سفانتملا نامضلا يئادتبالا")
    assert text == "على المتنافس تقديم الضمان الابتدائي"
    assert source == "pypdf"


def test_background_rereads_older_pdf_once_keeps_ocr_and_original(rec, monkeypatch):
    import json

    from qsone.records import extract as reader
    from qsone.records import files, search
    from qsone.records.mapping import worker

    data = sample_pdf([["Sample original"], ["Sample scan"]])
    f = files.add_file(rec, "sample.pdf", data, actor="engineer")
    with rec.write("one") as c:
        c.execute("DELETE FROM meta WHERE key=?", ("extractor:" + f.id,))
        c.execute(
            "UPDATE chunks SET locator=? WHERE file_id=? AND seq=1",
            (json.dumps({"page": 2, "read_by": "tesseract"}), f.id),
        )
    seen = []

    def reread(name, raw):
        seen.append(raw)
        return reader.Extracted(
            "pdf",
            "read",
            2,
            [Piece({"page": 1}, "الضمان الابتدائي 1%")],
            None,
            page_sources={1: "pdf-inspector", 2: "pdfium"},
        )

    monkeypatch.setattr(files, "extract", reread)
    assert worker.step(rec)
    assert seen == [data]
    assert files.read_original(rec, f.id) == data
    assert search.search(rec, "الضمان الابتدائي").hits
    assert not search.search(rec, "original").hits
    assert json.loads(rec.meta()["pdf_sources:" + f.id]) == {"1": "pdf-inspector", "2": "pdfium"}
    with rec.read() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM chunks WHERE file_id=? "
                "AND json_extract(locator,'$.read_by')='tesseract'",
                (f.id,),
            ).fetchone()[0]
            == 1
        )
    worker.step(rec)
    assert seen == [data]


def test_pdf_source_selection_keeps_good_pdfium_and_survives_failed_alternatives(monkeypatch):
    from qsone.records import extract as reader

    seen = []

    def broken(*args):
        seen.append(args[1])
        raise ValueError("Synthetic damaged alternative")

    monkeypatch.setattr(reader, "_inspector_text", broken)
    monkeypatch.setattr(reader, "_pypdf_text", broken)
    good = "على المتنافس تقديم الضمان الابتدائي"
    assert reader.select_pdf_text(b"sample", 0, good) == (good, "pdfium")
    assert seen == []
    bad = "ىلع سفانتملا نامضلا يئادتبالا"
    assert reader.select_pdf_text(b"sample", 1, bad) == (bad, "pdfium")
    assert seen == [1, 1]


def test_pdf_markdown_preserves_visible_blank_placeholders():
    from qsone.records.extract import _plain_markdown

    assert "____" in _plain_markdown("# الدفعة المقدمة\n| الدفعة | ____ |\n")


def test_inspector_parses_multi_page_pdf_once(monkeypatch):
    from types import SimpleNamespace

    import pdf_inspector

    from qsone.records import extract as reader

    calls = []
    monkeypatch.setattr(reader, "_page_text", lambda _: "ىلع سفانتملا")

    def inspect(data, indices=None):
        calls.append(indices)
        return SimpleNamespace(
            pages=[SimpleNamespace(page=i, markdown="على المتنافس") for i in range(4)]
        )

    monkeypatch.setattr(pdf_inspector, "extract_pages_markdown_bytes", inspect)
    result = reader.extract("sample.pdf", sample_pdf([["Sample"]] * 4))
    assert len(result.pieces) == 4
    assert len(calls) == 1


def test_rereading_a_pdf_with_no_map_row_creates_it(rec, monkeypatch):
    """A project made before the map: re-reading its PDF used to fail (map_files.kind NOT NULL)
    on every slice, so the map never started (Kareem's walk, 8 Nov 2026)."""
    from qsone.records import files
    from qsone.records.mapping import worker

    f = files.add_file(rec, "sample.pdf", sample_pdf([["Sample"]]), actor="engineer")
    with rec.write("one") as c:
        c.execute("DELETE FROM meta WHERE key=?", ("extractor:" + f.id,))
        c.execute("DROP TRIGGER map_files_no_delete")  # only to make the old project's shape
        c.execute("DELETE FROM map_files WHERE file_id=?", (f.id,))
    assert worker.step(rec)
    with rec.read() as c:
        assert c.execute(
            "SELECT kind, pages, local_state FROM map_files WHERE file_id=?", (f.id,)
        ).fetchone() == ("pdf", 1, "waiting")
