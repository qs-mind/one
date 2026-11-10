"""A Word 97-2003 document read into paragraphs and table rows, as the .docx reader gives them:
headings carried, list numbers shown, every cell of a row in its column (an empty cell keeps
its place), field instructions dropped and their results kept, hidden, deleted and symbol-font
characters left out and flagged. Work grows with the file: each lookup is a bisect."""

import bisect
import dataclasses
import re
import struct

from qsone.records.arabic import display_text
from qsone.records.extract import Piece
from qsone.records.hidden import Flag
from qsone.records.readers import doc_ole as ole
from qsone.records.readers import doc_props as props
from qsone.records.readers.doc_lists import Lists

MARKS = re.compile("[\r\x07\x0c]")
_DROP = dict.fromkeys(map(ord, "\x00\x01\x02\x03\x04\x05\x06\x08\x13\x14\x15\x1f\xad"))
_SHOWN = str.maketrans({"\x0b": "\n", "\x0e": "\n", "\t": " ", "\x1e": "-"}) | _DROP
_PLAIN = props.Para()
_PART_NAME = {"footnote": "footnote", "endnote": "endnote", "comment": "comment"}
_PART_NAME |= {"header": "header_footer", "textbox": "text_box", "header_textbox": "text_box"}
_RUNS = re.compile("[^\r\x07\x0c\x13\x14\x15]+")
_FIELD_MARKS = re.compile("[\x13\x14\x15]")
_FLIP = bytes([1, 0]) + bytes(range(2, 256))
_BUTTON = re.compile(r"\s*(?:MACROBUTTON|GOTOBUTTON)\s+\S+\s+", re.I)
_FORM = re.compile(r"\s*FORM(?:DROPDOWN|CHECKBOX)\b", re.I)
_KEEP = "\r\x07\x0c\x13\x14\x15"
LOST = {ole.STSHF: "styles", ole.SED: "sections", ole.BTE_PAPX: "tables"}
LOST |= {ole.BTE_CHPX: "hidden", ole.HDD: "headers", ole.PLF_LST: "numbering"}
LOST |= {ole.PLF_LFO: "numbering"}
DELETED, SYMBOL = 1, 2


def _join(s: str) -> str:
    """Surrogate pairs kept as two indexes while reading become one character again."""
    if not any("\ud800" <= c <= "\udfff" for c in s):
        return s
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _start(span: tuple) -> int:
    return span[0]


def _holding(spans: list[tuple], cp: int) -> tuple | None:
    """The span of `spans` (sorted, apart from each other) that holds `cp`, by bisect."""
    i = bisect.bisect_right(spans, cp, key=_start) - 1
    return spans[i] if i >= 0 and spans[i][0] <= cp < spans[i][1] else None


