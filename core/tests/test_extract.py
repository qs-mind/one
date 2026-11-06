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
