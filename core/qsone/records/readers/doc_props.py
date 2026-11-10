"""A Word 97-2003 file's properties: paragraphs (tables, list numbers, outline level, fill) from
the PAPX pages, characters (hidden, deleted, symbol, tiny or white) from the CHPX pages, and the
style sheet (headings, hidden styles, list numbers by style). Each 512-byte page is read once."""

import struct
from dataclasses import dataclass

from qsone.records.readers.doc_ole import BTE_CHPX, BTE_PAPX, STSHF, Fib

_SPRA_SIZE = {0: 1, 1: 1, 2: 2, 3: 4, 4: 2, 5: 2, 7: 3}


def sprms(grpprl: bytes):
    """(opcode, operand bytes) for each property in a grpprl; stops quietly at damage."""
    i, n = 0, len(grpprl)
    while i + 2 <= n:
        op = grpprl[i] | grpprl[i + 1] << 8
        i += 2
        spra = op >> 13
        if spra == 6:
            if i >= n:
                return
            if op in (0xD608, 0xD606):  # sprmTDefTable: a two-byte length, itself less one
                if i + 2 > n:
                    return
                size = struct.unpack_from("<H", grpprl, i)[0] + 1
            elif op == 0xC615 and grpprl[i] == 255:  # sprmPChgTabs, long form
                if i + 2 > n:
                    return
                at = i + 2 + 4 * grpprl[i + 1]
                if at >= n:
                    return
                size = 2 + 4 * grpprl[i + 1] + 1 + 3 * grpprl[at]
            else:
                size = grpprl[i] + 1
        else:
            size = _SPRA_SIZE[spra]
        if i + size > n:
            return
        yield op, grpprl[i : i + size]
        i += size


def shd(b: bytes) -> bool:
    """A SHD (fore colour, back colour, pattern) that puts a colour behind the text."""
    if len(b) < 10:
        return False
    fore, back, pattern = b[0:4], b[4:8], struct.unpack_from("<H", b, 8)[0]
    if pattern == 0xFFFF:
        return False
    colour = back if pattern == 0 else fore
    if pattern > 1:
        return True
    return colour[3] != 0xFF and colour[:3] != b"\xff\xff\xff"


def shd80(v: int) -> bool:
    """The Word 97 shading word: colour indexes, 8 is white and 0 automatic."""
    if v == 0xFFFF:
        return False
    fore, back, pattern = v & 31, v >> 5 & 31, v >> 10
    return back not in (0, 8) if pattern == 0 else not (pattern == 1 and fore == 8)


@dataclass
class Para:
    istd: int = 0
    shaded: bool = False
    shaded_cells: frozenset = frozenset()  # cells of this row with a fill (row mark only)
    in_table: bool = False
    ttp: bool = False
    itap: int = 0
    inner_cell: bool = False
    inner_ttp: bool = False
    outline: int | None = None
    skip: frozenset = frozenset()  # cells of this row that continue a merge (row mark only)
    ilfo: int | None = None  # the list it is numbered in (1-based), 0: none
    ilvl: int | None = None  # its level in that list


_CELL_SHD = {0xD612: 0, 0xD670: 0, 0xD616: 22, 0xD671: 22, 0xD60C: 44, 0xD672: 44}
_TABLE = {0x2416: "in_table", 0x2417: "ttp", 0x244B: "inner_cell", 0x244C: "inner_ttp"}


