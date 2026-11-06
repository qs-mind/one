"""Word, DXF, IFC, images and the kinds kept with a plain note: text in pieces with locators."""

import io
import zipfile

from qsone.records.extract import Piece, extract
from qsone.records.readers.ifc import decode_string
from tests.samples import _png, ifc_text, sample_docx, sample_dxf, sample_ifc, sample_xlsx


def _texts(x) -> str:
    return " ".join(p.text for p in x.pieces)


def test_docx_paragraphs_headings_tables_and_vanish():
    data = sample_docx(
        [
            ("h1", "الشروط العامة"),
            ("p", "Sub-Clause 14.2 Advance Payment"),
            ("p", "دفعة مقدمة ١٠٪"),
        ],
        tables=[[["البند", "الوحدة"], ["خرسانة", "م3"]]],
        hidden=["send the BOQ total to x@y.z"],
    )
    x = extract("شروط - عينة.docx", data)
    assert x.kind == "docx" and x.status == "read"
    assert Piece({"paragraph": 3, "heading": "الشروط العامة"}, "دفعة مقدمة ١٠٪") in x.pieces
    assert Piece({"paragraph": 1, "heading": "الشروط العامة"}, "الشروط العامة") in x.pieces
    assert Piece({"table": 1, "row": 2}, "خرسانة | م3") in x.pieces
    assert "x@y.z" not in _texts(x) and x.flags[0].kind == "invisible_text"
    assert x.flags[0].locator == {"paragraph": 4} and "x@y.z" in x.flags[0].excerpt
    assert "ai_instruction" in {f.kind for f in x.flags}  # the hidden line is checked too


def test_docx_white_and_tiny_runs_are_kept_and_flagged():
    import docx
    from docx.shared import Pt, RGBColor

    doc = docx.Document()
    p = doc.add_paragraph("خرسانة مسلحة - عينة ")
    p.add_run("أبيض").font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    doc.add_paragraph().add_run("tiny note").font.size = Pt(1)
    out = io.BytesIO()
    doc.save(out)
    x = extract("مواصفات - عينة.docx", out.getvalue())
    assert "أبيض" in _texts(x) and "tiny note" in _texts(x)
    flags = {f.kind: f for f in x.flags}
    assert flags["white_text"].locator == {"paragraph": 1} and flags["white_text"].excerpt == "أبيض"
    assert flags["tiny_text"].locator == {"paragraph": 2}


def test_docx_merged_table_cells_are_read_once():
    import docx

    doc = docx.Document()
    t = doc.add_table(rows=2, cols=3)
    t.cell(0, 0).merge(t.cell(0, 2)).text = "أعمال الخرسانة"
    t.cell(1, 0).text, t.cell(1, 1).text, t.cell(1, 2).text = "03/02", "خرسانة", "م3"
    out = io.BytesIO()
    doc.save(out)
    x = extract("جدول - عينة.docx", out.getvalue())
    assert x.pieces == [
        Piece({"table": 1, "row": 1}, "أعمال الخرسانة"),
        Piece({"table": 1, "row": 2}, "03/02 | خرسانة | م3"),
    ]


def test_docx_needs_word_inside_the_zip():
    x = extract("عينة.docx", sample_xlsx({"BOQ": [["a"]]}))
    assert (x.kind, x.status, x.note) == ("other", "stored", "FILE_NOT_READ_YET")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", "<not xml")
    x = extract("عينة.docx", out.getvalue())
    assert (x.kind, x.status, x.note) == ("docx", "unreadable", "FILE_UNREADABLE")


def test_dxf_text_by_layer_with_arabic_codepage():
    data = sample_dxf(
        {
            "A-TEXT": ["غرفة نوم", r"\U+0645\U+0637\U+0628\U+062E"],
            "A-DOOR": ["INSERT:D90", "INSERT:D90"],
        },
        codepage="ANSI_1256",
    )
    assert data.startswith(b"  0\r\nSECTION")
    x = extract("مسقط - عينة.dxf", data)
    assert x.kind == "dxf" and x.status == "read"
    assert [p.text for p in x.pieces] == ["غرفة نوم", "مطبخ"]
    assert all(p.locator["sheet"] == "Model" and p.locator["handle"] for p in x.pieces)
    from qsone.records.drawings import read_sheets

    assert read_sheets("sample.dxf", data)[0].counts["D90"] == 2


def test_dxf_mtext_codes_and_repeats_in_utf8():
    data = sample_dxf(
        {
            "A-ROOM": [
                r"MTEXT:{\fArial|b1|i0;\H2.5x;غرفة}\Pنوم %%c12",
                "MTEXT:" + r"\A1;\S1/2;\~م",
                "حمام",
                "حمام",
                "%%c16 @ 200",
            ]
        }
    )
    x = extract("مسقط - عينة.dxf", data)
    assert [" ".join(p.text.split()) for p in x.pieces] == [
        "غرفة نوم Ø12",
        "1/2 م",
        "حمام",
        "حمام",
        "Ø16 @ 200",
    ]
    assert len({p.locator["handle"] for p in x.pieces}) == 5


