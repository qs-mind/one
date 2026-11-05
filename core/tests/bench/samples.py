"""Sample input files for the bench, written fresh: every name and text says it is a sample.

- an Arabic BOQ in Excel, six columns: code, description, unit, quantity, rate, amount;
- a short specification in Word.
The quantities and rates are sample values made up for testing, not real prices."""

from pathlib import Path

import openpyxl
from docx import Document

BOQ_NAME = "جدول كميات - عينة اختبار (sample BOQ).xlsx"
SPEC_NAME = "مواصفات - عينة اختبار (sample spec).docx"

BOQ_ROWS = [
    ("", "أعمال الحفر (عينة)", "", "", "", ""),
    ("01/01", "حفر في تربة عادية لأي عمق (عينة)", "م3", "1200", "85", "102000"),
    ("01/02", "ردم بناتج الحفر على طبقات (عينة)", "م3", "800", "45", "36000"),
    ("", "أعمال الخرسانة (عينة)", "", "", "", ""),
    ("02/01", "خرسانة عادية للأساسات (عينة)", "م3", "150", "2400", "360000"),
    ("02/02", "خرسانة مسلحة للأسقف (عينة)", "م3", "320", "4100", "1312000"),
]


def write_boq(path: Path) -> Path:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "BOQ"
    sheet.sheet_view.rightToLeft = True
    sheet.append(["جدول كميات - عينة اختبار، أرقام غير حقيقية"])
    sheet.append(["رقم البند", "الوصف", "الوحدة", "الكمية", "الفئة", "القيمة"])
    for code, description, unit, quantity, rate, amount in BOQ_ROWS:
        sheet.append(
            [
                code or None,
                description,
                unit or None,
                int(quantity) if quantity else None,
                int(rate) if rate else None,
                int(amount) if amount else None,
            ]
        )
    book.save(path)
    return path


def write_spec(path: Path) -> Path:
    doc = Document()
    doc.add_heading("مواصفات فنية - عينة اختبار", level=1)
    doc.add_paragraph(
        "هذا الملف عينة لمنصة الاختبار، وليس مواصفات حقيقية. "
        "This file is a test-bench sample, not a real specification."
    )
    doc.add_heading("أعمال الخرسانة (عينة)", level=2)
    doc.add_paragraph("تستخدم خرسانة جاهزة من مورد معتمد، والأسمنت بورتلاندي عادي (نص عينة).")
    doc.save(path)
    return path


def write(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    return [write_boq(folder / BOQ_NAME), write_spec(folder / SPEC_NAME)]
