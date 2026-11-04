"""Native smoke test: SQLCipher, sqlite-vec and FTS5 load on every CI system."""

from qsone import copy


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


def test_every_new_text_has_both_languages():
    for name in [
        "PROJECT_NOT_FOUND",
        "PROJECT_KEY_MISSING",
        "FILE_SCANNED_PAGES",
        "NUMBER_NOT_EXACT",
    ]:
        text = getattr(copy, name)
        assert text["en"].strip() and text["ar"].strip()
