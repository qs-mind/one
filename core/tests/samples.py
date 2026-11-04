"""Synthetic sample files («عينة» / "sample"), made inside the tests. Never real tender files."""

import datetime as dt
import io

import openpyxl
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
