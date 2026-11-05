"""Patch the client's own xlsx, cell by cell, without breaking it. Pure: bytes in, bytes out.

Only the mapped cells change. Each touched sheet is read with `expat` to find the byte range of
each target `<c>`, and only that element is rebuilt or inserted; the rest of the part is copied
byte for byte, so styles, drawings, names, validations and conditional formats stay as the client
made them. A cell holding the client's formula is never overwritten. `fullCalcOnLoad` is set in
`xl/workbook.xml`, so Excel recalculates the client's own formulas when the file opens. Every
other zip entry keeps its bytes, name, order, date and compression. Stdlib only (no lxml).
"""

import io
import posixpath
import re
import xml.parsers.expat
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from xml.sax.saxutils import escape

from qsone import copy
from qsone.records.project import RecordsError

MAX_PART_BYTES = 64 * 1024 * 1024  # a zip-bomb guard: no part of a BOQ is this big
MAX_COLUMN, MAX_ROW = 16384, 1048576  # XFD, as Excel
WORKBOOK = "xl/workbook.xml"
_MAIN = {
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "http://purl.oclc.org/ooxml/spreadsheetml/main",
}
_REL = "relationships"  # the end of both the transitional and the strict namespace
# The children of <workbook> that come after <calcPr>, in schema order.
_AFTER_CALC = {
    "oleSize",
    "customWorkbookViews",
    "pivotCaches",
    "smartTagPr",
    "smartTagTypes",
    "webPublishing",
    "fileRecoveryPr",
    "webPublishObjects",
    "extLst",
}
_REF = re.compile(r"([A-Z]{1,3})([0-9]{1,7})")
_ATTR = re.compile(rb"""(\s+)([^\s=/>]+)\s*=\s*("[^"]*"|'[^']*')""")
_QNAME = re.compile(rb"<([^\s/>]+)")
_TAG_END = re.compile(rb"""(?:[^"'>]|"[^"]*"|'[^']*')*>""")
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


@dataclass(frozen=True)
class Write:
    sheet: str
    cell: str  # "F12"
    value: Decimal | str


@dataclass(frozen=True)
class Patched:
    data: bytes
    written: list[str]
    skipped: list[tuple[str, str]]  # (cell, "formula" | "merged")


def column_number(letters: str) -> int | None:
    """`A` is 1 and `XFD` is 16384; anything else is None."""
    if not re.fullmatch(r"[A-Z]{1,3}", letters):
        return None
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n if n <= MAX_COLUMN else None


def _cell_ref(ref: str) -> tuple[int, int]:
    m = _REF.fullmatch(ref)
    col = column_number(m[1]) if m else None
    if col is None or not 1 <= int(m[2]) <= MAX_ROW:
        raise ValueError(f"not a cell reference: {ref!r}")
    return col, int(m[2])


def _unreadable() -> RecordsError:
    return RecordsError(copy.FILE_UNREADABLE, status=422)


# Reading the zip and the workbook ---------------------------------------------------------------


def _read_zip(data: bytes) -> tuple[list[zipfile.ZipInfo], dict[str, bytes], bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            parts = {}
            for info in infos:
                if info.file_size > MAX_PART_BYTES:
                    raise _unreadable()
                with z.open(info) as f:
                    body = f.read(MAX_PART_BYTES + 1)
                if len(body) > MAX_PART_BYTES:
                    raise _unreadable()
                parts[info.filename] = body
            return infos, parts, z.comment
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, ValueError, EOFError):
        raise _unreadable() from None


def _parse(body: bytes, start, end=None) -> xml.parsers.expat.XMLParserType:
    """Runs expat over one part with `start(uri, local, attrs, index)` and `end(uri, local,
    index)`. A DOCTYPE is refused: no part of an xlsx has one, and entities could blow up."""
    p = xml.parsers.expat.ParserCreate(namespace_separator=" ")

    def on_start(name, attrs):
        uri, _, local = name.rpartition(" ")
        start(uri, local, attrs, p.CurrentByteIndex)

    def on_end(name):
        uri, _, local = name.rpartition(" ")
        end(uri, local, p.CurrentByteIndex)

    def no_doctype(*_):
        raise _unreadable()

    p.StartElementHandler = on_start
    if end is not None:
        p.EndElementHandler = on_end
    p.StartDoctypeDeclHandler = no_doctype
    try:
        p.Parse(body, True)
    except xml.parsers.expat.ExpatError:
        raise _unreadable() from None
    return p