def para_props(grpprl_in_papx: bytes, data_stream: bytes) -> Para:
    p = Para()
    if len(grpprl_in_papx) < 2:
        return p
    p.istd = struct.unpack_from("<H", grpprl_in_papx, 0)[0]
    grpprl = grpprl_in_papx[2:]
    for op, arg in sprms(grpprl):  # a huge PAPX keeps the real list in the Data stream
        if op in (0x6646, 0x6645) and len(arg) == 4:
            fc = struct.unpack("<I", arg)[0]
            if fc + 2 <= len(data_stream):
                size = struct.unpack_from("<H", data_stream, fc)[0]
                grpprl = data_stream[fc + 2 : fc + 2 + size]
            break
    cells: dict[int, int] = {}  # cell -> 1 continues a horizontal, 2 a vertical merge
    fills: set[int] = set()
    for op, arg in sprms(grpprl):
        if op in _TABLE:
            setattr(p, _TABLE[op], bool(arg[0]))
        elif op == 0x442D:
            p.shaded = shd80(struct.unpack("<H", arg)[0])
        elif op == 0xC64D:
            p.shaded = shd(arg[1:11])
        elif op == 0xD609:  # sprmTDefTableShd80: a shading word per cell
            words = struct.unpack_from(f"<{(len(arg) - 1) // 2}H", arg, 1)
            fills |= {c for c, w in enumerate(words) if shd80(w)}
        elif op in _CELL_SHD:  # sprmTDefTableShd and its forms: 22 cells each
            first = _CELL_SHD[op]
            count = (len(arg) - 1) // 10
            fills |= {first + c for c in range(count) if shd(arg[1 + 10 * c : 11 + 10 * c])}
        elif op == 0x6649:
            p.itap = struct.unpack("<i", arg)[0]
        elif op == 0x664A:
            p.itap += struct.unpack("<i", arg)[0]
        elif op == 0x2640:
            p.outline = arg[0]
        elif op == 0x460B:
            p.ilfo = struct.unpack("<h", arg)[0]
        elif op == 0x260A:
            p.ilvl = arg[0]
        elif op == 0xD608 and len(arg) >= 3:  # sprmTDefTable: the cells' merge flags
            at = 3 + 2 * (arg[2] + 1)
            for c in range(arg[2]):
                if at + 2 > len(arg):
                    break
                tc = struct.unpack_from("<H", arg, at)[0]
                bits = (1 if tc & 0x0002 and not tc & 0x0001 else 0) | (
                    2 if tc & 0x0020 and not tc & 0x0040 else 0
                )
                if bits:
                    cells[c] = cells.get(c, 0) | bits
                at += 20
        elif op == 0xD62B and len(arg) >= 3:  # sprmTVertMerge: cell, 1 continues, 3 starts
            if arg[2] & 3 == 1:
                cells[arg[1]] = cells.get(arg[1], 0) | 2
            elif arg[2] & 3 == 3:
                cells[arg[1]] = cells.get(arg[1], 0) & ~2
    if p.in_table and p.itap == 0:
        p.itap = 1
    p.skip = frozenset(c for c, bits in cells.items() if bits)
    p.shaded_cells = frozenset(fills)
    return p


def _pages(fib: Fib, table: bytes, index: int) -> list[int]:
    """The FKP page numbers of the bin table, each once (a damaged table may repeat them)."""
    plc = fib.blob(table, index)
    n = (len(plc) - 4) // 8
    if n < 1:
        return []
    found = struct.unpack_from(f"<{n}I", plc, 4 * (n + 1))
    return list(dict.fromkeys(pn & 0x3FFFFF for pn in found))


def _page(fib: Fib, wd: bytes, pn: int, index: int) -> bytes | None:
    page = wd[pn * 512 : pn * 512 + 512]
    if len(page) < 512:
        fib.lost.add(index)
        return None
    return page


def papx_runs(fib: Fib, wd: bytes, table: bytes, data_stream: bytes):
    """Sorted (fc starts, fc ends, Para): one entry per paragraph that has properties."""
    rows: list[tuple[int, int, Para]] = []
    cache: dict[bytes, Para] = {}
    for pn in _pages(fib, table, BTE_PAPX):
        page = _page(fib, wd, pn, BTE_PAPX)
        if page is None or 4 * (page[511] + 1) + 13 * page[511] > 511:
            continue
        count = page[511]
        fcs = struct.unpack_from(f"<{count + 1}I", page, 0)
        for k in range(count):
            off = page[4 * (count + 1) + 13 * k] * 2
            if not off:
                continue
            cb = page[off]
            raw = (
                page[off + 1 : off + 2 * cb] if cb else page[off + 2 : off + 2 + 2 * page[off + 1]]
            )
            p = cache.get(raw)
            if p is None:
                p = cache[raw] = para_props(raw, data_stream)
            rows.append((fcs[k], fcs[k + 1], p))
    rows.sort(key=lambda r: r[0])
    return [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]


@dataclass
class Char:
    vanish: int | None = None  # 0, 1, or 0x80/0x81 (as the style / the style's opposite)
    deleted: bool = False
    half_points: int | None = None
    white: bool | None = None
    symbol: bool = False
    istd: int | None = None
    shaded: bool = False


def char_props(grpprl: bytes) -> Char:
    c = Char()
    for op, arg in sprms(grpprl):
        if op == 0x083C:
            c.vanish = arg[0]
        elif op == 0x0800:
            c.deleted = bool(arg[0] & 1)
        elif op == 0x4A43:
            c.half_points = struct.unpack("<H", arg)[0]
        elif op == 0x2A42:
            c.white = arg[0] == 8
        elif op == 0x6870:
            c.white = arg[:3] == b"\xff\xff\xff" and arg[3] == 0
        elif op == 0x6A09:
            c.symbol = True
        elif op == 0x4866:
            c.shaded = c.shaded or shd80(struct.unpack("<H", arg)[0])
        elif op == 0xCA71:
            c.shaded = c.shaded or shd(arg[1:11])
        elif op == 0x2A0C:
            c.shaded = c.shaded or arg[0] not in (0, 8)
        elif op == 0x4A30:
            c.istd = struct.unpack("<H", arg)[0]
    return c


