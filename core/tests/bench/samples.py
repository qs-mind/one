"""Sample input files for the bench, written fresh: every name and text says it is a sample.

- an Arabic BOQ in Excel, six columns: code, description, unit, quantity, rate, amount;
- a short specification in Word;
- a supplier's quote in PDF (its own folder, for the workspace screens: `write_quote`).
The quantities and rates are sample values made up for testing, not real prices."""

import re
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


def write_boq(path: Path, *, priced: bool = True, rows: list[tuple] = BOQ_ROWS) -> Path:
    """The sample BOQ; `priced=False` leaves out its rates and amounts, as a client's BOQ in a
    tender comes."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "المقايسة"  # as the tender pack names it: the bench fake must read the name
    sheet.sheet_view.rightToLeft = True
    sheet.append(["جدول كميات - عينة اختبار، أرقام غير حقيقية"])
    sheet.append(
        ["رقم البند", "الوصف", "الوحدة", "الكمية", "الفئة", "القيمة"][: 6 if priced else 4]
    )
    for code, description, unit, quantity, rate, amount in rows:
        row = [
            code or None,
            description,
            unit or None,
            int(quantity) if quantity else None,
            int(rate) if rate else None,
            int(amount) if amount else None,
        ]
        sheet.append(row[: 6 if priced else 4])
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
    write_cli_samples(folder)
    return [write_boq(folder / BOQ_NAME), write_spec(folder / SPEC_NAME)]


QUOTE_NAME = "عرض أسعار المورد - عينة.pdf"
QUOTE_LINES = (
    "عرض أسعار توريد خرسانة جاهزة بتاريخ 2 نوفمبر 2026 - عينة اختبار، أسعار غير حقيقية",
    "خرسانة مسلحة للأسقف - عينة: 3450 جنيه للمتر المكعب",
)
QUOTE_RATE = "3450"  # the rate the quote gives the concrete's supply, as its line writes it
QUOTE_DATED = "2026-11-02"
# page 2: a quantity for the bench to cite as sample data, so the screens say «الأرقام عينة»
QUOTE_SAMPLE_LINES = ("كمية عينة للاختبار: 320 متر مكعب",)
QUOTE_QUANTITY = "320"


def _visual(line: str) -> str:
    """A line in the visual order an Arabic PDF stores it: reversed, its digit runs kept."""
    return re.sub(r"[0-9][0-9.,]*", lambda m: m.group(0)[::-1], line[::-1])


def write_quote(folder: Path) -> Path:
    """The supplier's quote: its page, supply only (it says nothing of labour), and a page of
    sample data."""
    from tests.samples import sample_pdf

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / QUOTE_NAME
    pages = [[_visual(line) for line in lines] for lines in (QUOTE_LINES, QUOTE_SAMPLE_LINES)]
    path.write_bytes(sample_pdf(pages))
    return path


# The workspace screens' tender: the client's BOQ, unpriced, with a supply-only item whose
# quantity the BOQ leaves blank (the bench cites it from the quote's sample page), and the quote.
WORKSPACE_BOQ_NAME = "جدول كميات المناقصة - عينة اختبار.xlsx"
SUPPLY_CODE = "02/03"
WORKSPACE_ROWS = [*BOQ_ROWS, (SUPPLY_CODE, "توريد خرسانة جاهزة للأسقف (عينة)", "م3", "", "", "")]


def write_workspace(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    boq = write_boq(folder / WORKSPACE_BOQ_NAME, priced=False, rows=WORKSPACE_ROWS)
    return [boq, write_quote(folder)]


TENDER_NAME = "مناقصة عينة - منصة الاختبار"


def write_tender(root: Path) -> Path:
    """A sample tender folder, as an engineer gets one: Arabic names, a nested folder, a zip with a
    folder inside, a RAR One keeps but does not read, and the same file twice."""
    import zipfile

    folder = root / TENDER_NAME
    (folder / "02 جداول").mkdir(parents=True, exist_ok=True)
    (folder / "نسخة").mkdir(exist_ok=True)
    write_boq(folder / "02 جداول" / BOQ_NAME)
    write_spec(folder / SPEC_NAME)
    (folder / "نسخة" / SPEC_NAME).write_bytes((folder / SPEC_NAME).read_bytes())  # a duplicate
    with zipfile.ZipFile(folder / "رسومات - عينة.zip", "w") as z:
        z.writestr("مخططات/ملاحظات اللوحات - عينة.txt", "لوحات عينة لمنصة الاختبار، مش حقيقية.\n")
    (folder / "رسومات - عينة.rar").write_bytes(b"Rar!\x1a\x07\x00 bench sample, not a real archive")
    return folder


OLD_NAME = "شغل قديم - عينة"
OLD_PROJECTS = ("برج إداري - عينة قديمة", "مدرسة - عينة قديمة")


def write_old(root: Path) -> Path:
    """A folder of old work: one folder per finished project, each with its specification."""
    folder = root / OLD_NAME
    for name in OLD_PROJECTS:
        (folder / name).mkdir(parents=True, exist_ok=True)
        write_spec(folder / name / SPEC_NAME)
    return folder


def write_cli_samples(folder: Path) -> None:
    """Small job-specific inputs. Every value is sample data, never a tender copy."""
    import typst

    from tests.samples import sample_pdf, sample_xls

    rows = [["Item", "Description", "Unit", "Quantity", "Rate", "Amount"]]
    rows += [
        [
            code,
            desc,
            unit,
            float(qty) if qty else "",
            float(rate) if rate else "",
            float(amount) if amount else "",
        ]
        for code, desc, unit, qty, rate, amount in BOQ_ROWS
    ]
    (folder / "sample-boq.xls").write_bytes(sample_xls({"Sample": rows}))
    (folder / "sample-conditions.pdf").write_bytes(
        sample_pdf(
            [
                ["Sample contract data: delay damages 0.2% per day; cap 10%."],
                ["Sample tender data: bid validity 180 days; bid security 350000 USD."],
            ]
        )
    )
    (folder / "sample-map-contract.pdf").write_bytes(
        sample_pdf(
            [
                [
                    "14.3 Sample contract data. Retention 10%. Advance payment: ____"
                    if p == 58
                    else "Sample bid data. Bid validity 180 days. See Clause 14.3"
                    if p == 26
                    else f"Sample page {p}"
                ]
                for p in range(1, 59)
            ]
        )
    )
    (folder / "sample-scan.pdf").write_bytes(sample_pdf([[]]))
    (folder / "sample-market.csv").write_text(
        "Month,Material,Price,Unit\n2026-09,Sample rebar,3200,EGP/t\n"
        "2026-08,Sample cement,1500,EGP/t\n",
        encoding="utf-8",
    )
    doc = Document()
    doc.add_paragraph("Sample booklet: offers must be submitted electronically.")
    doc.save(folder / "sample-booklet.docx")
    estimate = openpyxl.Workbook()
    ws = estimate.active
    ws.title = "Sample benchmark"
    ws.append(["Item", "Description", "Unit", "Quantity", "Rate", "Amount"])
    ws.append(["LOW", "Sample office low", "m2", 5000, 5900, 29500000])
    ws.append(["HIGH", "Sample office high", "m2", 5000, 7300, 36500000])
    estimate.save(folder / "sample-estimate.xlsx")
    source = "\n".join(
        [
            "#set page(width: 650pt, height: 500pt, margin: 30pt)",
            '#set text(font: "DejaVu Sans", size: 10pt)',
            "Sample BOQ: invented test quantities and prices.",
            "#table(columns: (45pt, 170pt, 45pt, 70pt, 70pt, 80pt), inset: 6pt,",
            "[Item], [Description], [Unit], [Quantity], [Rate], [Amount],",
            "[], [Concrete works sample], [], [], [], [],",
            "[1], [Concrete sample], [m3], [12.50], [20.00], [250.00],",
            "[2], [Concrete sample], [m3], [2.00], [30.00], [60.00])",
        ]
    )
    (folder / "sample-boq.pdf").write_bytes(typst.compile(source.encode()))
