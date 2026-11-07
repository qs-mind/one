"""Revision comparison from kept page text and in-memory PDFium page-box renders.

Unique sheet identifiers, then unique first-line titles, then residual order. Pairing is
reported as evidence, not certainty. Pixels are compared at LARGE (1400 px); no registration,
OCR, AI inference, decrypted temporary files, or persistent image cache.
"""

import io
import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher

import numpy as np
import pdfplumber
import pypdfium2
import pypdfium2.raw as pdfium_c

from qsone import copy
from qsone.records import files, render
from qsone.records.pdfium_guard import PDFIUM
from qsone.records.project import Records, RecordsError

SMALL, LARGE = 600, 1400
_SHEET = re.compile(r"(?<!\w)[A-Z]{1,5}\s*[-–]\s*\d{1,5}(?:[.-]\d+)?(?!\w)", re.I)
_ARABIC = re.compile(r"لوحة\s*(?:رقم)?\s*[:：#-]?\s*([\w.-]+)")


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(str(unicodedata.digit(c)) if c.isdecimal() else c for c in text)


def _sheet_candidates(text: str) -> list[str]:
    candidates = []
    for match in _SHEET.finditer(_normalized(text)):
        value = re.sub(r"\s+", "", match[0]).upper().replace("–", "-")
        prefix, number = value.split("-", 1)
        # Common standards and concrete strength grades are not drawing identifiers.
        if prefix in {"BS", "EN", "ISO", "ASTM", "DIN", "ACI", "ECP"}:
            continue
        if prefix == "C" and number.isdigit() and int(number) <= 100:
            continue
        candidates.append((match.start(), value))
    candidates.extend((m.start(), m[1].casefold()) for m in _ARABIC.finditer(_normalized(text)))
    return [value for _, value in sorted(candidates)]


def identity(text: str, title_block: str | None = None) -> tuple[str, str]:
    normalized = _normalized(text)
    matches = _sheet_candidates(title_block or "") or _sheet_candidates(normalized)
    sheet = matches[-1] if matches else ""
    lines = [" ".join(line.split()).casefold() for line in normalized.splitlines() if line.strip()]
    title = next((line for line in lines if not _sheet_candidates(line)), "")
    return sheet, title


def pair_pages(
    old: list[str],
    new: list[str],
    *,
    title_blocks: tuple[list[str | None], list[str | None]] | None = None,
) -> list[tuple[int, int, str]]:
    blocks = title_blocks or ([None] * len(old), [None] * len(new))
    ids = [
        [identity(t, block) for t, block in zip(pages, titles, strict=True)]
        for pages, titles in zip((old, new), blocks, strict=True)
    ]
    remaining = [set(range(len(old))), set(range(len(new)))]
    pairs = []
    for field, method in ((0, "sheet"), (1, "title")):
        counts = [Counter(ids[s][i][field] for i in remaining[s]) for s in (0, 1)]
        lookup = {ids[1][i][field]: i for i in remaining[1] if counts[1][ids[1][i][field]] == 1}
        for i in sorted(remaining[0]):
            key = ids[0][i][field]
            if key and counts[0][key] == 1 and key in lookup:
                j = lookup[key]
                # A title must not override two different explicit sheet numbers.
                if field == 1 and ids[0][i][0] and ids[1][j][0] and ids[0][i][0] != ids[1][j][0]:
                    continue
                pairs.append((i + 1, j + 1, method))
                remaining[0].remove(i)
                remaining[1].remove(j)
    for i, j in zip(sorted(remaining[0]), sorted(remaining[1]), strict=False):
        pairs.append((i + 1, j + 1, "order"))
    return sorted(pairs)


def overlay_pixels(old: np.ndarray, new: np.ndarray) -> tuple[np.ndarray, int]:
    """Same box/scale, exact RGBA difference; unmodified pixels retain the old image."""
    changed = np.any(old != new, axis=2)
    before = old[:, :, :3].astype(np.int16).sum(axis=2)
    after = new[:, :, :3].astype(np.int16).sum(axis=2)
    removed = changed & (after > before)
    added = changed & ~removed
    out = old.copy()
    out[removed] = [255, 0, 0, 255]
    out[added] = [0, 160, 0, 255]
    return out, int(np.count_nonzero(changed))


def _images(old: bytes, new: bytes, before: int, after: int, width: int):
    with PDFIUM:
        docs = []
        pages = []
        try:
            for data, number in ((old, before), (new, after)):
                doc = pypdfium2.PdfDocument(data)
                docs.append(doc)
                if not 1 <= number <= len(doc):
                    raise IndexError(number)
                pages.append(doc[number - 1])
            box_width = max(p.get_width() for p in pages)
            box_height = max(p.get_height() for p in pages)
            scale = width / box_width
            height = int(np.ceil(box_height * scale))
            if height > width * 8:
                raise ValueError("page box too tall")
            images = []
            drawing = False
            for page in pages:
                drawing |= any(
                    obj.type in (pdfium_c.FPDF_PAGEOBJ_PATH, pdfium_c.FPDF_PAGEOBJ_IMAGE)
                    for obj in page.get_objects()
                )
                bitmap = page.render(
                    scale=scale,
                    rev_byteorder=True,
                    force_bitmap_format=pdfium_c.FPDFBitmap_BGRA,
                    fill_color=(255, 255, 255, 255),
                )
                try:
                    pixels = np.frombuffer(bitmap.buffer, dtype=np.uint8).reshape(
                        bitmap.height, bitmap.stride
                    )
                    pixels = pixels[:, : bitmap.width * 4].reshape(bitmap.height, bitmap.width, 4)
                    canvas = np.full((height, width, 4), 255, dtype=np.uint8)
                    h, w = min(height, bitmap.height), min(width, bitmap.width)
                    canvas[:h, :w] = pixels[:h, :w]
                    images.append(canvas)
                finally:
                    bitmap.close()
            return *overlay_pixels(*images), drawing
        finally:
            for page in pages:
                page.close()
            for doc in docs:
                doc.close()