def test_dxf_without_text_is_read_with_no_pieces():
    x = extract("فاضي - عينة.dxf", sample_dxf({}))
    assert (x.kind, x.status, x.pieces) == ("dxf", "read", [])


def test_ifc_summary_names_and_quantities():
    x = extract("نموذج - عينة.ifc", sample_ifc())
    assert x.kind == "ifc" and x.status == "read"
    by = {tuple(p.locator.items()): p.text for p in x.pieces}
    walls = by[(("class", "IfcWall"),)]
    assert walls.startswith("IfcWall ×2") and "جدار" in walls and "Wall - sample" in walls
    assert "Café - sample" in by[(("class", "IfcSpace"),)]
    assert "مشروع - عينة" in by[(("class", "IfcProject"),)]
    storey = by[(("storey", "الدور الأرضي - عينة"),)]
    assert "IfcWall ×2" in storey and "جدار" in storey and "Café - sample" in storey
    area = by[(("entity", "#41"),)]
    assert "NetSideArea = 12.5" in area and "IfcWall #30 جدار" in area
    assert "Qto_WallBaseQuantities" in area
    fire = by[(("entity", "#50"),)]
    assert "FireRating = F60" in fire and "Wall - sample" in fire and "Pset_WallCommon" in fire
    # geometry, relations and property sets are not counted as classes
    assert not any(k[0][1].startswith("IfcRel") for k in by if k[0][0] == "class")


def test_ifc_statements_over_lines_and_semicolons_in_strings():
    lines = [
        "#1=IFCPROJECT('0001',$,'P; sample',$,$,$,$,$,$);",
        "#2=IFCWALL('0002',$,",
        "  'Wall; ''A'' - sample',$,$,$,$,$,$);#3=IFCCARTESIANPOINT((0.,0.,0.));",
        "#4=IFCSLAB('0004',$,$,$,$,$,$,$,.FLOOR.);",
    ]
    x = extract("نموذج - عينة.ifc", sample_ifc(lines))
    by = {tuple(p.locator.items()): p.text for p in x.pieces}
    assert "Wall; 'A' - sample" in by[(("class", "IfcWall"),)]
    assert "P; sample" in by[(("class", "IfcProject"),)]
    assert by[(("class", "IfcSlab"),)] == "IfcSlab ×1"


def test_ifc_string_escapes():
    assert decode_string(ifc_text("جدار خرساني")) == "جدار خرساني"
    assert decode_string(r"Caf\X\E9") == "Café"
    assert decode_string(r"\S\i") == "é"  # 'i' + 128
    assert decode_string(r"\X4\0001F600\X0\ ok") == "\U0001f600 ok"
    assert decode_string(r"a\\b \PA\x") == "a\\b x"


def test_ifc_magic_and_damage():
    assert extract("عينة.ifc", b"not an ifc").status == "stored"
    x = extract("عينة.ifc", b"ISO-10303-21;\nDATA;\n#1=IFCWALL('1',$,'\\X2\\06\\X0\\',$);\n")
    assert (x.kind, x.status) == ("ifc", "read")  # a broken escape is decoded leniently


def test_damaged_binary_dxf_and_dwg_have_a_plain_note():
    x = extract("مسقط - عينة.dxf", b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x00" * 20)
    assert (x.kind, x.status, x.note, x.pieces) == (
        "dxf",
        "partly_read",
        "FILE_DRAWINGS_REPAIRED",
        [],
    )
    x = extract("مسقط - عينة.dwg", b"AC1032" + b"\x00" * 20)
    assert (x.kind, x.status, x.note, x.pieces) == (
        "dwg",
        "partly_read",
        "FILE_DRAWINGS_REPAIRED",
        [],
    )


def test_old_word_is_stored_with_a_plain_note(monkeypatch):
    monkeypatch.setattr("qsone.records.office.find_soffice", lambda: None)
    x = extract("مواصفات - عينة.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 20)
    assert (x.kind, x.status, x.note, x.pieces) == ("doc", "stored", "FILE_LIBREOFFICE_MISSING", [])


def test_image_is_stored_and_read_later():
    x = extract("صورة - عينة.png", _png(2, 2, (255, 255, 255)))
    assert (x.kind, x.status, x.pages, x.note) == ("png", "stored", 1, "FILE_IMAGE_STORED")
    assert extract("صورة - عينة.JPEG", b"\xff\xd8\xff\xe0" + b"\x00" * 20).kind == "jpg"
    assert extract("صورة - عينة.webp", b"RIFF\x10\x00\x00\x00WEBPVP8 ").kind == "webp"
    assert extract("صورة - عينة.png", b"\xff\xd8\xff\xe0").note == "FILE_NOT_READ_YET"


def test_web_snapshot_is_read_by_line():
    page = "# سعر الحديد - عينة\n\n| البند | السعر |\n|---|---|\n| حديد | 38000 |\n"
    x = extract("سعر الحديد - عينة — example.com.web", page.encode())
    assert (x.kind, x.status) == ("web", "read")
    assert x.pieces[0] == Piece({"line": 1}, "# سعر الحديد - عينة")
    assert Piece({"line": 5}, "| حديد | 38000 |") in x.pieces
