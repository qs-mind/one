"""PDF pages as PNG images, in memory: no temp file, no page image on disk.

Plan 7 defines this module for the canvas; Plan 5 needs it first, to send a scanned page to the
engineer's AI. pdfium renders to RGBA, and `_png` writes the PNG by hand (IHDR, one IDAT, IEND).
PDFium operations are serialized process-wide."""

import math
import struct
import zlib

import pypdfium2
import pypdfium2.raw as pdfium_c

from qsone.records.pdfium_guard import PDFIUM, pdfium_locked


@pdfium_locked
def page_count(pdf_bytes: bytes) -> int:
    doc = pypdfium2.PdfDocument(pdf_bytes)
    try:
        return len(doc)
    finally:
        doc.close()


def page_png(pdf_bytes: bytes, page: int, width: int) -> bytes:
    """Page `page` (from 1) as a PNG `width` pixels wide, on white. Raises `IndexError` for a
    page the file does not have."""
    with PDFIUM:
        doc = pypdfium2.PdfDocument(pdf_bytes)
        try:
            if not 1 <= page <= len(doc):
                raise IndexError(f"page {page} of {len(doc)}")
            pdf_page = doc[page - 1]
            try:
                # pdfium's size is ceil(points * scale): step the scale down past float error.
                scale = width / pdf_page.get_width()
                while math.ceil(pdf_page.get_width() * scale) > width:
                    scale = math.nextafter(scale, 0)
                bitmap = pdf_page.render(
                    scale=scale,
                    rev_byteorder=True,
                    force_bitmap_format=pdfium_c.FPDFBitmap_BGRA,
                    fill_color=(255, 255, 255, 255),
                )
                try:
                    data = bytes(bitmap.buffer)
                    return _png(bitmap.width, bitmap.height, data, bitmap.stride)
                finally:
                    bitmap.close()
            finally:
                pdf_page.close()
        finally:
            doc.close()


def _png(width: int, height: int, rgba: bytes, stride: int) -> bytes:
    """An 8-bit RGBA PNG: filter 0 on every row, zlib level 6."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    row = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride : y * stride + row] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def image_png(data: bytes, width: int | None = None) -> bytes:
    """Decode a standalone image in memory; keep original pixel coordinates for OCR."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image.load()
        image = image.convert("RGB")
        if width is not None:
            image = image.resize(
                (width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS
            )
        out = io.BytesIO()
        image.save(out, format="PNG")
        return out.getvalue()


# AI providers refuse large pictures (Anthropic: 10 MB per image) and scale big ones down anyway.
MODEL_EDGE = 2576
MODEL_BYTES = 3_500_000


def for_model(png: bytes) -> tuple[bytes, str]:
    """A picture an AI provider accepts: at most MODEL_EDGE px on its long side and MODEL_BYTES,
    as PNG when that fits, else JPEG. Returns the bytes and their media type."""
    import io

    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(png))
    except UnidentifiedImageError:
        return png, "image/png"  # not a picture PIL knows: the provider says what is wrong
    with image:
        if max(image.size) <= MODEL_EDGE and len(png) <= MODEL_BYTES:
            return png, "image/png"
        image = image.convert("RGB")
        image.thumbnail((MODEL_EDGE, MODEL_EDGE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        if out.tell() <= MODEL_BYTES:
            return out.getvalue(), "image/png"
        for quality in (90, 80, 70, 60):
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=quality)
            if out.tell() <= MODEL_BYTES:
                break
        return out.getvalue(), "image/jpeg"
