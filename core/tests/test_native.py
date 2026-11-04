"""Native smoke test: SQLCipher, sqlite-vec, FTS5, onnxruntime and tokenizers load on every CI
system."""

import importlib.util
import re
import sys
from pathlib import Path

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
