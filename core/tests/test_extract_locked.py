"""A workbook locked with a password says so and asks for an open copy; an empty workbook is noted
as empty (tender day, 5 Nov 2026: the locked one was «ONE لسه مش بيقرا النوع ده من الملفات»
the empty one "read" with no note). Synthetic files only."""

import io

import openpyxl

from qsone import copy
from qsone.records.extract import extract

# The start of an Office file locked with a password: an OLE2 compound file whose directory names
# the EncryptionInfo and EncryptedPackage streams (UTF-16 names), not the zip an open .xlsx is.
_CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
LOCKED = _CFB + "EncryptionInfo".encode("utf-16-le") + "EncryptedPackage".encode("utf-16-le")


def test_a_locked_workbook_says_it_is_locked():
    for name in ("مقايسة بكلمة سر - عينة.xlsx", "عقد - عينة.docx"):
        x = extract(name, LOCKED)
        assert (x.status, x.note) == ("unreadable", "FILE_LOCKED")
    assert "password" in copy.FILE_LOCKED["en"] and "open copy" in copy.FILE_LOCKED["en"]
    assert "باسورد" in copy.FILE_LOCKED["ar"]


def test_an_old_office_file_is_still_not_read_yet():
    """An OLE2 file named .xlsx with no encrypted package is not a locked workbook."""
    x = extract("ملف - عينة.xlsx", _CFB)
    assert x.note == "FILE_NOT_READ_YET"


def test_an_empty_workbook_is_noted_as_empty():
    wb = openpyxl.Workbook()
    out = io.BytesIO()
    wb.save(out)
    x = extract("شيت فاضي - عينة.xlsx", out.getvalue())
    assert (x.status, x.pieces, x.note) == ("read", [], "FILE_SHEETS_EMPTY")
    assert set(copy.FILE_SHEETS_EMPTY) == {"en", "ar"}
