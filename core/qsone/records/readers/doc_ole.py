"""A Word 97-2003 file's container and text: the OLE2 streams (olefile, in memory), the File
Information Block, and the piece table that holds the characters. Raises `NotRead` with a
reason when the bytes are not a Word 97-2003 file, or are locked or damaged."""

import array
import io
import struct
import sys
import zipfile
from dataclasses import dataclass, field

import olefile

CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

NOT_WORD = "not-word"  # an OLE2 file without a WordDocument stream, or other bytes
IS_DOCX = "is-docx"  # a .docx named .doc
IS_OTHER = "is-other"  # RTF, OpenDocument or a web page named .doc: LibreOffice reads them
TOO_OLD = "too-old"  # Word 6.0/95 or older
LOCKED = "locked"
DAMAGED = "damaged"

WORKBOOK_LIMIT = 16 * 1024 * 1024  # bytes of an Excel sheet inside the file that ONE reads


class NotRead(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


def sniff(data: bytes) -> None:
    """Raise NotRead for bytes that are not an OLE2 file, saying what they are."""
    if data.startswith(CFB):
        return
    head = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                kind = z.read("mimetype")[:60] if "mimetype" in names else b""
        except (zipfile.BadZipFile, OSError, KeyError, RuntimeError):
            raise NotRead(NOT_WORD, "a damaged zip archive") from None
        if "word/document.xml" in names:
            raise NotRead(IS_DOCX)
        if b"opendocument.text" in kind:
            raise NotRead(IS_OTHER, "OpenDocument")
        raise NotRead(NOT_WORD, "a zip archive")
    if head.startswith((b"{\\rtf", b"<html", b"<!doctype", b"<?xml", b"mime-version", b"<?mso")):
        raise NotRead(IS_OTHER, "RTF or markup")
    if b"<html" in head:
        raise NotRead(IS_OTHER, "markup")
    if data[:2] in (b"\xdb\xa5", b"\x9b\xa5", b"\x31\xbe", b"\x32\xbe"):
        raise NotRead(TOO_OLD, "Word 2.0 or Word for DOS")
    raise NotRead(NOT_WORD, "not an OLE2 file")


_OLD_IDENTS = {0xA5DC, 0xA697, 0xA698, 0xA699, 0x8098, 0x8099}  # Word 6.0/95, Far East too


@dataclass
class Embedded:
    """An object in ObjectPool: an Excel sheet's bytes when it is one, else just counted."""

    workbook: bytes | None = None  # its Workbook stream: BIFF records, which xlrd reads
    package: bytes | None = None  # an .xlsx (a zip in the Package stream)
    too_large: bool = False


@dataclass
class Streams:
    wd: bytes
    table: bytes
    data: bytes
    short: list[str]  # streams shorter than the directory says: the file is cut short
    objects: list[Embedded] = field(default_factory=list)


def open_streams(data: bytes) -> Streams:
    sniff(data)
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as e:  # olefile raises OSError, IndexError, struct.error... on damage
        raise NotRead(DAMAGED, f"container: {type(e).__name__}") from None
    try:
        names = {
            "/".join(n).lower(): "/".join(n) for n in ole.listdir(streams=True, storages=False)
        }
        if "worddocument" not in names:
            raise NotRead(LOCKED if "encryptedpackage" in names else NOT_WORD)
        short: list[str] = []
        wd = _stream(ole, names["worddocument"], short)
        if len(wd) < 0x20:
            raise NotRead(DAMAGED, "WordDocument shorter than its header")
        ident, nfib = struct.unpack_from("<HH", wd, 0)
        flags = struct.unpack_from("<H", wd, 0x0A)[0]
        if ident in _OLD_IDENTS or (ident == 0xA5EC and nfib < 0x00C0):
            raise NotRead(TOO_OLD, f"nFib {nfib}")
        if ident != 0xA5EC:
            raise NotRead(DAMAGED, f"wIdent {ident:#06x}")
        if flags & 0x0100:
            raise NotRead(LOCKED)
        table_name = "1table" if flags & 0x0200 else "0table"
        if table_name not in names:
            raise NotRead(DAMAGED, f"no {table_name}")
        table = _stream(ole, names[table_name], short)
        data_stream = _stream(ole, names["data"], short) if "data" in names else b""
        objects = [_embedded(ole, names, pool) for pool in _pools(ole)]
        return Streams(wd, table, data_stream, short, objects)
    finally:
        ole.close()


def _pools(ole) -> list[str]:
    return sorted(
        "/".join(n).lower()
        for n in ole.listdir(streams=False, storages=True)
        if len(n) == 2 and n[0].lower() == "objectpool"
    )


def _embedded(ole, names: dict[str, str], pool: str) -> Embedded:
    found = Embedded()
    for stream in ("workbook", "book"):
        name = names.get(f"{pool}/{stream}")
        if name is None:
            continue
        if ole.get_size(name) > WORKBOOK_LIMIT:
            return Embedded(too_large=True)
        found.workbook = ole.openstream(name).read()
        return found
    name = names.get(f"{pool}/package")
    if name is not None:
        if ole.get_size(name) > WORKBOOK_LIMIT:
            return Embedded(too_large=True)
        body = ole.openstream(name).read()
        if body.startswith(b"PK\x03\x04"):
            found.package = body
    return found


def _stream(ole, name: str, short: list[str]) -> bytes:
    try:
        body = ole.openstream(name).read()
        if len(body) < ole.get_size(name):  # olefile gives what is there and says nothing
            short.append(name)
        return body
    except Exception as e:
        raise NotRead(DAMAGED, f"stream {name}: {type(e).__name__}") from None


# the File Information Block: the index of each (fc, lcb) pair in FibRgFcLcb97
STSHF, SED, HDD, BTE_CHPX, BTE_PAPX, CLX, PLF_LST, PLF_LFO = 1, 6, 11, 12, 13, 33, 73, 74
PARTS = ("main", "footnote", "header", "macro", "comment", "endnote", "textbox", "header_textbox")


class Fib:
    def __init__(self, wd: bytes):
        if len(wd) < 0x9A + 8 * 34:
            raise NotRead(DAMAGED, "WordDocument too short for a Word 97 header")
        self.flags = struct.unpack_from("<H", wd, 0x0A)[0]
        self.fc_min = struct.unpack_from("<I", wd, 0x18)[0]
        self.ccp = dict(zip(PARTS, struct.unpack_from("<8i", wd, 0x4C), strict=True))
        if min(self.ccp.values()) < 0 or sum(self.ccp.values()) > len(wd):
            raise NotRead(DAMAGED, "text length")
        self.pairs = struct.unpack_from("<H", wd, 0x98)[0]
        self.lost: set[int] = set()  # structures that lie beyond the end of the table stream
        self._wd = wd

    def at(self, index: int) -> tuple[int, int]:
        if index >= self.pairs or 0x9A + 8 * index + 8 > len(self._wd):
            return 0, 0
        return struct.unpack_from("<II", self._wd, 0x9A + 8 * index)

    def blob(self, table: bytes, index: int) -> bytes:
        fc, lcb = self.at(index)
        if lcb and fc + lcb > len(table):
            self.lost.add(index)
            return b""
        return table[fc : fc + lcb]


@dataclass
class TextPiece:
    cp: int  # first CP
    end: int  # one past the last CP
    fc: int  # byte offset in WordDocument
    wide: bool  # 16-bit characters
    prm: bytes = b""  # properties a fast save laid over this piece


_PRM_SPRM = {0x18: 0x2416, 0x19: 0x2417, 0x41: 0x0800, 0x5C: 0x083C}


def pieces_of(fib: Fib, wd: bytes, table: bytes) -> list[TextPiece]:
    clx = fib.blob(table, CLX)
    if CLX in fib.lost:
        raise NotRead(DAMAGED, "the piece table lies outside the file")
    if not clx:  # no piece table: one run of text at fcMin (some non-Word writers)
        return [TextPiece(0, sum(fib.ccp.values()), fib.fc_min, bool(fib.flags & 0x1000))]
    i, prcs = 0, []  # property lists a fast save refers to from the pieces
    while i < len(clx) and clx[i] == 1:
        if i + 3 > len(clx):
            raise NotRead(DAMAGED, "piece table header")
        size = struct.unpack_from("<H", clx, i + 1)[0]
        prcs.append(clx[i + 3 : i + 3 + size])
        i += 3 + size
    if i + 5 > len(clx) or clx[i] != 2:
        raise NotRead(DAMAGED, "no piece table in the Clx")
    n = (struct.unpack_from("<I", clx, i + 1)[0] - 4) // 12
    if n < 1 or i + 5 + 4 * (n + 1) + 8 * n > len(clx):
        raise NotRead(DAMAGED, "piece table cut")
    cps = struct.unpack_from(f"<{n + 1}I", clx, i + 5)
    out = []
    for k in range(n):
        fc, prm = struct.unpack_from("<IH", clx, i + 5 + 4 * (n + 1) + 8 * k + 2)
        if cps[k + 1] < cps[k] or cps[k + 1] - cps[0] > len(wd):
            raise NotRead(DAMAGED, "piece table out of order")
        compressed = bool(fc & 0x40000000)
        fc &= 0x3FFFFFFF
        if prm & 1:
            props = prcs[prm >> 1] if prm >> 1 < len(prcs) else b""
        else:  # one property: its old short number and a one-byte value
            op = _PRM_SPRM.get(prm >> 1 & 0x7F)
            props = struct.pack("<HB", op, prm >> 8) if op else b""
        piece = TextPiece(cps[k], cps[k + 1], fc // 2 if compressed else fc, not compressed, props)
        out.append(piece)
    return out


_CP1252 = {
    b: ord(bytes([b]).decode("cp1252"))
    for b in range(0x80, 0xA0)
    if b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D)
}


def decode(pieces: list[TextPiece], wd: bytes) -> tuple[str, int]:
    """All the text, one str index per CP (a surrogate pair stays two), and how many CPs lay
    beyond the end of the stream (a file cut short)."""
    parts, missing = [], 0
    for p in pieces:
        n = p.end - p.cp
        size = n * (2 if p.wide else 1)
        raw = wd[p.fc : p.fc + size]
        if len(raw) < size:
            missing += (size - len(raw)) // (2 if p.wide else 1)
            raw = raw[: len(raw) // 2 * 2] if p.wide else raw
        if p.wide:
            text = raw.decode("utf-16-le", "surrogatepass")
            if len(text) != len(raw) // 2:  # astral characters: one index per code unit
                units = array.array("H", raw)
                if sys.byteorder == "big":
                    units.byteswap()
                text = "".join(map(chr, units))
        else:
            text = raw.decode("latin-1").translate(_CP1252)
        parts.append(text + "\x00" * (n - len(text)))
    return "".join(parts), missing
