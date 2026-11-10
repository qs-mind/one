"""Word (.docx) through python-docx: a piece per paragraph with the nearest heading above it, and a
piece per table row. Runs marked hidden (`w:vanish`) are left out and flagged; white and tiny runs
are kept and flagged. Text in content controls and text boxes is read; headers, footers, notes and
comments are not."""

import io

import docx
from docx.enum.dml import MSO_COLOR_TYPE, MSO_THEME_COLOR
from docx.oxml.ns import qn
from docx.shared import RGBColor
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from qsone.records.arabic import display_text
from qsone.records.extract import Piece
from qsone.records.hidden import TINY_POINTS, Flag, excerpt

_P, _TBL, _TR, _TC, _R = qn("w:p"), qn("w:tbl"), qn("w:tr"), qn("w:tc"), qn("w:r")
_CONTAINERS = {qn("w:sdt"), qn("w:sdtContent"), qn("w:customXml"), qn("w:smartTag")}
_RUN_TEXT = {qn("w:t"): None, qn("w:tab"): " ", qn("w:br"): "\n", qn("w:cr"): "\n"}
_RUN_TEXT[qn("w:noBreakHyphen")] = "-"
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_WHITE_THEMES = {MSO_THEME_COLOR.BACKGROUND_1, MSO_THEME_COLOR.LIGHT_1}
_HIDING = ("invisible_text", "white_text", "tiny_text")


def read(data: bytes) -> tuple[list[Piece], list[Flag], list[Piece]]:
    """The pieces, the flags, and the hidden (vanish) text as pieces, so the check for orders to
    an AI reads it too."""
    document = docx.Document(io.BytesIO(data))
    pieces: list[Piece] = []
    flags: list[Flag] = []
    hidden: list[Piece] = []
    paragraph = table = 0
    heading = None
    for block in _blocks(document.element.body, (_P, _TBL)):
        if block.tag == _P:
            paragraph += 1
            para = Paragraph(block, document)
            text, hid = _paragraph(para, shaded=False)
            if text and _is_heading(para):
                heading = text
            if text:
                where = {"paragraph": paragraph} | ({"heading": heading} if heading else {})
                pieces.append(Piece(where, text))
            _flag({"paragraph": paragraph}, hid, flags, hidden)
            continue
        table += 1
        for row, tr in enumerate(_blocks(block, (_TR,)), 1):
            cells, hid = [], {k: "" for k in _HIDING}
            for tc in _blocks(tr, (_TC,)):
                if _continues_merge(tc):
                    cells.append("")  # the cell above, merged down: read once, its place kept
                    continue
                shaded = _shaded(tc.tcPr)
                parts = []
                for p in tc.iter(_P):
                    text, more = _paragraph(Paragraph(p, document), shaded=shaded)
                    parts.append(text)
                    hid = {k: hid[k] + more[k] for k in _HIDING}
                cells.append(display_text("\n".join(parts)))  # an empty cell keeps its column
            while cells and not cells[-1]:
                cells.pop()
            if cells:
                pieces.append(Piece({"table": table, "row": row}, " | ".join(cells)))
            _flag({"table": table, "row": row}, hid, flags, hidden)
    return pieces, flags, hidden


def _blocks(parent, tags: tuple[str, ...]):
    """Children of `parent` with one of `tags`, looking inside content controls and the like."""
    for child in parent.iterchildren():
        if child.tag in tags:
            yield child
        elif child.tag in _CONTAINERS:
            yield from _blocks(child, tags)


def _flag(where: dict, hid: dict[str, str], flags: list[Flag], hidden: list[Piece]) -> None:
    for kind in _HIDING:
        count = sum(not ch.isspace() for ch in hid[kind])
        if count:
            flags.append(Flag(kind, where, excerpt(hid[kind]), count))
    if hid["invisible_text"].strip():
        hidden.append(Piece(where, display_text(hid["invisible_text"])))


def _paragraph(para: Paragraph, *, shaded: bool) -> tuple[str, dict[str, str]]:
    """The paragraph's shown text, and its hidden text by kind of hiding."""
    style = para.style
    shaded = shaded or _shaded(para._p.pPr)
    shown, hid = [], {k: [] for k in _HIDING}
    for r in para._p.iter(_R):
        text = "".join(_RUN_TEXT[c.tag] or c.text or "" for c in r if c.tag in _RUN_TEXT)
        if not text:
            continue
        run = Run(r, para)
        if _effective(run, style, lambda f: f.hidden):
            hid["invisible_text"].append(text)
            continue
        shown.append(text)
        size = _effective(run, style, lambda f: f.size)
        if size is not None and size.pt < TINY_POINTS:
            hid["tiny_text"].append(text)
        elif not shaded and not _shaded(r.rPr) and _effective(run, style, _white):
            hid["white_text"].append(text)
    return display_text("".join(shown)), {k: "".join(v) for k, v in hid.items()}


def _effective(run: Run, paragraph_style, get):
    """A run property as Word applies it: the run, its character style, the paragraph style,
    each with the styles they are based on."""
    value = get(run.font)
    if value is not None:
        return value
    for style in (run.style, paragraph_style):
        while style is not None:
            value = get(style.font)
            if value is not None:
                return value
            style = style.base_style
    return None


def _white(font) -> bool | None:
    color = font.color
    if color.type is None:
        return None
    if color.type == MSO_COLOR_TYPE.THEME:
        return color.theme_color in _WHITE_THEMES
    return color.type == MSO_COLOR_TYPE.RGB and color.rgb == _WHITE


def _shaded(pr) -> bool:
    """A fill or highlight behind the text (run, paragraph or cell), so white text shows."""
    if pr is None:
        return False
    shd = pr.find(qn("w:shd"))
    fill = "" if shd is None else (shd.get(qn("w:fill")) or "").lower()
    highlight = pr.find(qn("w:highlight"))
    mark = "" if highlight is None else (highlight.get(qn("w:val")) or "").lower()
    return fill not in ("", "auto", "ffffff") or mark not in ("", "none", "white")


def _continues_merge(tc) -> bool:
    pr = tc.tcPr
    merge = None if pr is None else pr.find(qn("w:vMerge"))
    return merge is not None and merge.get(qn("w:val")) != "restart"


def _is_heading(para: Paragraph) -> bool:
    style = para.style
    name = (style.name or "").lower() if style is not None else ""
    if name.startswith("heading") or name == "title":
        return True
    prs = [para._p.pPr]
    while style is not None:
        prs.append(style.element.pPr)
        style = style.base_style
    for pr in prs:
        level = None if pr is None else pr.find(qn("w:outlineLvl"))
        if level is not None:
            return int(level.get(qn("w:val"), "9")) < 9
    return False
