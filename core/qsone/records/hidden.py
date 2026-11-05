"""Hidden-text flags, made when a file is added: text a person does not see but an AI reads (white,
tiny, invisible or off the page; hidden sheets, rows and columns), and lines that look like orders
to an AI. A flag is a warning only: the text is never silently dropped or silently trusted, and
detection is never the defence (the Brief is marked untrusted anyway)."""

import ctypes
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

import pypdfium2.raw as pdfium_c

from qsone.records.arabic import display_text, normalise

FlagKind = Literal[
    "white_text",
    "tiny_text",
    "invisible_text",
    "off_page",
    "hidden_sheet",
    "hidden_rows",
    "hidden_columns",
    "hidden_element",
    "ai_instruction",
]

EXCERPT_CHARS = 160
TINY_POINTS = 1.5
MAX_LOCATOR_ITEMS = 200  # rows, columns or cells named in one locator; `count` has them all


@dataclass(frozen=True)
class Flag:
    kind: FlagKind
    locator: dict
    excerpt: str  # at most 160 characters
    count: int


class _Piece(Protocol):
    locator: dict
    text: str


def excerpt(text: str) -> str:
    return " ".join(display_text(text).split())[:EXCERPT_CHARS]


# Lines that look like orders to an AI ---------------------------------------------------------

_ENGLISH = re.compile(
    r"\bignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|above|prior)\s+instructions\b"
    r"|\bdisregard\b[^.\n]{0,40}?\binstructions\b"
    r"|\byou\s+are\s+(?:an?|the)\s+(?:ai|assistant|language\s+model)\b"
    r"|\bsystem\s+prompt\b"
    r"|\b(?:do\s+not|don'?t)\s+tell\s+the\s+(?:user|engineer)\b"
    r"|\bsend\b[^\n]{0,80}?\bto\b[^\n]{0,80}?@",
    re.IGNORECASE,
)


def _arabic(phrase: str, gap: int) -> str:
    """`phrase` normalised as the word index is, words apart by up to `gap` other words."""
    between = rf"(?: \S+){{0,{gap}}} "
    return r"(?:^| )" + between.join(map(re.escape, normalise(phrase).split())) + r"(?= |$)"


_ARABIC = re.compile(
    "|".join(
        [_arabic(p, 2) for p in ("تجاهل التعليمات", "انس التعليمات", "انسى التعليمات")]
        + [
            _arabic(p, 0)
            for p in (
                "أنت مساعد",
                "أنت نموذج",
                "أنت ذكاء اصطناعي",
                "لا تخبر المستخدم",
                "بصفتك مساعد",
                "بصفتك نموذج",
            )
        ]
    )
)


def ai_instruction_flags(pieces: Iterable[_Piece]) -> list[Flag]:
    """One flag per locator, counting the lines that look like orders to an AI; the excerpt is
    the first such line, from a little before the match."""
    found: dict[str, Flag] = {}
    for piece in pieces:
        for line in piece.text.split("\n"):
            m = _ENGLISH.search(line)
            if m is None and not _ARABIC.search(normalise(line)):
                continue
            start = 0 if m is None or m.start() < 40 else m.start() - 40
            key = json.dumps(piece.locator, sort_keys=True, ensure_ascii=False)
            old = found.get(key)
            found[key] = (
                Flag("ai_instruction", piece.locator, excerpt(line[start:]), 1)
                if old is None
                else Flag(old.kind, old.locator, old.excerpt, old.count + 1)
            )
    return list(found.values())


# PDF: pdfium's text API, character by character -----------------------------------------------

_INVISIBLE_MODES = {pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE, pdfium_c.FPDF_TEXTRENDERMODE_CLIP}
_STROKE_ONLY = {pdfium_c.FPDF_TEXTRENDERMODE_STROKE, pdfium_c.FPDF_TEXTRENDERMODE_STROKE_CLIP}
_LIGHT = 235  # a grey level this light or lighter counts as white


