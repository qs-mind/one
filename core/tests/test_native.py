"""Native smoke test: SQLCipher, sqlite-vec, FTS5, onnxruntime and tokenizers load on every CI
system."""

import importlib.util
import json
import re
import sys
from importlib.resources import files
from pathlib import Path
from string import Formatter

import pytest

from qsone import copy, settings
from qsone.meaning.manifest import MODELS


def test_sqlite_vec_and_fts5_load_in_an_encrypted_file(tmp_path):
    import sqlcipher3.dbapi2 as sq
    import sqlite_vec

    c = sq.connect(tmp_path / "x.db")
    c.execute(f"PRAGMA key = \"x'{'11' * 32}'\"")
    assert c.execute("PRAGMA cipher_version").fetchone()[0].startswith("4.")
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    assert c.execute("select vec_version()").fetchone()[0]
    c.execute("create virtual table f using fts5(norm, content='', contentless_delete=1)")
    c.close()


def test_file_readers_import():
    import openpyxl  # noqa: F401
    import platformdirs  # noqa: F401
    import pypdfium2  # noqa: F401
    import xlrd  # noqa: F401


def test_new_libraries_import():
    # Plan 5: web pages to Markdown, and the Sandbox's WebAssembly runtime (its native library).
    import bs4  # noqa: F401
    import docx  # noqa: F401
    import markdownify  # noqa: F401
    import wasmtime

    assert wasmtime.Engine()


@pytest.mark.skipif(
    importlib.util.find_spec("onnxruntime") is None, reason="no onnxruntime here (Intel Mac)"
)
def test_onnxruntime_and_tokenizers_load():
    import onnxruntime
    import tokenizers

    assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
    assert tokenizers.Tokenizer  # the Rust extension imported


def test_pins_are_exact():
    for spec in MODELS:
        assert re.fullmatch(r"[0-9a-f]{40}", spec.revision)
        for f in spec.files:
            assert re.fullmatch(r"[0-9a-f]{64}", f.sha256) and f.size > 0
            assert f"/resolve/{spec.revision}/" in spec.url(f) and "/main/" not in spec.url(f)
    assert sum(s.size for s in MODELS) == 1_173_349_509


def test_data_folder_follows_the_override(data_dir):
    assert settings.data_dir() == data_dir


def test_windows_keeps_the_data_folder_local_never_roaming(monkeypatch, tmp_path):
    # Settings, projects and the 1.2 GB of models must not sync with a roaming office profile.
    monkeypatch.delenv("QSONE_DATA_DIR")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert settings.data_dir() == tmp_path / "Local" / "app.qsmind.one"
    monkeypatch.delenv("LOCALAPPDATA")
    assert settings.data_dir() == Path.home() / "AppData" / "Local" / "app.qsmind.one"


def test_macos_and_linux_data_folders_are_unchanged(monkeypatch, tmp_path):
    monkeypatch.delenv("QSONE_DATA_DIR")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert settings.data_dir() == Path.home() / "Library" / "Application Support" / "app.qsmind.one"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert settings.data_dir() == tmp_path / "share" / "app.qsmind.one"


def test_every_new_text_has_both_languages():
    for name in [
        "PROJECT_NOT_FOUND",
        "PROJECT_KEY_MISSING",
        "FILE_SCANNED_PAGES",
        "NUMBER_NOT_EXACT",
        "MEANING_DOWNLOAD_FAILED",
        "MEANING_FILE_DAMAGED",
        "MEANING_NO_SPACE",
        "MEANING_NOT_ON_THIS_COMPUTER",
        "MEANING_NOT_READY",
        "MEANING_MODEL_FAILED",
        "MEANING_INDEX_FAILED",
        "SEARCH_SUPERSEDED",
        "SEARCH_WORDS_ONLY",
    ]:
        text = getattr(copy, name)
        assert text["en"].strip() and text["ar"].strip()
    assert "local" not in copy.SEARCH_WORDS_ONLY["en"]
    assert "محلي" not in copy.SEARCH_WORDS_ONLY["ar"]


# Plan 6: Deliverables -------------------------------------------------------------------------

FONTS = files("qsone") / "fonts"


