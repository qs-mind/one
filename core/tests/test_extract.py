import datetime as dt

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
    x = extract("مخطط - عينة.dwg", b"AC1032 sample")
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