def pdf_page_flags(page, textpage, number: int) -> list[Flag]:
    """White, tiny, invisible and off-page text on one open pypdfium2 page.

    White text counts only where the page around it is white too, so a white heading on a dark
    table header is not flagged. Invisible text over a page image is a scan's own text layer
    (OCR), so it is not flagged either; the text is still read and still checked for orders."""
    tp = textpage.raw
    n = pdfium_c.FPDFText_CountChars(tp)
    left, bottom, right, top = page.get_cropbox()
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    box = [ctypes.c_double() for _ in range(4)]  # left, right, bottom, top
    matrix = pdfium_c.FS_MATRIX()
    objects: dict[int, tuple[int, float]] = {}  # text object -> render mode, size scale
    hits: dict[str, list[int]] = {k: [] for k in ("white", "tiny", "invisible", "off_page")}
    boxes: dict[int, tuple[float, float, float, float]] = {}
    chars = 0
    for i in range(n):
        if pdfium_c.FPDFText_IsGenerated(tp, i) == 1:
            continue
        space = chr(pdfium_c.FPDFText_GetUnicode(tp, i)).isspace()
        chars += not space
        obj = pdfium_c.FPDFText_GetTextObject(tp, i)
        key = ctypes.cast(obj, ctypes.c_void_p).value or 0
        if key not in objects:
            # Many PDFs set the font at 1 pt and scale it with the text matrix (1 Tf, 12 0 0 12 Tm)
            scale = 1.0
            if key and pdfium_c.FPDFPageObj_GetMatrix(obj, matrix):
                scale = math.hypot(matrix.c, matrix.d)
            objects[key] = (pdfium_c.FPDFTextObj_GetTextRenderMode(obj) if key else 0, scale)
        mode, scale = objects[key]
        pdfium_c.FPDFText_GetFillColor(tp, i, r, g, b, a)
        if mode in _INVISIBLE_MODES or (a.value == 0 and mode not in _STROKE_ONLY):
            hits["invisible"].append(i)
        elif mode not in _STROKE_ONLY and min(r.value, g.value, b.value) >= 250:
            hits["white"].append(i)
        if pdfium_c.FPDFText_GetFontSize(tp, i) * scale < TINY_POINTS:
            hits["tiny"].append(i)
        if not space and pdfium_c.FPDFText_GetCharBox(tp, i, *box):
            lo, hi, bo, to = (v.value for v in box)
            boxes[i] = (lo, hi, bo, to)
            if hi < left or lo > right or to < bottom or bo > top:
                hits["off_page"].append(i)
    if hits["white"]:
        hits["white"] = _on_white(page, hits["white"], boxes)
    if hits["invisible"] and _ocr_layer(page, hits["invisible"], tp, chars):
        hits["invisible"] = []
    kinds = {"white": "white_text", "tiny": "tiny_text", "invisible": "invisible_text"}
    flags = []
    for name, indexes in hits.items():
        text = _chars(tp, indexes)
        count = sum(not ch.isspace() for ch in text)
        if count:
            flags.append(Flag(kinds.get(name, name), {"page": number}, excerpt(text), count))
    return flags


def _chars(tp, indexes: list[int]) -> str:
    """The characters at `indexes`, with a space where the run breaks."""
    out, prev = [], None
    for i in indexes:
        if prev is not None and i != prev + 1:
            out.append(" ")
        out.append(chr(pdfium_c.FPDFText_GetUnicode(tp, i)))
        prev = i
    return "".join(out)


def _on_white(page, indexes: list[int], boxes: dict) -> list[int]:
    """The white characters whose surroundings are white on the rendered page: at least three of
    four points just outside the corners of the character's box. Spaces follow their run."""
    bitmap = page.render(scale=1, grayscale=True, fill_color=(255, 255, 255, 255))
    try:
        pixels, stride = bitmap.buffer, bitmap.stride
        width, height, conv = bitmap.width, bitmap.height, bitmap.get_posconv(page)

        def light(x: float, y: float) -> bool:
            px, py = conv.to_bitmap(x, y)
            if not (0 <= px < width and 0 <= py < height):
                return True
            return pixels[int(py) * stride + int(px)] >= _LIGHT

        kept, last = [], False
        for i in indexes:
            if i in boxes:
                lo, hi, bo, to = boxes[i]
                corners = [(lo - 1, bo - 1), (hi + 1, bo - 1), (lo - 1, to + 1), (hi + 1, to + 1)]
                last = sum(light(x, y) for x, y in corners) >= 3
            if last:
                kept.append(i)
        return kept
    finally:
        bitmap.close()


def _ocr_layer(page, invisible: list[int], tp, chars: int) -> bool:
    """Nine tenths of the page's text is invisible and the page has an image: a scan's text."""
    shown = sum(not chr(pdfium_c.FPDFText_GetUnicode(tp, i)).isspace() for i in invisible)
    if shown < 0.9 * chars:
        return False
    images = page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=2)
    return next(images, None) is not None


# Excel: what a person does not see in a sheet ----------------------------------------------------