def _sheet_paths(parts: dict[str, bytes]) -> dict[str, str]:
    """Sheet name -> its part path, through `xl/workbook.xml` and its relationships."""
    if WORKBOOK not in parts:
        raise _unreadable()
    sheets: dict[str, str] = {}
    targets: dict[str, str] = {}

    def on_sheet(uri, local, attrs, _):
        if uri in _MAIN and local == "sheet":
            rid = next((v for k, v in attrs.items() if k.endswith(f"{_REL} id")), None)
            if rid is not None and "name" in attrs:
                sheets[attrs["name"]] = rid

    def on_rel(_uri, local, attrs, _):
        if local == "Relationship" and attrs.get("TargetMode") != "External":
            targets[attrs.get("Id", "")] = attrs.get("Target", "")

    _parse(parts[WORKBOOK], on_sheet)
    _parse(parts.get("xl/_rels/workbook.xml.rels", b"<Relationships/>"), on_rel)
    out = {}
    for name, rid in sheets.items():
        target = targets.get(rid)
        if target is None:
            continue
        path = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
        out[name] = posixpath.normpath(path)
    return out


# Reading a sheet --------------------------------------------------------------------------------


def _tag_end(body: bytes, i: int) -> int:
    """The index just past the `>` of the tag that starts at `i` (a `>` inside quotes is text)."""
    m = _TAG_END.match(body, i + 1)
    if m is None:
        raise _unreadable()
    return m.end()


@dataclass
class _Cell:
    col: int
    start: int
    tag_end: int
    end: int = 0
    formula: bool = False


@dataclass
class _Row:
    n: int
    qname: bytes
    start: int
    tag_end: int
    empty: bool  # written <row .../>
    style: int | None
    close: int = 0  # where </row> starts
    cells: list[_Cell] = field(default_factory=list)


@dataclass
class _Sheet:
    rows: dict[int, _Row] = field(default_factory=dict)
    cols: list[tuple[int, int, int]] = field(default_factory=list)  # (min, max, style)
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)  # (c1, r1, c2, r2)


def _scan(body: bytes) -> _Sheet:
    sheet = _Sheet()
    state: dict = {"row": None, "cell": None, "last_row": 0, "last_col": 0}

    def start(uri, local, attrs, i):
        if uri not in _MAIN:
            return
        if local == "row":
            tag_end = _tag_end(body, i)
            n = int(attrs["r"]) if "r" in attrs else state["last_row"] + 1
            custom = attrs.get("customFormat") in ("1", "true")
            row = _Row(
                n,
                _QNAME.match(body, i)[1],
                i,
                tag_end,
                body[tag_end - 2 : tag_end] == b"/>",
                int(attrs["s"]) if custom and "s" in attrs else None,
            )
            state.update(row=row, last_row=n, last_col=0)
        elif local == "c" and state["row"] is not None:
            col = _cell_ref(attrs["r"])[0] if "r" in attrs else state["last_col"] + 1
            state["cell"] = _Cell(col, i, _tag_end(body, i))
            state["last_col"] = col
        elif local == "f" and state["cell"] is not None:
            state["cell"].formula = True
        elif local == "col" and "style" in attrs:
            sheet.cols.append((int(attrs["min"]), int(attrs["max"]), int(attrs["style"])))
        elif local == "mergeCell" and "ref" in attrs:
            a, _, b = attrs["ref"].partition(":")
            (c1, r1), (c2, r2) = _cell_ref(a), _cell_ref(b or a)
            sheet.merges.append((c1, r1, c2, r2))

    def end(uri, local, i):
        if uri not in _MAIN:
            return
        if local == "c" and state["cell"] is not None:
            cell = state["cell"]
            empty = body[cell.tag_end - 2 : cell.tag_end] == b"/>"
            cell.end = cell.tag_end if empty else _tag_end(body, i)
            state["row"].cells.append(cell)
            state["cell"] = None
        elif local == "row" and state["row"] is not None:
            row = state["row"]
            row.close = i
            sheet.rows[row.n] = row
            state["row"] = None

    try:
        _parse(body, start, end)
    except (KeyError, ValueError):  # a row or cell with a broken `r`
        raise _unreadable() from None
    return sheet


