"""Synthetic Word 97 (.doc) files made in pure Python, for the .doc reader's tests: no Word, no
LibreOffice. Just enough of the format for those tests; every text in them is sample data.

    word_doc(blocks, ...) -> bytes

`blocks`: ("p", text) a paragraph, ("h", text) a heading, ("li", text, level) a numbered list
paragraph (one list: «1.», then «1.1» …, `nfc` its number format), ("table", [[cell, ...], ...])
a table, "\\n" in a cell starting a paragraph. Inside a text: FIELD(instruction|result) a field,
HIDE(text) a hidden run, DEL(text) a tracked deletion, SYM(text) symbol-font characters,
WHITE(text) white text, HIDEWHITE(text) hidden white text of 1 pt.
`objects` are streams inside ObjectPool: {"Workbook": BIFF bytes} or {"Package": xlsx bytes}."""

import re
import struct

SECTOR = 512
FREE, END, FAT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD


def cfb(streams: dict[str, bytes]) -> bytes:
    """A version 3 compound file; a "/" in a name puts the stream in a storage. Each stream is
    padded to 4096 bytes at least, so there is no mini stream."""
    tree: dict = {}
    for path, body in streams.items():
        node = tree
        *dirs, leaf = path.split("/")
        for d in dirs:
            node = node.setdefault(d, {})
        node[leaf] = body
    entries: list[list] = [["Root Entry", 5, FREE, FREE, b""]]  # name, kind, right, child, body

    def add(node: dict) -> int:
        names = sorted(node, key=lambda n: (len(n), n.upper()))  # the order the format asks for
        ids = []
        for name in names:
            ids.append(len(entries))
            is_dir = isinstance(node[name], dict)
            entries.append([name, 1 if is_dir else 2, FREE, FREE, b"" if is_dir else node[name]])
            if is_dir:
                entries[ids[-1]][3] = add(node[name])
        for a, b in zip(ids, ids[1:], strict=False):  # siblings as a chain to the right
            entries[a][2] = b
        return ids[0] if ids else FREE

    entries[0][3] = add(tree)
    bodies = []
    for e in entries:
        body = e[4]
        if e[1] == 2:
            body += b"\0" * (4096 - len(body) if len(body) < 4096 else -len(body) % SECTOR)
        bodies.append(body)
    dir_sectors = -(-len(entries) // 4)
    data_sectors = sum(len(b) // SECTOR for b in bodies)
    fat_sectors = 1
    while fat_sectors * 128 < fat_sectors + dir_sectors + data_sectors:
        fat_sectors += 1
    assert fat_sectors <= 109, "too big for this small writer"
    fat = [FAT] * fat_sectors
    first_dir = len(fat)
    fat += [first_dir + i + 1 for i in range(dir_sectors - 1)] + [END]
    starts = []
    for body in bodies:
        n = len(body) // SECTOR
        starts.append(len(fat) if n else END)
        if n:
            fat += [len(fat) + i + 1 for i in range(n - 1)] + [END]
    fat += [FREE] * (fat_sectors * 128 - len(fat))
    header = bytearray(SECTOR)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 0x18, 0x003E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<II", header, 0x2C, fat_sectors, first_dir)
    struct.pack_into("<I", header, 0x38, 4096)
    struct.pack_into("<IIII", header, 0x3C, END, 0, END, 0)
    struct.pack_into("<109I", header, 0x4C, *range(fat_sectors), *[FREE] * (109 - fat_sectors))
    raw_entries = []
    for (name, kind, right, child, _), start, body in zip(entries, starts, bodies, strict=True):
        raw = name.encode("utf-16-le") + b"\0\0"
        e = bytearray(128)
        e[: len(raw)] = raw
        struct.pack_into("<HBB", e, 0x40, len(raw), kind, 1)
        struct.pack_into("<III", e, 0x44, FREE, right, child)
        struct.pack_into("<II", e, 0x74, start if kind == 2 else END if kind == 5 else 0, len(body))
        raw_entries.append(bytes(e))
    raw_entries += [bytes(128)] * (dir_sectors * 4 - len(raw_entries))
    return bytes(header) + struct.pack(f"<{len(fat)}I", *fat) + b"".join(raw_entries + bodies)


def _sprm(op: int, arg: bytes) -> bytes:
    return struct.pack("<H", op) + arg


IN_TABLE = _sprm(0x2416, b"\x01") + _sprm(0x6649, struct.pack("<i", 1))
CHARS = {
    "HIDE": _sprm(0x083C, b"\x01"),
    "DEL": _sprm(0x0800, b"\x01"),
    "SYM": _sprm(0x6A09, struct.pack("<HH", 0, 0xF0FC)),
    "WHITE": _sprm(0x2A42, b"\x08"),
}
CHARS["HIDEWHITE"] = CHARS["HIDE"] + CHARS["WHITE"] + _sprm(0x4A43, struct.pack("<H", 2))
SPECIAL = _sprm(0x0855, b"\x01")
_MARKUP = re.compile(r"FIELD\((.*?)\|(.*?)\)|(HIDEWHITE|HIDE|DEL|SYM|WHITE)\((.*?)\)")


def _row_mark(cells: int, merged: frozenset) -> bytes:
    edges = struct.pack(f"<{cells + 1}h", *(i * 9000 // cells for i in range(cells + 1)))
    tcs = b"".join(
        struct.pack("<HH", 0x0002 if c in merged else 0, 9000 // cells) + b"\0" * 16
        for c in range(cells)
    )
    body = bytes([cells]) + edges + tcs
    row = IN_TABLE + _sprm(0x2417, b"\x01")
    return row + _sprm(0xD608, struct.pack("<H", len(body) + 1) + body)


def _fkps(runs: list[tuple[int, int, bytes]], para: bool) -> list[bytes]:
    """512-byte pages for (fc start, fc end, property bytes) runs in fc order."""
    pages, i, width = [], 0, 13 if para else 1
    while i < len(runs):
        page, top, fcs, offsets = bytearray(512), 511, [runs[i][0]], []
        while i < len(runs):
            _, end, props = runs[i]
            if not props:
                blob = b""
            elif not para:
                blob = bytes([len(props)]) + props
            elif len(props) % 2:
                blob = bytes([(len(props) + 1) // 2]) + props
            else:
                blob = b"\0" + bytes([len(props) // 2]) + props
            n = len(offsets) + 1
            new_top = (top - len(blob)) & ~1 if blob else top
            if 4 * (n + 1) + width * n > new_top:
                break
            if blob:
                top = new_top
                page[top : top + len(blob)] = blob
            offsets.append(top // 2 if blob else 0)
            fcs.append(end)
            i += 1
        struct.pack_into(f"<{len(fcs)}I", page, 0, *fcs)
        for k, off in enumerate(offsets):
            page[4 * len(fcs) + width * k] = off
        page[511] = len(offsets)
        pages.append(bytes(page))
    return pages


def _std(istd: int, sti: int, kind: int, base: int, name: str) -> bytes:
    body = struct.pack("<HHHHH", sti, kind | base << 4, (2 if kind == 1 else 1) | istd << 4, 0, 0)
    body += struct.pack("<H", len(name)) + name.encode("utf-16-le") + b"\0\0"
    if kind == 1:
        body += struct.pack("<HH", 2, istd)
    body += struct.pack("<H", 0)
    return struct.pack("<H", len(body)) + body


def _stsh() -> bytes:
    stshi = struct.pack("<HHHHHH", 15, 10, 1, 0x005B, 15, 0) + struct.pack("<3H", 0, 0, 0)
    styles = {
        0: _std(0, 0, 1, 0xFFF, "Normal"),
        1: _std(1, 1, 1, 0, "heading 1"),
        10: _std(10, 65, 2, 0xFFF, "Default Paragraph Font"),
    }
    blob = b"".join(styles.get(i, struct.pack("<H", 0)) for i in range(15))
    return struct.pack("<H", len(stshi)) + stshi + blob


def _lists(nfc: int) -> tuple[bytes, bytes]:
    """One list of nine levels («%1.», «%1.%2», …) and one override naming it: PlfLst and its
    levels, and PlfLfo."""
    lst = struct.pack("<h", 1) + struct.pack("<ii", 7, 0) + b"\xff\xff" * 9 + b"\0\0"
    levels = b""
    for lv in range(9):
        xst = "".join(chr(k) + "." for k in range(lv + 1))
        xst = xst[:-1] if lv else xst
        nums = bytes(range(1, 2 * lv + 2, 2)) + b"\0" * (9 - lv - 1)
        lvlf = struct.pack("<iBB", 1, nfc, 0) + nums + b"\0" + b"\0" * 8 + bytes([0, 0, 0, 0])
        levels += lvlf + struct.pack("<H", len(xst)) + xst.encode("utf-16-le")
    lfo = struct.pack("<i", 1) + struct.pack("<iiiBBBB", 7, 0, 0, 0, 0, 0, 0) + struct.pack("<i", 0)
    return lst + levels, lfo


def word_doc(
    blocks,
    *,
    objects=(),
    nfc=0,
    pieces="wide",
    encrypted=False,
    nfib=0x00C1,
    ident=0xA5EC,
    chp_repeat=1,
) -> bytes:
    text: list[str] = []
    marks: list[tuple[int, bytes]] = []  # cp of each paragraph mark, its properties
    chars: dict[int, bytes] = {}

    def add(s: str, props: bytes, mark: str):
        at = 0
        for m in _MARKUP.finditer(s):
            text.extend(s[at : m.start()])
            at = m.end()
            if m[3]:
                chars.update(dict.fromkeys(range(len(text), len(text) + len(m[4])), CHARS[m[3]]))
                text.extend(m[4])
            else:
                for ch, part in (("\x13", f" {m[1]} "), ("\x14", m[2]), ("\x15", "")):
                    chars[len(text)] = SPECIAL
                    text.append(ch)
                    text.extend(part)
        text.extend(s[at:])
        marks.append((len(text), props))
        text.append(mark)

    plain, heading = struct.pack("<H", 0), struct.pack("<H", 1)
    if blocks and blocks[-1][0] == "table":
        blocks = [*blocks, ("p", "")]
    for block in blocks:
        kind, value = block[0], block[1]
        if kind == "table":
            for row in value:
                merged = frozenset(i for i, c in enumerate(row) if c.startswith("MERGED:"))
                for cell in row:
                    *first, last = cell.removeprefix("MERGED:").split("\n")
                    for line in first:
                        add(line, plain + IN_TABLE, "\r")
                    add(last, plain + IN_TABLE, "\x07")
                add("", plain + _row_mark(len(row), merged), "\x07")
        elif kind == "li":
            numbered = _sprm(0x460B, struct.pack("<h", 1)) + _sprm(0x260A, bytes([block[2]]))
            add(value, plain + numbered, "\r")
        else:
            add(value, heading if kind == "h" else plain, "\r")
    ccp_text = len(text)
    text = "".join(text)
    wide = pieces == "wide"
    fc_min = 0x600
    stream = bytearray(fc_min)
    stream += text.encode("utf-16-le") if wide else text.encode("latin-1")
    fc_mac = len(stream)
    size = 2 if wide else 1
    para_runs, at = [], fc_min
    for cp, props in marks:
        end = fc_min + (cp + 1) * size
        para_runs.append((at, end, props))
        at = end
    if at < fc_mac:
        para_runs.append((at, fc_mac, plain))
    char_runs: list[tuple[int, int, bytes]] = []
    for cp in range(len(text)):
        a, props = fc_min + cp * size, chars.get(cp, b"")
        if char_runs and char_runs[-1][2] == props:
            char_runs[-1] = (char_runs[-1][0], a + size, props)
        else:
            char_runs.append((a, a + size, props))
    stream += b"\0" * (-len(stream) % 512)
    pn_chp = len(stream) // 512
    chp_pages = _fkps(char_runs, para=False) or [bytes(512)]
    stream += b"".join(chp_pages)
    pn_pap = len(stream) // 512
    pap_pages = _fkps(para_runs, para=True)
    stream += b"".join(pap_pages)

    table, where = bytearray(), {}

    def put(index: int, blob: bytes):
        table.extend(b"\0" * (-len(table) % 2))
        where[index] = (len(table), len(blob))
        table.extend(blob)

    def bte(pages, first_pn, repeat=1):
        pns = [pn for pn in range(first_pn, first_pn + len(pages)) for _ in range(repeat)]
        firsts = [struct.unpack_from("<I", p, 0)[0] for p in pages for _ in range(repeat)]
        last = struct.unpack_from("<I", pages[-1], 4 * pages[-1][511])[0]
        return struct.pack(f"<{len(pns) + 1}I", *firsts, last) + struct.pack(f"<{len(pns)}I", *pns)

    put(1, _stsh())
    put(6, struct.pack("<II", 0, len(text)) + struct.pack("<HIHI", 0, 0x5F0, 0, 0xFFFFFFFF))
    put(12, bte(chp_pages, pn_chp, chp_repeat))
    put(13, bte(pap_pages, pn_pap))
    fc = fc_min if wide else fc_min * 2 | 0x40000000
    plc = struct.pack("<II", 0, len(text)) + struct.pack("<HIH", 0, fc, 0)
    put(33, b"\x02" + struct.pack("<I", len(plc)) + plc)
    if any(b[0] == "li" for b in blocks):
        lst, lfo = _lists(nfc)
        put(73, lst[: 2 + 28])
        table.extend(lst[2 + 28 :])  # the levels follow the lists
        put(74, lfo)

    fib = bytearray(0x9A + 93 * 8 + 2)
    flags = 0x0200 | 0x1000 | (0x0100 if encrypted else 0)
    struct.pack_into("<HHHHHH", fib, 0, ident, nfib, 0, 0x0409, 0, flags)
    struct.pack_into("<II", fib, 0x18, fc_min, fc_mac)
    struct.pack_into("<8i", fib, 0x4C, ccp_text, 0, 0, 0, 0, 0, 0, 0)
    struct.pack_into("<H", fib, 0x98, 93)
    for index, (at, lcb) in where.items():
        struct.pack_into("<II", fib, 0x9A + 8 * index, at, lcb)
    stream[: len(fib)] = fib
    streams = {"WordDocument": bytes(stream), "1Table": bytes(table)}
    for n, found in enumerate(objects, 1):
        for name, body in found.items():
            streams[f"ObjectPool/_{1000 + n}/{name}"] = body
    return cfb(streams)


def biff_workbook(rows: list[list]) -> bytes:
    """The Workbook stream of an .xls with one sheet «Sheet1» holding `rows`."""
    import io

    import olefile
    import xlwt

    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if value != "":
                sheet.write(r, c, value)
    out = io.BytesIO()
    book.save(out)
    with olefile.OleFileIO(io.BytesIO(out.getvalue())) as ole:
        return ole.openstream("Workbook").read()


def xlsx_package(rows: list[list]) -> bytes:
    import io

    import openpyxl

    book = openpyxl.Workbook()
    for row in rows:
        book.active.append([None if v == "" else v for v in row])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
