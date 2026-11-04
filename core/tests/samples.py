"""Synthetic sample files («عينة» / "sample"), made inside the tests. Never real tender files."""

import datetime as dt
import io
import struct
import zipfile
import zlib
from xml.sax import saxutils

import openpyxl
import pytest
import xlwt


def sample_pdf(pages: list[list[str]]) -> bytes:
    """A hand-written PDF, one string per line. Each string must be in visual order, as Arabic PDFs
    store their glyphs. An empty page has no text layer, like a scanned page. A Type1 Helvetica font
    with a ToUnicode map gives each character a one-byte code, so no font file is needed."""
    chars = sorted({c for page in pages for line in page for c in line} - {" "})
    assert len(chars) <= 223, "too many different characters for a one-byte font"
    codes = {" ": 32} | {c: n for n, c in enumerate(chars, start=33)}
    cmap = "".join(f"<{n:02X}> <{c.encode('utf-16-be').hex().upper()}>\n" for c, n in codes.items())
    to_unicode = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
        "1 begincodespacerange <00> <FF> endcodespacerange\n"
        f"{len(codes)} beginbfchar\n{cmap}endbfchar\n"
        "endcmap CMapName currentdict /CMap defineresource pop end end\n"
    ).encode()

    def stream(data: bytes) -> bytes:
        return b"<< /Length %d >>\nstream\n%s\nendstream" % (len(data), data)

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>"
        % (b" ".join(b"%d 0 R" % (5 + 2 * i) for i in range(len(pages))), len(pages)),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 32 /LastChar 255"
        b" /Widths [%s] /ToUnicode 4 0 R >>" % b" ".join([b"500"] * 224),
        stream(to_unicode),
    ]
    for i, lines in enumerate(pages):
        text = "".join(f"<{bytes(codes[c] for c in line).hex()}> Tj T*\n" for line in lines)
        content = f"BT /F1 12 Tf 16 TL 72 770 Td\n{text}ET".encode() if lines else b""
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842]"
            b" /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (6 + 2 * i)
        )
        objects.append(stream(content))

    out = bytearray(b"%PDF-1.7\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def sample_xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def sample_xls(sheets: dict[str, list[list]]) -> bytes:
    wb = xlwt.Workbook(encoding="utf-8")
    date = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    for name, rows in sheets.items():
        ws = wb.add_sheet(name)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if isinstance(value, dt.date):
                    ws.write(r, c, value, date)
                elif value is not None:
                    ws.write(r, c, value)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# Plan 6: Deliverables -------------------------------------------------------------------------

SAMPLE_ACTOR = "lead_qs"
SAMPLE_TITLE = "بيانات تجريبية - عينة"
SAMPLE_DATED = "2026-11-01"

# The base BOQ: (section, code, description, quantity or None, unit, rate). The descriptions
# carry tatweel («حفـــر»); 03/02 is Plan 3's item (120 m3 at 39850.50 EGP); 2-4 is «فئة فقط».
_BASE_ITEMS = [
    ("أعمال الحفر", "1-1", "حفـــر في أرض عادية حتى منسوب التأسيس - عينة", "5555", "m3", "14"),
    ("أعمال الحفر", "1-2", "ردم بناتج الحفـــر على طبقات - عينة", "1200", "m3", "22.50"),
    ("أعمال الخرسانة", "2-1", "خرسانة عادية للأساسات - عينة", "85.5", "m3", "2750"),
    ("أعمال الخرسانة", "03/02", "خرسانة مسلحة للأسقـــف - عينة", "120", "m3", "39850.50"),
    ("أعمال الخرسانة", "2-3", "بياض مـحارة للحوائط - عينة", "640", "م2", "95"),
]
_RATE_ONLY = ("أعمال الخرسانة", "2-4", "دهانات بلاستيك للحوائط - عينة", None, "م2", "120")
RATE_ONLY_NOTE = "فئة فقط"


def sample_source(rec) -> str:
    """The one sample source (kind `sample`), made on first use."""
    from qsone.records import ledger

    with rec.read() as c:
        row = c.execute(
            "SELECT id FROM sources WHERE kind = 'sample' AND title = ?", (SAMPLE_TITLE,)
        ).fetchone()
    if row:
        return row[0]
    return ledger.add_source(
        rec, kind="sample", title=SAMPLE_TITLE, actor=SAMPLE_ACTOR, dated=SAMPLE_DATED
    )


def sample_boq_rows(rec, rows: int = 6, *, with_rate_only: bool = True) -> list[dict]:
    """Writes `rows` BOQ items with sample numbers and returns the Sheet's rows for
    `store.create`: `{"section": title, "level": 1}` before each section's items, then
    `{"item_id": id}`. Past the base six, items «بند إضافي - عينة n» go 50 to a section."""
    from qsone.records import ledger

    base = [*_BASE_ITEMS, _RATE_ONLY] if with_rate_only else list(_BASE_ITEMS)
    plan = base[:rows]
    for n in range(len(plan) + 1, rows + 1):
        k = (n - len(base) - 1) // 50 + 1
        plan.append(
            (f"أعمال إضافية - عينة {k}", f"9-{n}", f"بند إضافي - عينة {n}", str(n), "m3", "10.25")
        )
    source = sample_source(rec)
    out: list[dict] = []
    section = None
    with rec.write(SAMPLE_ACTOR) as c:
        at = rec.clock()
        for title, code, description, quantity, unit, rate in plan:
            if title != section:
                out.append({"section": title, "level": 1})
                section = title
            fields = {"description": description}
            if quantity is None:
                fields["quantity_note"] = RATE_ONLY_NOTE
            item = ledger.write_item(
                c, at=at, actor=SAMPLE_ACTOR, kind="boq_item", code=code, fields=fields
            )
            numbers = {"rate": (rate, "EGP")} | ({"quantity": (quantity, None)} if quantity else {})
            for name, (value, currency) in numbers.items():
                ledger.write_number(
                    c,
                    at=at,
                    actor=SAMPLE_ACTOR,
                    item_id=item,
                    name=name,
                    value=value,
                    unit=unit,
                    currency=currency,
                    source_id=source,
                    dated=SAMPLE_DATED,
                )
            out.append({"item_id": item})
    return out


def sample_sheet(rec, rows: int = 6, *, with_rate_only: bool = True) -> str:
    """A priced BOQ Sheet «جدول الكميات - عينة», made with `store.create` (Plan 6 Task 2), so
    its amounts and totals are saved calculations. Skips the test until Task 2 is merged."""
    store = pytest.importorskip("qsone.deliverables.store")
    return store.create(
        rec,
        kind="sheet",
        variant="boq",
        title="جدول الكميات - عينة",
        language="ar",
        actor=SAMPLE_ACTOR,
        rows=sample_boq_rows(rec, rows, with_rate_only=with_rate_only),
    )


def sample_document_blocks(sheet_id: str) -> list[dict]:
    """A covering letter: an h1, two paragraphs (one with a `cell` reference to the sheet's grand
    total) and «الأسعار سارية حالياً لمدة ٣٠ يوماً», the only digits outside a reference."""

    def p(*children) -> dict:
        return {"type": "p", "children": list(children)}

    total = {
        "type": "cell",
        "deliverable": sheet_id,
        "row": "total",
        "column": "amount",
        "children": [{"text": ""}],
    }
    return [
        {"type": "h1", "children": [{"text": "خطاب تقديم العطاء - عينة"}]},
        p({"text": "السادة / شركة التطوير العقاري - عينة، تحية طيبة وبعد،"}),
        p(
            {"text": "نتشرف بتقديم عطائنا بإجمالي "},
            total,
            {"text": " جنيه مصري حسب جدول الكميات المرفق."},
        ),
        p({"text": "الأسعار سارية حالياً لمدة ٣٠ يوماً"}),
    ]


def sample_document(rec, sheet_id: str) -> str:
    """The covering letter as a Document (Plan 6 Task 2). Skips the test until Task 2 is merged."""
    store = pytest.importorskip("qsone.deliverables.store")
    return store.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب العطاء - عينة",
        language="ar",
        actor=SAMPLE_ACTOR,
        blocks=sample_document_blocks(sheet_id),
    )