def test_typst_and_docx_import_and_typst_uses_only_our_fonts():
    import docx  # noqa: F401
    import pypdfium2
    import typst

    source = (
        b'#let data = json(bytes(sys.inputs.data))\n#set text(font: "Zain", lang: "ar", dir: rtl)\n'
        b"#data.title\n"
    )
    title = "أعمال الحفر - عينة"
    pdf = typst.compile(
        source,
        font_paths=[str(FONTS)],
        ignore_system_fonts=True,
        sys_inputs={"data": json.dumps({"title": title}, ensure_ascii=False)},
    )
    assert b"Zain" in pdf  # the embedded font is ours
    doc = pypdfium2.PdfDocument(pdf)
    try:
        assert doc[0].get_textpage().get_text_range() == title  # reading order kept
    finally:
        doc.close()


def test_fonts_ship_with_their_licence():
    assert (FONTS / "OFL.txt").is_file()
    for name in ["KumbhSans-Variable.ttf", "Zain-Regular.ttf", "Zain-Bold.ttf"]:
        assert (FONTS / name).read_bytes()[:4] == b"\x00\x01\x00\x00", name  # TrueType
    licence = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    assert "KumbhSans Project Authors" in licence and "Zain Project Authors" in licence
    assert "SIL OPEN FONT LICENSE Version 1.1" in licence


PLAN_6_TEXTS = [
    "DELIVERABLE_NOT_FOUND",
    "DELIVERABLE_CALC_REASON",
    "RECORDS_MOVED",
    "TEMPLATE_UNKNOWN",
    "COLUMN_NOT_ALLOWED",
    "NODE_NOT_ALLOWED",
    "OP_UNKNOWN",
    "OP_NOT_IN_TEMPLATE",
    "ROW_NOT_FOUND",
    "NUMBER_WAS_CALCULATED",
    "AMOUNT_IS_COMPUTED",
    "CHANGE_STALE",
    "CHANGE_NOT_PENDING",
    "COMMENT_NOT_FOUND",
    "COMMENT_NEEDS_TEXT",
    "ANCHOR_NOT_FOUND",
    "SIGNOFF_PENDING_CHANGES",
    "SIGNOFF_OPEN_CODE_C",
    "SIGNOFF_NEEDS_CHECK",
    "SIGNOFF_CODE_C",
    "ALREADY_SIGNED_OFF",
    "EXPORT_DRAFT_MARK",
    "SAMPLE_DATA",
    "SOURCES_SHEET",
    "ENTERED_BY_ENGINEER",
    "MANUAL_EDIT_REASON",
    "FILL_XLS_NOT_SUPPORTED",
    "FILL_NEEDS_SIGNOFF",
    "FILL_SHEET_NOT_FOUND",
    "FILL_ROW_MISSING",
    "FILL_ROW_TWICE",
    "FILL_CODE_MISMATCH",
    "FILL_FORMULA_SKIPPED",
    "FILL_COLUMN_LETTER",
    "FILL_PLAN_NOT_FOUND",
    "EXPORT_FORMAT_NOT_ALLOWED",
]


def test_every_plan_6_text_has_both_languages_and_the_same_placeholders():
    def fields(s: str) -> set[str]:
        return {f for _, f, _, _ in Formatter().parse(s) if f is not None}

    for name in PLAN_6_TEXTS:
        text = getattr(copy, name)
        assert set(text) == {"en", "ar"}, name
        assert text["en"].strip() and text["ar"].strip(), name
        assert fields(text["en"]) == fields(text["ar"]), name


def test_plan_6_texts_say_what_the_plan_says():
    assert copy.RECORDS_MOVED == {
        "en": "Update from Project Records",
        "ar": "تحديث من سجلات المشروع",
    }
    assert copy.EXPORT_DRAFT_MARK["ar"] == "مسودة — غير معتمد"
    assert copy.SAMPLE_DATA["ar"] == "بيانات تجريبية"
    assert copy.SOURCES_SHEET["ar"] == "المصادر"
    assert copy.ENTERED_BY_ENGINEER == {"en": "Entered by the engineer", "ar": "أدخله المهندس"}
    title = {"en": "BOQ - sample", "ar": "جدول الكميات - عينة"}
    assert (
        copy.fill(copy.MANUAL_EDIT_REASON, title=title)["ar"]
        == "تعديل يدوي في «جدول الكميات - عينة»"
    )
    assert copy.fill(copy.DELIVERABLE_CALC_REASON, title="x")["en"] == "calculated in «x»"
    for kind in ["text", "number", "calc"]:
        assert kind in copy.COLUMN_NOT_ALLOWED["en"]
    for op in ["set_number", "set_section_title", "set_columns", "set_block", "move_block"]:
        assert op in copy.OP_UNKNOWN["en"]
    assert ".xlsx" in copy.FILL_XLS_NOT_SUPPORTED["en"]
