"""PDF number locations in displayed page points, top-left origin, entirely in memory."""

import ctypes
import json
import math
import re
from contextlib import closing
from decimal import Decimal, InvalidOperation

import pypdfium2 as pdfium
import pypdfium2.raw as raw

from qsone import copy
from qsone.records import files
from qsone.records.project import Records, RecordsError

_TOKEN = re.compile(r"(?<![\w.,٬٫])[+-]?\d[\d,٬]*(?:[.٫]\d+)?(?![\w.,٬٫])")


def _number(text):
    try:
        return Decimal(text.replace(",", "").replace("٬", "").replace("٫", "."))
    except InvalidOperation:
        return None


def pdf_numbers(data: bytes, page: int) -> dict:
    """Native numeric tokens and glyph boxes in the displayed CropBox/rotation frame."""
    try:
        with pdfium.PdfDocument(data) as doc:
            if not 1 <= page <= len(doc):
                raise RecordsError(copy.PAGE_NOT_FOUND, status=404, field="page")
            with closing(doc[page - 1]) as p:
                width, height = p.get_size()
                boxes = []
                with closing(p.get_textpage()) as text:
                    # One Unicode scalar per PDFium char index, not text-string offsets.
                    chars = "".join(
                        chr(raw.FPDFText_GetUnicode(text, i)) for i in range(text.count_chars())
                    )
                    for match in _TOKEN.finditer(chars):
                        points = []
                        for i in range(match.start(), match.end()):
                            left, bottom, right, top = text.get_charbox(i)
                            for x, y in (
                                (left, bottom),
                                (left, top),
                                (right, bottom),
                                (right, top),
                            ):
                                dx, dy = ctypes.c_int(), ctypes.c_int()
                                # Sub-point precision, with page rotation/crop.
                                raw.FPDF_PageToDevice(
                                    p,
                                    0,
                                    0,
                                    round(width * 1000),
                                    round(height * 1000),
                                    0,
                                    x,
                                    y,
                                    dx,
                                    dy,
                                )
                                points.append((dx.value / 1000, dy.value / 1000))
                        box = [
                            max(0, min(x for x, _ in points)),
                            max(0, min(y for _, y in points)),
                            min(width, max(x for x, _ in points)),
                            min(height, max(y for _, y in points)),
                        ]
                        if box[0] < box[2] and box[1] < box[3]:
                            boxes.append({"text": match.group(), "box": box})
                return {"width": width, "height": height, "numbers": boxes}
    except RecordsError:
        raise
    except Exception:
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None


def page_boxes(rec: Records, file_id: str, page: int, value: str = "") -> dict:
    data = files.read_original(rec, file_id)
    found = pdf_numbers(data, page)
    target = _number(value) if value else None
    boxes = [
        n["box"] for n in found["numbers"] if target is not None and _number(n["text"]) == target
    ]
    if target is not None and target.is_finite():
        with rec.read() as conn:
            rows = conn.execute(
                "SELECT locator, text FROM chunks WHERE file_id = ?"
                " AND json_extract(locator, '$.page') = ?"
                " AND json_extract(locator, '$.read_by') IS NOT NULL ORDER BY seq",
                (file_id, page),
            ).fetchall()
        for locator, text in rows:
            loc = json.loads(locator)
            if _number(text) == target and loc.get("box") and loc["box"] not in boxes:
                boxes.append(loc["box"])
    return {"width": found["width"], "height": found["height"], "boxes": boxes}


def check_region(rec: Records, anchor) -> dict:
    if not isinstance(anchor, dict) or anchor.get("kind") != "file_region":
        raise RecordsError(copy.ANCHOR_NOT_FOUND, status=422, field="anchor")
    file_id, page, box = (anchor.get(k) for k in ("file_id", "page", "box"))
    if not isinstance(file_id, str) or type(page) is not int or page < 1:
        raise RecordsError(copy.ANCHOR_NOT_FOUND, status=422, field="anchor.page")
    if (
        not isinstance(box, (list, tuple))
        or len(box) != 4
        or not all(type(n) in (float, int) and math.isfinite(n) for n in box)
    ):
        raise RecordsError(copy.ANCHOR_NOT_FOUND, status=422, field="anchor.box")
    size = page_boxes(rec, file_id, page)
    if not (0 <= box[0] < box[2] <= size["width"] and 0 <= box[1] < box[3] <= size["height"]):
        raise RecordsError(copy.ANCHOR_NOT_FOUND, status=422, field="anchor.box")
    return {"kind": "file_region", "file_id": file_id, "page": page, "box": list(box)}