def _letters(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def _number(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


Cell = tuple[int, int, str, bool, bool, str | None]  # row, column, text, row hidden, col hidden,
# and the cell's own hiding: "white_text", "tiny_text", "invisible_text" or None


class _Found:
    """What one check found in a sheet: the places (rows, columns or cells), and the first of
    their text, enough for the excerpt; a whole hidden sheet is never held twice."""

    def __init__(self) -> None:
        self.places: dict = {}  # place -> its texts so far
        self.size = 0
        self.cells = 0

    def add(self, place, text: str) -> None:
        texts = self.places.setdefault(place, [])
        self.cells += 1
        if self.size < 2 * EXCERPT_CHARS:
            texts.append(text)
            self.size += len(text)

    def text(self, between: str = " / ") -> str:
        """The texts in place order: " | " within a place, `between` places."""
        ordered = sorted(self.places.items(), key=lambda kv: kv[0])
        return between.join(" | ".join(t) for _, t in ordered if t)


def _sheet_flags(sheet: str, hidden: bool, cells: Iterable[Cell]) -> list[Flag]:
    whole, rows, cols = _Found(), _Found(), _Found()
    styled: dict[str, _Found] = {}
    for row, col, text, row_hidden, col_hidden, how in cells:
        if not text:
            continue
        if hidden:
            whole.add(0, text)
        if row_hidden:
            rows.add(row, text)
        if col_hidden:
            cols.add(col, text)
        if how:
            styled.setdefault(how, _Found()).add((row, col), text)
    flags = []
    if whole.cells:
        text = excerpt(whole.text())
        flags.append(Flag("hidden_sheet", {"sheet": sheet}, text, whole.cells))
    if rows.places:
        loc = {"sheet": sheet, "rows": sorted(rows.places)[:MAX_LOCATOR_ITEMS]}
        flags.append(Flag("hidden_rows", loc, excerpt(rows.text()), len(rows.places)))
    if cols.places:
        names = [_letters(c) for c in sorted(cols.places)][:MAX_LOCATOR_ITEMS]
        loc = {"sheet": sheet, "columns": names}
        flags.append(Flag("hidden_columns", loc, excerpt(cols.text()), len(cols.places)))
    for how, found in styled.items():
        refs = [f"{_letters(c)}{r}" for r, c in found.places][:MAX_LOCATOR_ITEMS]
        text = excerpt(found.text(" | "))
        flags.append(Flag(how, {"sheet": sheet, "cells": refs}, text, len(found.places)))
    return flags


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_WHITE_INDEXED = {"1", "9"}  # white in Excel's old 64-colour palette


def _white_colour(el: ET.Element | None) -> bool:
    if el is None:
        return False
    rgb = el.get("rgb", "")
    if rgb:
        return rgb[-6:].upper() == "FFFFFF"
    if el.get("theme") == "0":  # Background 1, white in every standard theme
        return float(el.get("tint", "0")) >= 0
    return el.get("indexed") in _WHITE_INDEXED


def _xlsx_styles(z: zipfile.ZipFile) -> list[str | None]:
    """Per cell format (`s`): how its text is hidden, if it is."""
    try:
        root = ET.fromstring(z.read("xl/styles.xml"))
    except KeyError:
        return []
    hidden_formats = {
        f.get("numFmtId")
        for f in root.iter(f"{_NS}numFmt")
        if f.get("formatCode", "").replace(" ", "") == ";;;"
    }
    fonts = []
    for font in root.iterfind(f"{_NS}fonts/{_NS}font"):
        size = font.find(f"{_NS}sz")
        tiny = size is not None and float(size.get("val", "11")) < TINY_POINTS
        fonts.append(
            "tiny_text"
            if tiny
            else "white_text"
            if _white_colour(font.find(f"{_NS}color"))
            else None
        )
    light_fills = []
    for fill in root.iterfind(f"{_NS}fills/{_NS}fill"):
        pattern = fill.find(f"{_NS}patternFill")
        kind = None if pattern is None else pattern.get("patternType", "none")
        light_fills.append(
            kind in (None, "none", "gray125") or _white_colour(pattern.find(f"{_NS}fgColor"))
        )
    out: list[str | None] = []
    for xf in root.iterfind(f"{_NS}cellXfs/{_NS}xf"):
        if xf.get("numFmtId") in hidden_formats:
            out.append("invisible_text")
            continue
        font_id, fill_id = int(xf.get("fontId", "0")), int(xf.get("fillId", "0"))
        how = fonts[font_id] if font_id < len(fonts) else None
        if how == "white_text" and fill_id < len(light_fills) and not light_fills[fill_id]:
            how = None  # white on a coloured fill is seen
        out.append(how)
    return out


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        f = z.open("xl/sharedStrings.xml")
    except KeyError:
        return []
    out = []
    with f:
        for _, el in ET.iterparse(f):
            if el.tag == f"{_NS}si":
                # rich text runs (r/t) and the plain t; phonetic runs (rPh) are not shown text
                skip = {t for ph in el.iter(f"{_NS}rPh") for t in ph.iter(f"{_NS}t")}
                out.append("".join(t.text or "" for t in el.iter(f"{_NS}t") if t not in skip))
                el.clear()
    return out


def _xlsx_sheets(z: zipfile.ZipFile) -> list[tuple[str, bool, str]]:
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target", "") for r in rels.iter(f"{_PKG}Relationship")}
    out = []
    for s in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{_NS}sheet"):
        target = targets.get(s.get(f"{_REL}id"), "")
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        out.append((s.get("name", ""), s.get("state", "visible") != "visible", path))
    return out


_REF = re.compile(r"([A-Z]+)(\d+)")


def _xlsx_cells(f, strings: list[str], styles: list[str | None]) -> Iterable[Cell]:
    hidden_cols: list[tuple[int, int]] = []
    for _, el in ET.iterparse(f):
        if el.tag == f"{_NS}col" and el.get("hidden") in ("1", "true"):
            hidden_cols.append((int(el.get("min", "0")), int(el.get("max", "0"))))
        elif el.tag == f"{_NS}row":
            row_hidden = el.get("hidden") in ("1", "true")
            for c in el.iter(f"{_NS}c"):
                m = _REF.match(c.get("r", ""))
                if m is None:
                    continue
                col, row = _number(m[1]), int(m[2])
                value = c.find(f"{_NS}v")
                kind = c.get("t")
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
                elif value is None or value.text is None:
                    continue
                elif kind == "s":
                    i = int(value.text)
                    text = strings[i] if i < len(strings) else ""
                else:
                    text = value.text
                s = int(c.get("s", "0"))
                yield (
                    row,
                    col,
                    display_text(text),
                    row_hidden,
                    any(lo <= col <= hi for lo, hi in hidden_cols),
                    styles[s] if s < len(styles) else None,
                )
            el.clear()


def xlsx_flags(data: bytes) -> list[Flag]:
    """zip + iterparse over each sheet, with styles.xml for white or tiny fonts and the ";;;"
    number format; the workbook is never loaded whole."""
    flags = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        strings, styles = _shared_strings(z), _xlsx_styles(z)
        for name, hidden, path in _xlsx_sheets(z):
            try:
                f = z.open(path)
            except KeyError:
                continue  # a chart sheet or a broken link: no cells
            with f:
                flags += _sheet_flags(name, hidden, _xlsx_cells(f, strings, styles))
    return flags


_XLS_WHITE = {1, 9}


def xls_flags(book, text: Callable[[object, int, int], str]) -> list[Flag]:
    """The same checks for an old .xls, from an xlrd book opened with `formatting_info=True`;
    `text(sheet, row, col)` gives a cell's text (rows and columns from 0)."""
    hows: dict[int, str | None] = {}
    for n, xf in enumerate(book.xf_list):
        font = book.font_list[xf.font_index]
        fmt = book.format_map.get(xf.format_key)
        filled = xf.background.fill_pattern != 0 and xf.background.pattern_colour_index not in (
            *_XLS_WHITE,
            64,  # the system window colour
        )
        if fmt is not None and fmt.format_str.replace(" ", "") == ";;;":
            hows[n] = "invisible_text"
        elif font.height < TINY_POINTS * 20:  # twips
            hows[n] = "tiny_text"
        elif font.colour_index in _XLS_WHITE and not filled:
            hows[n] = "white_text"
        else:
            hows[n] = None
    flags = []
    for sheet in book.sheets():
        rows, cols = sheet.rowinfo_map, sheet.colinfo_map

        def cells(sheet=sheet, rows=rows, cols=cols) -> Iterable[Cell]:
            for r in range(sheet.nrows):
                row_hidden = bool(getattr(rows.get(r), "hidden", 0))
                for c in range(sheet.row_len(r)):
                    yield (
                        r + 1,
                        c + 1,
                        text(sheet, r, c),
                        row_hidden,
                        bool(getattr(cols.get(c), "hidden", 0)),
                        hows.get(sheet.cell_xf_index(r, c)),
                    )

        flags += _sheet_flags(sheet.name, sheet.visibility != 0, cells())
    return flags