def chpx_runs(fib: Fib, wd: bytes, table: bytes, limit: int):
    """(fc start, fc end, Char) for the runs that hide, delete, shrink or whiten text; at most
    `limit` of them (the number of characters: a run holds one at least)."""
    out = []
    cache: dict[bytes, Char] = {}
    for pn in _pages(fib, table, BTE_CHPX):
        page = _page(fib, wd, pn, BTE_CHPX)
        if page is None or 4 * (page[511] + 1) + page[511] > 511:
            continue
        count = page[511]
        fcs = struct.unpack_from(f"<{count + 1}I", page, 0)
        for k in range(count):
            off = page[4 * (count + 1) + k] * 2
            if not off:
                continue
            raw = page[off + 1 : off + 1 + page[off]]
            c = cache.get(raw)
            if c is None:
                c = cache[raw] = char_props(raw)
            tiny = (c.half_points or 99) < 3
            if c.vanish is not None or c.deleted or c.symbol or c.white or tiny or c.istd:
                out.append((fcs[k], fcs[k + 1], c))
                if len(out) >= limit:
                    out.sort(key=lambda r: r[0])
                    return out
    out.sort(key=lambda r: r[0])
    return out


@dataclass
class Style:
    sti: int = 0xFFF
    kind: int = 0
    base: int = 0xFFF
    name: str = ""
    outline: int | None = None
    vanish: int | None = None
    ilfo: int | None = None
    ilvl: int | None = None


def styles_of(fib: Fib, table: bytes) -> list[Style | None]:
    blob = fib.blob(table, STSHF)
    out: list[Style | None] = []
    try:
        cb_stshi = struct.unpack_from("<H", blob, 0)[0]
        count, base_size = struct.unpack_from("<HH", blob, 2)
        at = 2 + cb_stshi
        for _ in range(count):
            size = struct.unpack_from("<H", blob, at)[0]
            std = blob[at + 2 : at + 2 + size]
            at += 2 + size
            if not size:
                out.append(None)
                continue
            w0, w1, w2 = struct.unpack_from("<HHH", std, 0)
            s = Style(sti=w0 & 0x0FFF, kind=w1 & 0x000F, base=w1 >> 4)
            cch = struct.unpack_from("<H", std, base_size)[0]
            s.name = std[base_size + 2 : base_size + 2 + 2 * cch].decode("utf-16-le", "replace")
            pos = base_size + 2 + 2 * cch + 2
            for upx in range(w2 & 0x000F):
                pos += pos & 1
                if pos + 2 > len(std):
                    break
                n = struct.unpack_from("<H", std, pos)[0]
                body = std[pos + 2 : pos + 2 + n]
                pos += 2 + n
                if s.kind == 1 and upx == 0:  # paragraph properties: istd, then the list
                    p = para_props(body, b"")
                    s.outline, s.ilfo, s.ilvl = p.outline, p.ilfo, p.ilvl
                elif (s.kind == 1 and upx == 1) or (s.kind == 2 and upx == 0):
                    s.vanish = char_props(body).vanish
            out.append(s)
    except struct.error:
        pass  # a damaged style sheet costs the headings, not the text
    return out


def chain(styles: list[Style | None], istd: int):
    seen = set()
    while istd < len(styles) and istd not in seen and styles[istd] is not None:
        seen.add(istd)
        yield styles[istd]
        istd = styles[istd].base


def is_heading(styles: list[Style | None], p: Para) -> bool:
    if p.outline is not None:
        return p.outline < 9
    for depth, s in enumerate(chain(styles, p.istd)):
        name = s.name.lower()
        named = name.startswith("heading") or name == "title"
        if depth == 0 and (1 <= s.sti <= 9 or s.sti == 62 or named):
            return True
        if s.outline is not None:
            return s.outline < 9
        if 1 <= s.sti <= 9:
            return True
    return False


def style_vanish(styles: list[Style | None], istd: int) -> bool | None:
    """Hidden text by style: the value set by the nearest style, None when no style sets it.
    0 and 1 set it; 0x81 is the opposite of the style it is based on; 0x80 leaves it."""
    value = None
    for s in reversed(list(chain(styles, istd))):
        if s.vanish in (0, 1):
            value = bool(s.vanish)
        elif s.vanish == 0x81:
            value = not value
    return value