def sheet_rows(data: bytes, sheet: str) -> set[int]:
    """The row numbers the client's sheet has. Raises FILL_SHEET_NOT_FOUND."""
    _, parts, _ = _read_zip(data)
    return set(_scan(parts[_sheet_path(parts, sheet)]).rows)


def _sheet_path(parts: dict[str, bytes], sheet: str) -> str:
    path = _sheet_paths(parts).get(sheet)
    if path is None:
        raise RecordsError(copy.fill(copy.FILL_SHEET_NOT_FOUND, sheet=sheet), 422, "sheet")
    if path not in parts:
        raise _unreadable()
    return path


# Writing ----------------------------------------------------------------------------------------


def _number(value: Decimal) -> str:
    """Exact decimal text, never through float, never an exponent: 39850.50 -> 39850.5."""
    if not value.is_finite():
        raise ValueError(f"not a number: {value}")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _content(prefix: bytes, value: Decimal | str) -> tuple[bytes, bytes]:
    """(the `t` attribute, the children) for a cell holding `value`."""
    if isinstance(value, Decimal):
        return b"", b"<%sv>%s</%sv>" % (prefix, _number(value).encode(), prefix)
    text = escape(_NOT_XML.sub("", value)).encode()
    body = b'<%sis><%st xml:space="preserve">%s</%st></%sis>' % (
        prefix,
        prefix,
        text,
        prefix,
        prefix,
    )
    return b' t="inlineStr"', body


def _rebuilt(body: bytes, cell: _Cell, value: Decimal | str) -> bytes:
    """The cell with every attribute but `t` kept, holding `value`."""
    tag = body[cell.start : cell.tag_end]
    qname = _QNAME.match(tag)[1]
    prefix = qname[: -len(b"c")]
    kept = b"".join(ws + name + b"=" + v for ws, name, v in _ATTR.findall(tag) if name != b"t")
    t, children = _content(prefix, value)
    return b"<%s%s%s>%s</%s>" % (qname, kept, t, children, qname)


def _new_cell(sheet: _Sheet, row: _Row, col: int, ref: str, value: Decimal | str) -> bytes:
    """A cell Excel never wrote, styled as its row (when the row has its own format) or its
    column would show it."""
    prefix = row.qname[: -len(b"row")]
    style = row.style
    if style is None:
        style = next((s for lo, hi, s in sheet.cols if lo <= col <= hi), None)
    s = b"" if style is None else b' s="%d"' % style
    t, children = _content(prefix, value)
    return b'<%sc r="%s"%s%s>%s</%sc>' % (prefix, ref.encode(), s, t, children, prefix)


