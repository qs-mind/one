"""Paragraphs and table rows of a CP range of a Word 97-2003 document (`blocks`). Nothing is
dropped: cells whose row mark is missing come out as paragraphs. A row keeps every cell in its
column, an empty one as an empty place; a cell a merge covers is empty, its text flagged."""

from qsone.records.extract import Piece
from qsone.records.readers.doc_document import MARKS
from qsone.records.readers.doc_props import Para, is_heading

_PLAIN = Para()


def blocks(doc, start: int, end: int, part: str, pieces: list[Piece]) -> None:
    text = doc.text
    where = {} if part == "main" else {"part": part}
    cell: list[str] = []  # paragraphs of the open outer cell
    cells: list[tuple[str, int, int]] = []  # text, cp start, cp end
    in_table = False
    n_par = n_table = n_row = 0
    heading = None
    pos = par_start = cell_start = start
    buf: list[str] = []

    def flush(to: int, p: Para | None) -> str:
        buf.append(text[pos:to])
        s = doc.shown("".join(buf))
        buf.clear()
        label = doc.number(p) if p is not None else ""  # counted even when the text is empty
        return label + s if s else s

    def paragraph(s: str, a: int, b: int, p: Para) -> None:
        nonlocal n_par, heading
        n_par += 1
        if part == "main":
            if s and is_heading(doc.styles, p):
                heading = s
            loc = {"paragraph": n_par} | ({"heading": heading} if heading else {})
        else:
            loc = where | {"paragraph": n_par}
        doc._spans.append((a, b, {k: v for k, v in loc.items() if k != "heading"}, p.shaded))
        if s:
            pieces.append(Piece(loc, s))

    def loose_cells() -> None:
        """Cells with no row mark after them (a damaged or foreign file): kept as paragraphs."""
        nonlocal cells, cell
        if cell:
            cells.append((doc.shown("\n".join(cell)), cell_start, par_start))
        if cells:
            doc.notes.add("tables")
        for s, a, b in cells:
            paragraph(s, a, b, _PLAIN)
        cells, cell = [], []

    def row(s: str, p: Para) -> None:
        nonlocal n_row, cells, cell
        n_row += 1
        loc = where | {"table": n_table, "row": n_row}
        shown = []
        for i, (c, a, b) in enumerate(cells):
            doc._spans.append((a, b, loc, i in p.shaded_cells))
            if i in p.skip:  # under a merged cell: Word does not show it
                shown.append("")
                if c:
                    doc._merged.append((loc, c))
            else:
                shown.append(c)
        if s:  # text in the row mark's own paragraph: not expected, never dropped
            shown.append(s)
        while shown and not shown[-1]:
            shown.pop()
        if shown:
            pieces.append(Piece(loc, " | ".join(shown)))
        cells, cell = [], []

    for m in MARKS.finditer(text, start, end):
        at, ch = m.start(), m[0]
        page_break = ch == "\x0c" and at + 1 not in doc.section_ends
        if page_break and doc.fc_after(at) not in doc.p_end_set:
            buf.append(text[pos:at] + "\n")  # a page break inside a paragraph
            pos = at + 1
            continue
        p = doc.para_at(at)
        s = flush(at, p)
        pos = at + 1
        if ch == "\x07" or p.itap >= 1:
            if not in_table:
                in_table, n_table, n_row = True, n_table + 1, 0
                cell_start = par_start
            if ch == "\x07" and p.ttp:
                row(s, p)
                cell_start = at + 1
            elif ch == "\x07":
                cell.append(s)
                cells.append((doc.shown("\n".join(cell)), cell_start, at + 1))
                cell, cell_start = [], at + 1
            else:  # a paragraph inside a cell, or a row end of a table inside the cell
                if s or not p.inner_ttp:
                    cell.append(s)
                if p.shaded:
                    doc._spans.append((par_start, at + 1, {}, True))
            par_start = at + 1
            continue
        if in_table:
            loose_cells()
            in_table = False
        paragraph(s, par_start, at + 1, p)
        par_start = at + 1
    loose_cells()
    tail = flush(end, None)
    if tail:
        paragraph(tail, par_start, end, _PLAIN)