class Document:
    def __init__(self, streams: ole.Streams):
        self.wd, self.table = streams.wd, streams.table
        self.fib = ole.Fib(self.wd)
        self.text_pieces = ole.pieces_of(self.fib, self.wd, self.table)
        if self.text_pieces[0].cp != 0:
            raise ole.NotRead(ole.DAMAGED, "the piece table does not start at the first character")
        self.text, self.missing = ole.decode(self.text_pieces, self.wd)
        self.total = sum(self.fib.ccp.values())
        self.missing += max(self.fib.ccp["main"] - len(self.text), 0)
        self.text += "\x00" * max(self.total - len(self.text), 0)
        self.cp_starts = [p.cp for p in self.text_pieces]
        self._by_fc = sorted(self.text_pieces, key=lambda p: p.fc)
        self._fc_starts = [p.fc for p in self._by_fc]
        self.styles = props.styles_of(self.fib, self.table)
        self.lists = Lists(self.fib, self.table)
        runs = props.papx_runs(self.fib, self.wd, self.table, streams.data)
        self.p_starts, self.p_ends, self.p_props = runs
        self.p_end_set = set(self.p_ends)
        self._laid: dict[tuple, props.Para] = {}
        self._flagged: list[tuple[str, int, int]] = []  # kind, cp start, cp end
        self._spans: list[tuple[int, int, dict, bool]] = []  # cp start, end, locator, shaded
        self._merged: list[tuple[dict, str]] = []  # text in a cell that a merge covers
        self._raw = self.text
        self.notes: set[str] = set()  # what was read with less structure than the file has
        self.counts = {"deleted": 0, "symbols": 0, "forms": 0}
        self._hide()
        self._drop_field_codes()
        sed = self.fib.blob(self.table, ole.SED)
        n = (len(sed) - 4) // 16
        self.section_ends = set(struct.unpack_from(f"<{n + 1}I", sed, 0)[1:]) if n > 0 else set()

    def _piece_at(self, cp: int) -> ole.TextPiece:
        return self.text_pieces[max(bisect.bisect_right(self.cp_starts, cp) - 1, 0)]

    def fc_after(self, cp: int) -> int:
        p = self._piece_at(cp)
        return p.fc + (cp - p.cp + 1) * (2 if p.wide else 1)

    def para_at(self, cp: int) -> props.Para:
        """The properties of the paragraph whose mark is at `cp`: from the paragraph table,
        then what a fast save laid over the mark's piece."""
        piece = self._piece_at(cp)
        fc = piece.fc + (cp - piece.cp) * (2 if piece.wide else 1)
        i = bisect.bisect_right(self.p_starts, fc) - 1
        base = self.p_props[i] if i >= 0 and fc < self.p_ends[i] else _PLAIN
        if not piece.prm:
            return base
        key = (id(base), piece.prm)
        if key not in self._laid:
            p = dataclasses.replace(base)
            for op, arg in props.sprms(piece.prm):
                if op == 0x2416:
                    p.in_table = bool(arg[0])
                    p.itap = max(p.itap, 1) if p.in_table else 0
                elif op == 0x2417:
                    p.ttp = bool(arg[0])
                elif op == 0x6649:
                    p.itap = struct.unpack("<i", arg)[0]
                elif op == 0x664A:
                    p.itap = max(p.itap + struct.unpack("<i", arg)[0], 0)
                elif op == 0x244B:
                    p.inner_cell = bool(arg[0])
                elif op == 0x244C:
                    p.inner_ttp = bool(arg[0])
            if p.itap == 0:
                p.in_table = p.ttp = False
            self._laid[key] = p
        return self._laid[key]

    def _cp_ranges(self, fc0: int, fc1: int):
        """The CP ranges whose bytes lie in [fc0, fc1): one per text piece the bytes touch."""
        i = max(bisect.bisect_right(self._fc_starts, fc0) - 1, 0)
        while i < len(self._by_fc) and self._by_fc[i].fc < fc1:
            p = self._by_fc[i]
            size = 2 if p.wide else 1
            lo, hi = max(fc0, p.fc), min(fc1, p.fc + (p.end - p.cp) * size)
            if lo < hi:
                yield p.cp + (lo - p.fc) // size, p.cp + (hi - p.fc + size - 1) // size
            i += 1

    def _hide(self) -> None:
        """Hidden (vanish), deleted and symbol-font characters leave the text; marks stay.
        Hidden text follows Word's rule: the run's own value, else its character style, else
        its paragraph's style; 0x81 means the opposite of the style."""
        n = len(self.text)
        hid, gone = bytearray(n), bytearray(n)
        hidden_styles = {i for i in range(len(self.styles)) if props.style_vanish(self.styles, i)}
        if hidden_styles:  # rare: paragraphs whose style hides them
            start = 0
            for m in MARKS.finditer(self.text):
                if self.para_at(m.start()).istd in hidden_styles:
                    hid[start : m.end()] = b"\x01" * (m.end() - start)
                start = m.end()
        for fc0, fc1, c in props.chpx_runs(self.fib, self.wd, self.table, max(n, 1)):
            styled = props.style_vanish(self.styles, c.istd) if c.istd else None
            for a, b in self._cp_ranges(fc0, fc1):
                b = min(b, n)
                if a >= b:
                    continue
                if styled is not None:
                    hid[a:b] = (b"\x01" if styled else b"\x00") * (b - a)
                self._vanish(hid, a, b, c.vanish)
                if c.deleted or c.symbol:
                    gone[a:b] = bytes([DELETED if c.deleted else SYMBOL]) * (b - a)
                elif (c.half_points or 99) < 3:  # under 1.5 pt, as hidden.TINY_POINTS
                    self._flagged.append(("tiny_text", a, b))
                elif c.white and not c.shaded:
                    self._flagged.append(("white_text", a, b))
        for piece in self.text_pieces:  # what a fast save laid over a whole piece
            if piece.prm:
                c, a, b = props.char_props(piece.prm), piece.cp, min(piece.end, n)
                self._vanish(hid, a, b, c.vanish)
                if c.deleted:
                    gone[a:b] = bytes([DELETED]) * (b - a)
        if not any(hid) and not any(gone):
            return
        chars = list(self.text)
        hidden_spans = [(m.start(), m.end()) for m in re.finditer(b"\x01+", bytes(hid))]
        for a, b in hidden_spans:
            if not any(gone[a:b]):
                self._flagged.append(("invisible_text", a, b))
        for m in re.finditer(b"[\x01\x02]+", bytes(gone)):
            for i in range(m.start(), m.end()):
                if chars[i] not in _KEEP:
                    self.counts["deleted" if gone[i] == DELETED else "symbols"] += 1
        for a, b in hidden_spans + [m.span() for m in re.finditer(b"[\x01\x02]+", bytes(gone))]:
            for i in range(a, b):
                if chars[i] not in _KEEP:
                    chars[i] = "\x00"
        # white or tiny text that is hidden anyway is flagged once, as hidden
        starts = [a for a, _ in hidden_spans]

        def inside(cp: int) -> bool:
            i = bisect.bisect_right(starts, cp) - 1
            return i >= 0 and cp < hidden_spans[i][1]

        self._flagged = [f for f in self._flagged if f[0] == "invisible_text" or not inside(f[1])]
        self.text = "".join(chars)

    @staticmethod
    def _vanish(hid: bytearray, a: int, b: int, vanish: int | None) -> None:
        if vanish in (0, 1):
            hid[a:b] = (b"\x01" if vanish else b"\x00") * (b - a)
        elif vanish == 0x81:
            hid[a:b] = hid[a:b].translate(_FLIP)

    def _drop_field_codes(self) -> None:
        """Field instructions leave the text (begin mark to separator; to the end mark when a
        field has no result). Only a begin mark with its end mark counts: a stray mark hides
        nothing, so a damaged field cannot swallow the text after it."""
        stack: list[list[int]] = []  # [cp of begin, cp of separator or -1]
        spans = []
        for m in _FIELD_MARKS.finditer(self.text):
            if m[0] == "\x13":
                stack.append([m.start(), -1])
            elif m[0] == "\x14":
                if stack and stack[-1][1] < 0:
                    stack[-1][1] = m.start()
            elif stack:
                begin, sep = stack.pop()
                end = sep if sep >= 0 else m.start()
                if _FORM.match(self.text, begin + 1, end):
                    self.counts["forms"] += 1
                if sep < 0:  # no result: a button field shows the text written after its name
                    shown = _BUTTON.match(self.text, begin + 1, end)
                    if shown:
                        end = shown.end()
                spans.append((begin, end))
        if stack:
            self.notes.add("fields")
        if not spans:
            return
        chars = list(self.text)
        for a, b in spans:
            for i in range(a, b):
                if chars[i] not in "\r\x07\x0c":
                    chars[i] = "\x00"
        self.text = "".join(chars)

    def number(self, p: props.Para) -> str:
        ilfo, ilvl = p.ilfo, p.ilvl
        for s in props.chain(self.styles, p.istd):
            ilfo = s.ilfo if ilfo is None else ilfo
            ilvl = s.ilvl if ilvl is None else ilvl
        return self.lists.label(ilfo, ilvl)

    def pictures(self) -> int:
        """Pictures, drawings and objects in the text: their marks that are not hidden."""
        shown = sum(1 for m in re.finditer("\x01", self._raw) if self.text[m.start()] == "\x01")
        return self._raw.count("\x08") + shown

    def flags(self) -> tuple[list[Flag], list[Piece]]:
        """One flag per kind and paragraph or table row, as the .docx reader makes them. White
        text on a filled run, paragraph or cell shows, and is not flagged."""
        located = sorted(
            (s for s in self._spans if s[2]), key=_start
        )  # paragraphs and cells: apart
        fills = sorted(
            (s for s in self._spans if not s[2]), key=_start
        )  # filled paragraphs in a cell
        found: dict[tuple, list[str]] = {}
        for kind, a0, b0 in sorted(self._flagged, key=lambda f: f[1]):
            for m in _RUNS.finditer(self._raw, a0, b0):  # a run may cross a mark
                span = _holding(located, m.start())
                loc, shaded = (span[2], span[3]) if span else ({}, False)
                shaded = shaded or bool(_holding(fills, m.start()))
                if kind == "white_text" and (shaded or loc.get("part") == "text_box"):
                    continue  # on a fill it shows; a text box's own fill is not known here
                key = (kind, tuple(sorted(loc.items())))
                found.setdefault(key, []).append(m[0].translate(_SHOWN))
        flags, hidden = [], []
        for loc, text in self._merged:
            count = sum(not c.isspace() for c in text)
            flags.append(Flag("invisible_text", loc, " ".join(text.split())[:160], count))
            hidden.append(Piece(loc, text))
        for (kind, loc), texts in found.items():
            shown = display_text(_join("".join(texts)))
            count = sum(not c.isspace() for c in shown)
            if count:
                flags.append(Flag(kind, dict(loc), " ".join(shown.split())[:160], count))
                if kind == "invisible_text":
                    hidden.append(Piece(dict(loc), shown))
        return flags, hidden

    def read(self) -> list[Piece]:
        from qsone.records.readers.doc_blocks import blocks

        pieces: list[Piece] = []
        at, spans = 0, {}
        for part in ole.PARTS:
            spans[part] = (at, at + self.fib.ccp[part])
            at += self.fib.ccp[part]
        blocks(self, *spans["main"], "main", pieces)
        for part in ("footnote", "endnote", "comment", "header", "textbox", "header_textbox"):
            a, b = spans[part]
            if b > a:
                blocks(self, a, b, _PART_NAME[part], pieces)
        return pieces

    def shown(self, s: str) -> str:
        return display_text(_join(s.translate(_SHOWN)))
