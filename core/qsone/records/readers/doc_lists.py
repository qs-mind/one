"""List numbers of a Word 97-2003 file, as Word shows them («1.», «2.3», «أ-», «•»): the lists
(PlfLst, each followed in the table stream by its levels, LVL) and the list overrides (PlfLfo)
that paragraphs name with sprmPIlfo and sprmPIlvl. Numbers count up through the document;
a level starts again after a higher level is used."""

import struct
from dataclasses import dataclass, field

from qsone.records.readers.doc_ole import PLF_LFO, PLF_LST, Fib

_ROMAN = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l")]
_ROMAN += [(40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
_ARABIC_ALPHA = "أبتثجحخدذرزسشصضطظعغفقكلمنهوي"
_ABJAD = "أبجدهوزحطيكلمنسعفصقرشتثخذضظغ"
_BULLETS = {"", "", "", "", "", "", "·", "o"}


def _roman(n: int) -> str:
    out = []
    for value, letters in _ROMAN:
        while n >= value:
            out.append(letters)
            n -= value
    return "".join(out)


def _letters(n: int, alphabet: str) -> str:
    """1 → a, 26 → z, 27 → aa: Word repeats the letter."""
    n -= 1
    return alphabet[n % len(alphabet)] * (n // len(alphabet) + 1)


def number(n: int, nfc: int) -> str:
    if nfc in (1, 2):
        return _roman(n).upper() if nfc == 1 else _roman(n)
    if nfc in (3, 4):
        word = _letters(n, "abcdefghijklmnopqrstuvwxyz")
        return word.upper() if nfc == 3 else word
    if nfc == 22:
        return f"{n:02d}"
    if nfc == 46:
        return _letters(n, _ARABIC_ALPHA)
    if nfc == 48:
        return _letters(n, _ABJAD)
    if nfc == 255:
        return ""
    return str(n)


@dataclass
class Level:
    start: int = 1
    nfc: int = 0
    text: str = ""  # the number's text, characters 0-8 standing for the levels' numbers
    restart: bool = True


@dataclass
class _List:
    levels: list[Level]
    counts: list[int | None] = field(default_factory=lambda: [None] * 9)


def _level(table: bytes, at: int) -> tuple[Level, int]:
    """The LVL at `at`: a 28-byte LVLF, its paragraph and character properties, then its text."""
    start, nfc, bits = struct.unpack_from("<iBB", table, at)
    papx, chpx = table[at + 25], table[at + 24]
    pos = at + 28 + papx + chpx
    cch = struct.unpack_from("<H", table, pos)[0]
    text = table[pos + 2 : pos + 2 + 2 * cch].decode("utf-16-le", "replace")
    return Level(start, nfc, text, not bits & 0x08), pos + 2 + 2 * cch


class Lists:
    def __init__(self, fib: Fib, table: bytes):
        self.lists: dict[int, _List] = {}  # by lsid
        self.overrides: list[tuple[int, dict[int, int]]] = []  # by ilfo - 1: lsid, starts
        self.damaged = False
        try:
            self._read(fib, table)
        except (struct.error, IndexError):
            self.damaged = True

    def _read(self, fib: Fib, table: bytes) -> None:
        blob = fib.blob(table, PLF_LST)
        if not blob:
            return
        count = struct.unpack_from("<h", blob, 0)[0]
        fc, lcb = fib.at(PLF_LST)
        at = fc + lcb  # the levels follow the lists
        for k in range(max(count, 0)):
            lsid = struct.unpack_from("<i", blob, 2 + 28 * k)[0]
            simple = blob[2 + 28 * k + 26] & 1
            levels = []
            for _ in range(1 if simple else 9):
                level, at = _level(table, at)
                levels.append(level)
            self.lists[lsid] = _List(levels)
        lfo = fib.blob(table, PLF_LFO)
        if len(lfo) < 4:
            return
        n = struct.unpack_from("<i", lfo, 0)[0]
        heads = [struct.unpack_from("<i8xB", lfo, 4 + 16 * k) for k in range(max(n, 0))]
        pos = 4 + 16 * len(heads)
        for lsid, levels in heads:  # LFOData: a cp, then each level's override
            starts: dict[int, int] = {}
            pos += 4
            for _ in range(levels):
                start, bits = struct.unpack_from("<iI", lfo, pos)
                pos += 8
                if bits & 0x10:
                    starts[bits & 0x0F] = start
                if bits & 0x20:  # a whole level of its own: read past it
                    pos = _level(lfo, pos)[1]
            self.overrides.append((lsid, starts))

    def label(self, ilfo: int | None, ilvl: int | None) -> str:
        """The number the next paragraph of list `ilfo` at level `ilvl` shows, counted."""
        if not ilfo or ilfo < 1 or ilfo > len(self.overrides):
            return ""
        lsid, starts = self.overrides[ilfo - 1]
        found = self.lists.get(lsid)
        if found is None:
            return ""
        ilvl = min(ilvl or 0, len(found.levels) - 1)
        counts, level = found.counts, found.levels[ilvl]
        if counts[ilvl] is None:
            counts[ilvl] = starts.get(ilvl, level.start)
        else:
            counts[ilvl] += 1
        for deeper in range(ilvl + 1, 9):
            if deeper < len(found.levels) and found.levels[deeper].restart:
                counts[deeper] = None
        if level.nfc == 23:
            return "• "
        shown = []
        for ch in level.text:
            if ord(ch) < 9:
                lv = ord(ch)
                if lv < len(found.levels):
                    n = counts[lv] if counts[lv] is not None else found.levels[lv].start
                    shown.append(number(n, found.levels[lv].nfc))
            elif ch in _BULLETS:
                shown.append("•")
            else:
                shown.append(ch)
        text = "".join(shown).strip()
        return f"{text} " if text else ""