# The client's own BOQ, written as Excel writes it -------------------------------------------

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_X14AC = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
# Client rows 12-17: (code as the client wrote it, description, unit, quantity). Row 15 writes
# 03/02 in Arabic-Indic digits; row 17 is rate-only, its quantity cell holds text.
CLIENT_ROWS = [
    ("1-1", "حفـــر في أرض عادية حتى منسوب التأسيس - عينة", "م3", "5555"),
    ("1-2", "ردم بناتج الحفـــر على طبقات - عينة", "م3", "1200"),
    ("2-1", "خرسانة عادية للأساسات - عينة", "م3", "85.5"),
    ("٠٣/٠٢", "خرسانة مسلحة للأسقـــف - عينة", "م3", "120"),
    ("2-3", "بياض مـحارة للحوائط - عينة", "م2", "640"),
    ("2-4", "دهانات بلاستيك للحوائط - عينة", "م2", RATE_ONLY_NOTE),
]
CLIENT_FIRST_ROW = 12  # the header is row 11; the total is row 19
VBA_PROJECT = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"vbaProject - sample " * 8


def _png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A plain one-colour PNG, written by hand (no Pillow)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _client_parts(xlsm: bool) -> dict[str, bytes]:
    strings: list[str] = []

    def s(text: str) -> str:
        if text not in strings:
            strings.append(text)
        return f'<c r="{{r}}" s="{{st}}" t="s"><v>{strings.index(text)}</v></c>'

    def cell(ref: str, style: int, body: str = "") -> str:
        return f'<c r="{ref}" s="{style}"{body and ">" + body + "</c>" or "/>"}'

    def text(ref: str, style: int, value: str) -> str:
        return s(value).format(r=ref, st=style)

    def row(n: int, cells: list[str], extra: str = "") -> str:
        return f'<row r="{n}" spans="1:6"{extra} x14ac:dyDescent="0.25">{"".join(cells)}</row>'

    rows = [
        row(1, [text("A1", 1, "جدول كميات مبنى إداري - عينة")], ' ht="24" customHeight="1"'),
        row(2, [text("A2", 1, "المرحلة الأولى - عينة")]),
        row(4, [text("A4", 0, "المالك: شركة التطوير العقاري - عينة")]),
        row(5, [text("A5", 0, "العملة: جنيه مصري")]),
        row(
            11,
            [
                text(ref, 2, label)
                for ref, label in zip(
                    ["A11", "B11", "C11", "D11", "E11", "F11"],
                    ["البند", "بيان الأعمال", "الوحدة", "الكمية", "الفئة", "الإجمالي"],
                    strict=True,
                )
            ],
            ' ht="30" customHeight="1"',
        ),
    ]
    for i, (code, description, unit, quantity) in enumerate(CLIENT_ROWS):
        n = CLIENT_FIRST_ROW + i
        quantity_cell = (
            text(f"D{n}", 3, quantity)
            if quantity == RATE_ONLY_NOTE
            else cell(f"D{n}", 4, f"<v>{quantity}</v>")
        )
        if n == 12:
            amount = cell("F12", 6, "<f>D12*E12</f><v>0</v>")
        elif n == 13:
            amount = cell("F13", 6, '<f t="shared" ref="F13:F16" si="0">D13*E13</f><v>0</v>')
        elif n <= 16:
            amount = cell(f"F{n}", 6, '<f t="shared" si="0"/><v>0</v>')
        else:
            amount = cell(f"F{n}", 6)
        rate = [] if n == 14 else [cell(f"E{n}", 5)]  # E14 is missing, as Excel leaves it
        cells = [text(f"A{n}", 3, code), text(f"B{n}", 3, description), text(f"C{n}", 3, unit)]
        rows.append(row(n, [*cells, quantity_cell, *rate, amount]))
    rows.append(
        row(
            19,
            [
                text("A19", 7, "الإجمالي"),
                *(cell(f"{c}19", 7) for c in "BCDE"),
                cell("F19", 7, "<f>SUM(F12:F17)</f><v>0</v>"),
            ],
        )
    )
    sheet1 = (
        f'{_HEAD}<worksheet xmlns="{_MAIN}" xmlns:r="{_REL}" xmlns:mc="{_MC}"'
        f' mc:Ignorable="x14ac" xmlns:x14ac="{_X14AC}">'
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:F19"/>'
        '<sheetViews><sheetView rightToLeft="1" tabSelected="1" workbookViewId="0">'
        '<pane ySplit="11" topLeftCell="A12" activePane="bottomLeft" state="frozen"/>'
        '<selection pane="bottomLeft" activeCell="E12" sqref="E12"/></sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15" x14ac:dyDescent="0.25"/>'
        '<cols><col min="1" max="1" width="9" customWidth="1"/>'
        '<col min="2" max="2" width="48" customWidth="1"/>'
        '<col min="3" max="4" width="10" customWidth="1"/>'
        '<col min="5" max="5" width="14" style="5" customWidth="1"/>'
        '<col min="6" max="6" width="16" customWidth="1"/></cols>'
        f"<sheetData>{''.join(rows)}</sheetData>"
        '<mergeCells count="3"><mergeCell ref="A1:F1"/><mergeCell ref="A2:F2"/>'
        '<mergeCell ref="A19:E19"/></mergeCells>'
        '<conditionalFormatting sqref="F12:F17"><cfRule type="cellIs" dxfId="0" priority="1"'
        ' operator="greaterThan"><formula>1000000</formula></cfRule></conditionalFormatting>'
        '<dataValidations count="1"><dataValidation type="decimal" operator="greaterThanOrEqual"'
        ' allowBlank="1" showErrorMessage="1" sqref="E12:E17"><formula1>0</formula1>'
        "</dataValidation></dataValidations>"
        '<printOptions horizontalCentered="1"/>'
        '<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '<pageSetup paperSize="9" orientation="landscape" fitToHeight="0"/>'
        '<drawing r:id="rId1"/></worksheet>'
    )
    sheet2 = (
        f'{_HEAD}<worksheet xmlns="{_MAIN}" xmlns:r="{_REL}" xmlns:mc="{_MC}"'
        f' mc:Ignorable="x14ac" xmlns:x14ac="{_X14AC}"><dimension ref="A1:B1"/>'
        '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15" x14ac:dyDescent="0.25"/><sheetData>'
        + row(
            1,
            [text("A1", 2, "إجمالي جدول الكميات - عينة"), cell("B1", 7, "<f>BOQ!F19</f><v>0</v>")],
        )
        + '</sheetData><pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75"'
        ' header="0.3" footer="0.3"/></worksheet>'
    )
    shared = "".join(f'<si><t xml:space="preserve">{saxutils.escape(t)}</t></si>' for t in strings)
    count = sheet1.count('t="s"') + sheet2.count('t="s"')
    shared_strings = (
        f'{_HEAD}<sst xmlns="{_MAIN}" count="{count}" uniqueCount="{len(strings)}">{shared}</sst>'
    )
    border = "<left/><right/><top/><bottom/><diagonal/>"
    thin = "".join(
        f'<{side} style="thin"><color rgb="FF6E6A64"/></{side}>'
        for side in ["left", "right", "top", "bottom"]
    )
    styles = (
        f'{_HEAD}<styleSheet xmlns="{_MAIN}" xmlns:mc="{_MC}" mc:Ignorable="x14ac"'
        f' xmlns:x14ac="{_X14AC}">'
        '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
        '<fonts count="3" x14ac:knownFonts="1">'
        '<font><sz val="11"/><name val="Arial"/><family val="2"/></font>'
        '<font><b/><sz val="14"/><name val="Arial"/><family val="2"/></font>'
        '<font><b/><sz val="11"/><name val="Arial"/><family val="2"/></font></fonts>'
        '<fills count="4"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF2EEE7"/>'
        '<bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF9F8F4"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        f'<borders count="2"><border>{border}</border><border>{thin}<diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="8"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"'
        ' applyAlignment="1"><alignment horizontal="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1"'
        ' applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"'
        ' applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"'
        ' applyBorder="1"/>'
        '<xf numFmtId="164" fontId="0" fillId="3" borderId="1" xfId="0" applyNumberFormat="1"'
        ' applyFill="1" applyBorder="1" applyProtection="1"><protection locked="0"/></xf>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"'
        ' applyBorder="1"/>'
        '<xf numFmtId="164" fontId="2" fillId="2" borderId="1" xfId="0" applyNumberFormat="1"'
        ' applyFont="1" applyFill="1" applyBorder="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="1"><dxf><font><b/><color rgb="FFA6491B"/></font></dxf></dxfs>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium2"'
        ' defaultPivotStyle="PivotStyleLight16"/></styleSheet>'
    )
    workbook = (
        f'{_HEAD}<workbook xmlns="{_MAIN}" xmlns:r="{_REL}">'
        '<fileVersion appName="xl" lastEdited="7" lowestEdited="7" rupBuild="27425"/>'
        + ('<workbookPr codeName="ThisWorkbook"/>' if xlsm else "<workbookPr/>")
        + '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800"'
        ' windowHeight="12300"/></bookViews>'
        '<sheets><sheet name="BOQ" sheetId="1" r:id="rId1"/>'
        '<sheet name="ملخص" sheetId="2" r:id="rId2"/></sheets>'
        '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">BOQ!$A$1:$F$19'
        '</definedName><definedName name="BOQ_Total">BOQ!$F$19</definedName></definedNames>'
        '<calcPr calcId="191029"/></workbook>'
    )

    def rels(entries: list[tuple[str, str, str]]) -> str:
        body = "".join(
            f'<Relationship Id="{i}" Type="{t}" Target="{target}"/>' for i, t, target in entries
        )
        return f'{_HEAD}<Relationships xmlns="{_PKG}">{body}</Relationships>'

    office = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook_rels = [
        ("rId1", f"{office}/worksheet", "worksheets/sheet1.xml"),
        ("rId2", f"{office}/worksheet", "worksheets/sheet2.xml"),
        ("rId3", f"{office}/styles", "styles.xml"),
        ("rId4", f"{office}/sharedStrings", "sharedStrings.xml"),
    ]
    if xlsm:
        vba = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
        workbook_rels.append(("rId5", vba, "vbaProject.bin"))
    drawing = (
        f'{_HEAD}<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
        'spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        "<xdr:oneCellAnchor><xdr:from><xdr:col>0</xdr:col><xdr:colOff>0</xdr:colOff>"
        "<xdr:row>2</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>"
        '<xdr:ext cx="952500" cy="476250"/><xdr:pic><xdr:nvPicPr>'
        '<xdr:cNvPr id="2" name="شعار - عينة"/><xdr:cNvPicPr><a:picLocks noChangeAspect="1"/>'
        f'</xdr:cNvPicPr></xdr:nvPicPr><xdr:blipFill><a:blip xmlns:r="{_REL}" r:embed="rId1"/>'
        "<a:stretch><a:fillRect/></a:stretch></xdr:blipFill><xdr:spPr><a:xfrm>"
        '<a:off x="0" y="0"/><a:ext cx="952500" cy="476250"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>'
        "<xdr:clientData/></xdr:oneCellAnchor></xdr:wsDr>"
    )
    main = (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
        if xlsm
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    ml = "application/vnd.openxmlformats-officedocument"
    overrides = {
        "/xl/workbook.xml": main,
        "/xl/worksheets/sheet1.xml": f"{ml}.spreadsheetml.worksheet+xml",
        "/xl/worksheets/sheet2.xml": f"{ml}.spreadsheetml.worksheet+xml",
        "/xl/drawings/drawing1.xml": f"{ml}.drawing+xml",
        "/xl/styles.xml": f"{ml}.spreadsheetml.styles+xml",
        "/xl/sharedStrings.xml": f"{ml}.spreadsheetml.sharedStrings+xml",
        "/docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
        "/docProps/app.xml": f"{ml}.extended-properties+xml",
    }
    defaults = {
        "rels": "application/vnd.openxmlformats-package.relationships+xml",
        "xml": "application/xml",
        "png": "image/png",
    } | ({"bin": "application/vnd.ms-office.vbaProject"} if xlsm else {})
    content_types = (
        f'{_HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in defaults.items())
        + "".join(f'<Override PartName="{p}" ContentType="{t}"/>' for p, t in overrides.items())
        + "</Types>"
    )
    core = (
        f"{_HEAD}<cp:coreProperties xmlns:cp="
        '"http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>جدول كميات - عينة</dc:title><dc:creator>عينة</dc:creator>"
        '<dcterms:created xsi:type="dcterms:W3CDTF">2026-11-01T00:00:00Z</dcterms:created>'
        "</cp:coreProperties>"
    )
    app = (
        f'{_HEAD}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
        'extended-properties"><Application>Microsoft Excel</Application></Properties>'
    )
    parts = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": rels(
            [
                ("rId1", f"{office}/officeDocument", "xl/workbook.xml"),
                ("rId2", f"{_PKG}/metadata/core-properties", "docProps/core.xml"),
                ("rId3", f"{office}/extended-properties", "docProps/app.xml"),
            ]
        ),
        "xl/workbook.xml": workbook,
        "xl/_rels/workbook.xml.rels": rels(workbook_rels),
        "xl/worksheets/sheet1.xml": sheet1,
        "xl/worksheets/sheet2.xml": sheet2,
        "xl/worksheets/_rels/sheet1.xml.rels": rels(
            [("rId1", f"{office}/drawing", "../drawings/drawing1.xml")]
        ),
        "xl/drawings/drawing1.xml": drawing,
        "xl/drawings/_rels/drawing1.xml.rels": rels(
            [("rId1", f"{office}/image", "../media/image1.png")]
        ),
        "xl/styles.xml": styles,
        "xl/sharedStrings.xml": shared_strings,
        "docProps/core.xml": core,
        "docProps/app.xml": app,
    }
    out = {name: body.encode("utf-8") for name, body in parts.items()}
    out["xl/media/image1.png"] = _png(40, 20, (0xA6, 0x49, 0x1B))
    if xlsm:
        out["xl/vbaProject.bin"] = VBA_PROJECT
    return out


def sample_client_xlsx(*, xlsm: bool = False) -> bytes:
    """A client's BOQ built the way Excel writes one, as raw XML: shared strings,
    `mc:Ignorable="x14ac"` with `x14ac:dyDescent`, a right-to-left sheet «BOQ» frozen below the
    header (row 11), merged title cells, styled empty rate cells (E12-E17, but E14 is missing and
    takes its column's style), amounts `=D12*E12` and a shared formula F13:F16, a total
    `=SUM(F12:F17)`, a second sheet «ملخص», a defined name, a data validation, a conditional
    format, a print area and a logo image. `xlsm=True` adds a `vbaProject.bin`."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, data in _client_parts(xlsm).items():
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 1, 0, 0, 0))
            info.compress_type = (
                zipfile.ZIP_STORED if name.endswith(".png") else zipfile.ZIP_DEFLATED
            )
            z.writestr(info, data)
    return out.getvalue()