def _title_blocks(data: bytes, chunks: list[tuple[str, str]], count: int) -> list[str | None]:
    """One slot per displayed page; no title-block words means no identity evidence.

    PDFium owns displayed page numbers. A page with no pdfplumber title-block text
    must retain its slot rather than shifting later pages' identities forward.
    """
    ocr_words: dict[int, list[dict]] = {}
    for locator, text in chunks:
        loc = json.loads(locator)
        if loc.get("read_by") and loc.get("page"):
            words = loc.get("words") or (
                [{"text": text, "box": loc["box"]}] if "box" in loc else []
            )
            ocr_words.setdefault(loc["page"], []).extend(words)
    blocks: list[str | None] = [None] * count
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            x0, y0, x1, y1 = page.cropbox or page.bbox
            if page.chars:
                words = [
                    {
                        "text": word["text"],
                        "box": [
                            word["x0"] - x0,
                            word["top"] - y0,
                            word["x1"] - x0,
                            word["bottom"] - y0,
                        ],
                    }
                    for word in page.extract_words()
                ]
            else:
                words = ocr_words.get(page.page_number, [])
            selected = [
                w
                for w in words
                if (x1 - x0) / 2 <= (w["box"][0] + w["box"][2]) / 2 <= x1 - x0
                and (y1 - y0) / 2 <= (w["box"][1] + w["box"][3]) / 2 <= y1 - y0
            ]
            selected.sort(key=lambda w: (w["box"][1], w["box"][0]))
            blocks[page.page_number - 1] = " ".join(w["text"] for w in selected) or None
    return blocks


def _file(rec: Records, file_id: str):
    with rec.read() as conn:
        row = conn.execute(
            "SELECT name, kind, added_at FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if row is None:
            raise RecordsError(copy.FILE_NOT_FOUND, status=404, field="file")
        if row[1] != "pdf":
            raise RecordsError(copy.FILE_HAS_NO_PAGES, status=409, field="file")
        chunks = conn.execute(
            "SELECT locator, text FROM chunks WHERE file_id = ? ORDER BY seq", (file_id,)
        ).fetchall()
    data = files.read_original(rec, file_id)
    try:
        count = render.page_count(data)
        title_blocks = _title_blocks(data, chunks, count)
    except Exception:
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None
    texts = [""] * count
    for locator, text in chunks:
        page = json.loads(locator).get("page")
        if isinstance(page, int) and 1 <= page <= count:
            texts[page - 1] += text + "\n"
    return data, texts, {"file_id": file_id, "name": row[0], "date": row[2]}, title_blocks


def compare_files(rec: Records, old_file_id: str, new_file_id: str) -> dict:
    old, new = _file(rec, old_file_id), _file(rec, new_file_id)
    pairs, changed = [], []
    for before, after, method in pair_pages(old[1], new[1], title_blocks=(old[3], new[3])):
        removed, added = [], []
        a, b = old[1][before - 1].split(), new[1][after - 1].split()
        for tag, i, j, k, end in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag in ("replace", "delete"):
                removed.extend(a[i:j])
            if tag in ("replace", "insert"):
                added.extend(b[k:end])
        try:
            _, pixels, drawing = _images(old[0], new[0], before, after, LARGE)
        except Exception:
            raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None
        pair = {"old": old[2] | {"page": before}, "new": new[2] | {"page": after}, "method": method}
        if method == "sheet" and any(
            len(set(_sheet_candidates(item[1][page - 1]))) > 1
            for item, page in ((old, before), (new, after))
        ):
            pair["pairing_note"] = copy.COMPARE_PAIRING_REVIEW
        pairs.append(pair)
        if added or removed or pixels:
            line = (
                copy.COMPARE_TEXT_PIXELS
                if (added or removed) and pixels
                else (copy.COMPARE_TEXT if added or removed else copy.COMPARE_PIXELS)
            )
            changed.append(
                pair
                | {
                    "added": added,
                    "removed": removed,
                    "pixels_changed": pixels,
                    "overlay": drawing or bool(identity(old[1][before - 1])[0]),
                    "summary": line,
                }
            )
    return {
        "old": old[2],
        "new": new[2],
        "compared_at": datetime.now(UTC).isoformat(),
        "pairs": pairs,
        "changed": changed,
        "unchanged": len(pairs) - len(changed),
        "unpaired_old": [
            old[2] | {"page": n}
            for n in range(1, len(old[1]) + 1)
            if n not in {p["old"]["page"] for p in pairs}
        ],
        "unpaired_new": [
            new[2] | {"page": n}
            for n in range(1, len(new[1]) + 1)
            if n not in {p["new"]["page"] for p in pairs}
        ],
    }


def overlay_png(
    rec: Records, old_file_id: str, new_file_id: str, old_page: int, new_page: int, width: int
) -> bytes:
    if width not in (SMALL, LARGE):
        raise RecordsError(copy.COMPARE_WIDTH, status=422, field="width")
    old, new = _file(rec, old_file_id), _file(rec, new_file_id)
    try:
        pixels, _, _ = _images(old[0], new[0], old_page, new_page, width)
        h, w, _ = pixels.shape
        return render._png(w, h, pixels.tobytes(), w * 4)
    except IndexError:
        raise RecordsError(copy.PAGE_NOT_FOUND, status=404, field="page") from None
    except Exception:
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None
