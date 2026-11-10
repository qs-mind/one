"""In-memory PDF tables as BOQ sheets; boxes are PDF points from the top-left.

Geometry supplies reading order, so Arabic is extracted right-to-left as whole words,
without reversing strings (which would corrupt digits and mixed-language descriptions).
"""

import io
import re
import unicodedata
from itertools import groupby

import pdfplumber

from qsone import copy
from qsone.records import regions
from qsone.records.arabic import display_text
from qsone.records.project import RecordsError


def _arabic(char):
    return any(unicodedata.bidirectional(c) in ("AL", "R") for c in char["text"])


def cell_text(chars):
    # Some shaped fonts map a zero-advance component (dots) to its base letter too.
    # Ignore zero-advance letter components; retain actual combining accents.
    chars = [
        c
        for c in chars
        if c["width"] or not any(unicodedata.category(ch).startswith("L") for ch in c["text"])
    ]
    if not any(_arabic(c) for c in chars):
        return display_text(pdfplumber.utils.extract_text(chars))
    # Form spatial words using every character; direction never divides a word.
    words = pdfplumber.utils.extract_words(chars, return_chars=True)
    for word in words:
        arabic = any(_arabic(c) for c in word["chars"])
        word["direction"] = "rtl" if arabic else "ltr"
        if arabic:
            text = "".join(c["text"] for c in sorted(word["chars"], key=lambda c: -c["x0"]))
            # A numeric span still reads left-to-right within a whole Arabic word.
            word["text"] = (
                re.sub(r"[0-9٠-٩۰-۹]+(?:[.,٫٬][0-9٠-٩۰-۹]+)*", lambda m: m[0][::-1], text)
                if all(len(c["text"]) == 1 for c in word["chars"])
                else text  # OCR records already contain intact logical words.
            )
    lines = []
    for word in sorted(words, key=lambda w: w["top"]):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 4:
            lines.append([])
        lines[-1].append(word)
    ordered = []
    for line in lines:
        parts = []
        for direction, run in groupby(
            sorted(line, key=lambda w: -w["x0"]), key=lambda w: w["direction"]
        ):
            run = list(run)
            if direction == "ltr":
                run.reverse()
            parts.extend(w["text"] for w in run)
        ordered.append(" ".join(parts))
    return display_text("\n".join(ordered))


