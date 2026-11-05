"""A Document to Word (python-docx), in memory: headings, paragraphs, lists and tables from the
blocks; `num` and `cell` references as their formatted values, each with a numbered note in a
«المصادر» list at the end. An Arabic Deliverable is right to left throughout: python-docx has no
API for it, so `w:bidi`, `w:rtl`, `w:cs`, `w:bidiVisual` and the complex-script font and
language are set in the XML."""

import io

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from qsone import copy
from qsone.deliverables.store import ref_key
from qsone.export import DASH, FONT, check_draft, format_decimal, places, say, source_line, state

INK, COPPER = RGBColor(0x0E, 0x0F, 0x12), RGBColor(0xA6, 0x49, 0x1B)
_STYLES = {"h1": "Heading 1", "h2": "Heading 2", "h3": "Heading 3", "blockquote": "Quote"}
_INLINE = {"num", "cell"}
# What follows w:bidi in w:pPr, and w:lang in w:rPr (the schema's order).
_AFTER_BIDI = (
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)
_AFTER_LANG = ("w:eastAsianLayout", "w:specVanish", "w:oMath")


class _Writer:
    def __init__(self, view: dict):
        self.view = view
        self.language = view["language"]
        self.notes: list[dict] = []  # each reference shown, in order; its number is its place

    def runs(self, paragraph, children: list[dict]) -> None:
        for child in children:
            if child.get("type") in _INLINE:
                self.ref(paragraph, child)
            elif "text" in child and "type" not in child:
                run = paragraph.add_run(child["text"])
                run.bold = child.get("bold") or None
                run.italic = child.get("italic") or None
            else:  # a block inside an inline run (not made by Plate): its text, in place
                self.runs(paragraph, child.get("children", []))

    def ref(self, paragraph, node: dict) -> None:
        cell = self.view["refs"].get(ref_key(node))
        if cell is None:
            paragraph.add_run(DASH)
            return
        paragraph.add_run(format_decimal(cell["value"], places(cell), self.language))
        self.notes.append(cell)
        mark = paragraph.add_run(f"[{len(self.notes)}]")
        mark.font.superscript = True

    def block(self, container, node: dict) -> None:
        kind = node.get("type")
        children = node.get("children", [])
        if kind in ("ul", "ol"):
            for item in children:
                self.item(container, item, kind, 1)
        elif kind == "table":
            self.table(container, children)
        elif all(c.get("type") in _INLINE or "type" not in c for c in children):
            self.runs(container.add_paragraph(style=_STYLES.get(kind)), children)
        else:
            for child in children:
                self.block(container, child)

    def item(self, container, node: dict, kind: str, depth: int) -> None:
        """A list item: one paragraph of its text, then its nested lists one level in."""
        style = ("List Bullet" if kind == "ul" else "List Number") + (
            f" {min(depth, 3)}" if depth > 1 else ""
        )
        children = node.get("children", [])
        nested = [c for c in children if c.get("type") in ("ul", "ol")]
        paragraph = container.add_paragraph(style=style)
        self.runs(paragraph, [c for c in children if c not in nested])
        for sub_list in nested:
            for sub in sub_list.get("children", []):
                self.item(container, sub, sub_list["type"], depth + 1)

    def table(self, container, rows: list[dict]) -> None:
        width = max((len(r.get("children", [])) for r in rows), default=0)
        if not rows or not width:
            return
        table = container.add_table(rows=len(rows), cols=width)
        table.style = "Table Grid"
        for r, row in enumerate(rows):
            for c, td in enumerate(row.get("children", [])):
                cell = table.cell(r, c)
                first = cell.paragraphs[0]
                children = td.get("children", [])
                if all(x.get("type") in _INLINE or "type" not in x for x in children):
                    self.runs(first, children)
                    continue
                for n, child in enumerate(children):
                    if n == 0 and child.get("type") == "p":
                        self.runs(first, child.get("children", []))
                    else:
                        self.block(cell, child)

    def sources(self, document) -> None:
        """The «المصادر» table: one row per reference, numbered as its mark. A table, so each
        date and Latin phrase sits alone in its cell and reads in order in Arabic."""
        if not self.notes:
            return
        document.add_paragraph(say("sources", self.language), style="Heading 2")
        heads = [
            "",
            "src_value",
            "src_unit",
            "src_title",
            "src_file",
            "src_place",
            "src_dated",
            "src_link",
        ]
        table = document.add_table(rows=1, cols=len(heads))
        table.style = "Table Grid"
        for cell, name in zip(table.rows[0].cells, heads, strict=True):
            cell.paragraphs[0].add_run(say(name, self.language) if name else "").bold = True
        for n, number in enumerate(self.notes, 1):
            line = source_line(self.view, number)
            value = format_decimal(number["value"], places(number), self.language)
            values = [
                f"[{n}]",
                value,
                line["unit"],
                line["title"],
                line["file"],
                line["place"],
                line["dated"],
                line["link"],
            ]
            for cell, text in zip(table.add_row().cells, values, strict=True):
                cell.paragraphs[0].add_run(text)


def to_docx(view: dict) -> bytes:
    """A Document view as a .docx file."""
    if view.get("kind") != "document":
        raise ValueError("only a Document exports to Word")
    check_draft(view)
    language = view["language"]
    document = docx.Document()
    document.core_properties.title = view["title"]
    for name in ("Normal", *_STYLES.values()):
        style = document.styles[name]
        style.font.name = FONT
        if name != "Normal":
            style.font.color.rgb = INK
    header = document.sections[0].header.paragraphs[0]
    sample = [copy.SAMPLE_DATA[language]] if view.get("sample") else []
    mark = header.add_run(" · ".join([state(view), *sample]))
    mark.font.color.rgb, mark.font.size, mark.bold = COPPER, Pt(9), True

    writer = _Writer(view)
    for block in view["blocks"]:
        writer.block(document, block["node"])
    writer.sources(document)

    for part in (document.element.body, document.sections[0].header._element):
        _fonts_and_direction(part, rtl=language == "ar")
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _fonts_and_direction(root, *, rtl: bool) -> None:
    """Every run in Arial (Latin and complex script); for Arabic, every paragraph `w:bidi`,
    every run `w:rtl` and `w:cs` with the ar-EG language, every table `w:bidiVisual`."""
    for r in root.iter(qn("w:r")):
        rPr = r.get_or_add_rPr()
        fonts = rPr.get_or_add_rFonts()
        for side in ("w:ascii", "w:hAnsi", "w:cs"):
            fonts.set(qn(side), FONT)
        if not rtl:
            continue
        if rPr.b is not None:
            rPr.get_or_add_bCs()
        if rPr.i is not None:
            rPr.get_or_add_iCs()
        rPr.get_or_add_rtl()
        rPr.get_or_add_cs()
        if rPr.find(qn("w:lang")) is None:
            lang = OxmlElement("w:lang")
            lang.set(qn("w:bidi"), "ar-EG")
            rPr.insert_element_before(lang, *_AFTER_LANG)
    if not rtl:
        return
    for p in root.iter(qn("w:p")):
        pPr = p.get_or_add_pPr()
        if pPr.find(qn("w:bidi")) is None:
            pPr.insert_element_before(OxmlElement("w:bidi"), *_AFTER_BIDI)
    for tbl in root.iter(qn("w:tbl")):
        tbl.tblPr.get_or_add_bidiVisual()