def _patch_sheet(
    body: bytes, writes: dict[str, Decimal | str]
) -> tuple[bytes, list[str], list[tuple[str, str]]]:
    sheet = _scan(body)
    splices: list[tuple[int, int, int, bytes]] = []  # (start, end, column, bytes)
    inserts: dict[int, list[tuple[int, bytes]]] = {}
    written, skipped = [], []
    for ref, value in writes.items():
        col, n = _cell_ref(ref)
        if any(
            c1 <= col <= c2 and r1 <= n <= r2 and (col, n) != (c1, r1)
            for c1, r1, c2, r2 in sheet.merges
        ):
            skipped.append((ref, "merged"))
            continue
        row = sheet.rows.get(n)
        if row is None:
            raise RecordsError(copy.fill(copy.FILL_ROW_MISSING, row=n), 422)
        cell = next((c for c in row.cells if c.col == col), None)
        if cell is not None and cell.formula:
            skipped.append((ref, "formula"))
            continue
        if cell is not None:
            splices.append((cell.start, cell.end, col, _rebuilt(body, cell, value)))
        else:
            inserts.setdefault(n, []).append((col, _new_cell(sheet, row, col, ref, value)))
        written.append(ref)
    for n, new in inserts.items():
        row = sheet.rows[n]
        if row.empty:  # <row .../> becomes <row ...>cells</row>
            cells = b"".join(xml for _, xml in sorted(new))
            closed = b">%s</%s>" % (cells, row.qname)
            splices.append((row.tag_end - 2, row.tag_end, 0, closed))
            continue
        for col, xml_ in new:
            at = next((c.start for c in row.cells if c.col > col), row.close)
            splices.append((at, at, col, xml_))
    out = bytearray(body)
    for start, end, _, xml_ in sorted(splices, key=lambda s: (s[0], s[2]), reverse=True):
        out[start:end] = xml_
    return bytes(out), written, skipped


def _full_calc_on_load(body: bytes) -> bytes:
    """`fullCalcOnLoad="1"` on <calcPr>, or a new <calcPr> in its place in the schema order."""
    found: dict = {"depth": 0, "calc": None, "after": None, "end": None, "qname": None}

    def start(uri, local, attrs, i):
        found["depth"] += 1
        if found["depth"] == 1:
            found["qname"] = _QNAME.match(body, i)[1]
        elif found["depth"] == 2 and uri in _MAIN:
            if local == "calcPr":
                found["calc"] = i
            elif local in _AFTER_CALC and found["after"] is None:
                found["after"] = i

    def end(_uri, _local, i):
        if found["depth"] == 1:
            found["end"] = i
        found["depth"] -= 1

    _parse(body, start, end)
    if found["calc"] is not None:
        i = found["calc"]
        tag_end = _tag_end(body, i)
        tag = body[i:tag_end]
        qname = _QNAME.match(tag)[1]
        kept = b"".join(
            ws + name + b"=" + v for ws, name, v in _ATTR.findall(tag) if name != b"fullCalcOnLoad"
        )
        close = b"/>" if tag.endswith(b"/>") else b">"
        return body[:i] + b'<%s%s fullCalcOnLoad="1"%s' % (qname, kept, close) + body[tag_end:]
    prefix = found["qname"][: -len(b"workbook")]
    at = found["after"] if found["after"] is not None else found["end"]
    return body[:at] + b'<%scalcPr fullCalcOnLoad="1"/>' % prefix + body[at:]


def _write_zip(infos: list[zipfile.ZipInfo], parts: dict[str, bytes], comment: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.comment = comment
        for old in infos:
            info = zipfile.ZipInfo(old.filename, old.date_time)
            info.compress_type = old.compress_type
            info.external_attr = old.external_attr
            info.create_system = old.create_system
            info.comment = old.comment
            z.writestr(info, parts[old.filename])
    return out.getvalue()


def patch_xlsx(data: bytes, writes: list[Write]) -> Patched:
    """Writes each value into its cell: a number as `<v>` exact text, text as an inline string;
    the cell keeps its style. Formula cells and merged cells other than the first are skipped and
    reported. Raises `RecordsError`: FILL_SHEET_NOT_FOUND, FILL_ROW_MISSING (a row the sheet does
    not have; nothing is written), or FILE_UNREADABLE."""
    infos, parts, comment = _read_zip(data)
    by_sheet: dict[str, dict[str, Decimal | str]] = {}
    for w in writes:
        _cell_ref(w.cell)
        by_sheet.setdefault(w.sheet, {})[w.cell] = w.value
    written, skipped = [], []
    for name, cells in by_sheet.items():
        path = _sheet_path(parts, name)
        parts[path], done, left = _patch_sheet(parts[path], cells)
        written += done
        skipped += left
    parts[WORKBOOK] = _full_calc_on_load(parts[WORKBOOK])
    return Patched(_write_zip(infos, parts, comment), written, skipped)