def sheets(data, *, ocr_words=None):
    from qsone.records.boq import Cell, Sheet, guess

    result, missing = [], []
    previous = None
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            read_by = None  # a page read from its picture on this computer: numbers unchecked
            if not page.chars and ocr_words:
                found = ocr_words.get(page.page_number, [])
                page.objects["char"] = _ocr_chars(page, found)
                read_by = next((w["read_by"] for w in found if w.get("read_by")), None)
            if not page.chars:
                missing.append(page.page_number)
                previous = None
                continue
            crop_x, crop_y = page.cropbox[:2]
            numbers = regions.pdf_numbers(data, page.page_number)["numbers"]
            tables = page.find_tables()
            borderless = not tables
            if borderless:
                tables = page.find_tables(
                    {"vertical_strategy": "text", "horizontal_strategy": "text"}
                )
            for index, table in enumerate(tables):
                candidate = Sheet(f"PDF {page.page_number}.{index + 1}", False)
                lefts = sorted({box[0] for box in table.cells})
                tops = sorted({box[1] for box in table.cells})
                for r, row in enumerate(table.rows, 1):
                    for c, box in enumerate(row.cells, 1):
                        if box is None:
                            continue
                        x0, top, x1, bottom = box
                        right = sum(x < x1 - 0.1 for x in lefts)
                        last = sum(y < bottom - 0.1 for y in tops)
                        if right > c or last > r:
                            candidate.merges.append((r, c, last, right))
                        chars = [
                            ch
                            for ch in page.chars
                            if x0 <= (ch["x0"] + ch["x1"]) / 2 < x1
                            and top <= (ch["top"] + ch["bottom"]) / 2 < bottom
                        ]
                        text = cell_text(chars)
                        printed = [ch for ch in chars if ch["width"] and ch["text"].strip()]
                        if printed:
                            box = (
                                min(ch["x0"] for ch in printed),
                                min(ch["top"] for ch in printed),
                                max(ch["x1"] for ch in printed),
                                max(ch["bottom"] for ch in printed),
                            )
                        box = [box[0] - crop_x, box[1] - crop_y, box[2] - crop_x, box[3] - crop_y]
                        # Reuse the displayed glyph bounds used by number highlighting.
                        matches = (
                            [
                                n["box"]
                                for n in numbers
                                if regions._number(n["text"]) == regions._number(text)
                                and box[0] - 1 <= (n["box"][0] + n["box"][2]) / 2 <= box[2] + 1
                                and box[1] - 1 <= (n["box"][1] + n["box"][3]) / 2 <= box[3] + 1
                            ]
                            if regions._number(text) is not None
                            else []
                        )
                        if len(matches) == 1:
                            box = matches[0]
                        where = {"page": page.page_number, "box": list(box)}
                        if read_by:
                            where["read_by"] = read_by
                        candidate.cells.setdefault(r, {})[c] = Cell(text, None, where)
                header, columns = guess(candidate, candidate.last_row)
                if borderless and not columns:
                    continue  # prose aligned by chance is not a BOQ
                bounds = [*lefts, max(box[2] for box in table.cells)]
                # Only adjacent pages, last/first tables, matching column geometry and headings.
                continuation = previous and index == 0 and previous[0] == page.page_number - 1
                continuation = continuation and bool(previous[3])
                continuation = (
                    continuation
                    and len(previous[2]) == len(bounds)
                    and all(abs(a - b) <= 1 for a, b in zip(previous[2], bounds, strict=True))
                )
                continuation = continuation and (not columns or columns == previous[3])
                if continuation:
                    sheet = previous[1]
                    start = header + 1 if header else 1
                    offset = sheet.last_row
                    sheet.merges.extend(
                        (top + offset - start + 1, left, bottom + offset - start + 1, right)
                        for top, left, bottom, right in candidate.merges
                        if top >= start
                    )
                    for r in range(start, candidate.last_row + 1):
                        sheet.cells[offset + r - start + 1] = candidate.cells.get(r, {})
                else:
                    sheet = candidate
                    result.append(sheet)
                previous = (
                    page.page_number,
                    sheet,
                    bounds,
                    columns or (previous[3] if continuation else {}),
                )
            if not tables:
                previous = None
    for sheet in result:
        sheet.needs_reading = missing
    return result, missing


def read(data, name, *, ocr_words=None):
    found, missing = sheets(data, ocr_words=ocr_words)
    if not found:
        raise RecordsError(
            copy.BOQ_SCAN_NEEDS_READING if missing else copy.BOQ_PDF_NO_TABLES,
            status=422,
            field="file_id",
        )
    return [(s.name, False) for s in found], next((s for s in found if s.name == name), None)


def _ocr_chars(page, words):
    """Keep an OCR word intact while adapting CropBox points to pdfplumber's frame."""
    left, top, _, _ = page.cropbox
    chars = []
    for word in words:
        x0, y0, x1, y1 = word["box"]
        chars.append(
            {
                "text": word["text"],
                "x0": x0 + left,
                "x1": x1 + left,
                "top": y0 + top,
                "bottom": y1 + top,
                "doctop": y0 + top + page.initial_doctop,
                "width": x1 - x0,
                "height": y1 - y0,
                "upright": True,
            }
        )
    return chars


def read_stored(rec, file_id, name):
    """Read a PDF table using the already-kept local OCR word boxes when needed."""
    import json

    from qsone.records.files import read_original

    words = {}
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT locator, text FROM chunks WHERE file_id = ? ORDER BY seq", (file_id,)
        ).fetchall()
    for locator, text in rows:
        locator = json.loads(locator)
        if locator.get("read_by") and "box" in locator and text.strip():
            words.setdefault(locator["page"], []).append(
                {"text": text, "box": locator["box"], "read_by": locator["read_by"]}
            )
    return read(read_original(rec, file_id), name, ocr_words=words)
