"""ASCII DXF, read over its group codes line by line: TEXT, MTEXT (format codes stripped), ATTRIB
and ATTDEF text, and INSERT counts per block, one piece per layer. Text in block definitions is
read too, except in anonymous blocks (dimensions, hatches). Before AutoCAD 2007 text is in the
code page the header names (`$DWGCODEPAGE`, e.g. ANSI_1256 is cp1256); from 2007 it is UTF-8.
Binary DXF is not read here (see `is_binary`)."""

import codecs
import io
import re
from collections.abc import Iterator

from qsone.records.arabic import display_text
from qsone.records.extract import Piece

_ASCII = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*(?:999\r?\n[^\n]*\n\s*)?0\r?\nSECTION\r?\n")
_BINARY = b"AutoCAD Binary DXF\r\n\x1a\x00"
_WANTED = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF", "INSERT"}
_UNICODE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")
_SPECIAL = re.compile(r"%%(\d{3}|[cdpuoCDPUO%])")
_SPECIALS = {"c": "⌀", "d": "°", "p": "±", "u": "", "o": "", "%": "%"}
# MTEXT: escaped \ { }, paragraph and non-breaking space, codes ending in ';', switches, stacks.
_MTEXT = re.compile(r"\\(\\|\{|\}|P|~|[ACcFfHQTWp][^;]*;|[LlOoKkNX]|S([^;]*);)|[{}]")


def is_ascii(data: bytes) -> bool:
    return _ASCII.match(data[:4096]) is not None


def is_binary(data: bytes) -> bool:
    return data.startswith(_BINARY)


def read(data: bytes) -> list[Piece]:
    """Raises `ValueError` on a damaged file (a group code that is not a number)."""
    layers: dict[str, tuple[dict[str, int], dict[str, int]]] = {}  # texts, block inserts
    for kind, layer, text, block in _entities(data):
        texts, inserts = layers.setdefault(layer, ({}, {}))
        if kind == "INSERT":
            inserts[block] = inserts.get(block, 0) + 1
            continue
        text = _mtext(text) if kind == "MTEXT" else _special(_UNICODE.sub(_hex, text))
        text = " ".join(display_text(text).split())
        if text:
            texts[text] = texts.get(text, 0) + 1
    pieces = []
    for layer, (texts, inserts) in layers.items():
        parts = [t if n == 1 else f"{t} ×{n}" for t, n in texts.items()]
        parts += [f"{name} ×{n}" for name, n in inserts.items()]
        if parts:
            pieces.append(Piece({"layer": layer}, " | ".join([layer, *parts])))
    return pieces


def _pairs(data: bytes) -> Iterator[tuple[int, bytes]]:
    lines = iter(io.BytesIO(data))
    for code in lines:
        if not code.strip():
            continue
        yield int(code), next(lines, b"").rstrip(b"\r\n")


def _entities(data: bytes) -> Iterator[tuple[str, str, str, str]]:
    """(kind, layer, text, block name) for each text or INSERT entity in ENTITIES or BLOCKS."""
    section, version, codepage = None, "", None
    encoding = "cp1252"
    pending = None  # the header variable being read
    entity: dict | None = None
    skip_block = False
    for code, raw in _pairs(data):
        if code == 0:
            if entity is not None and not skip_block and entity["kind"] in _WANTED:
                text = "".join(entity["text"]) or entity["value"] or entity["tag"]
                yield entity["kind"], entity["layer"], text, entity["tag"]
            value = raw.decode("ascii", "replace").strip()
            entity = None
            if value == "ENDBLK":
                skip_block = False
            if value == "SECTION":
                section = "?"
                continue
            if value == "ENDSEC":
                section = None
                continue
            if section in ("ENTITIES", "BLOCKS"):
                entity = {"kind": value, "layer": "0", "text": [], "value": "", "tag": ""}
            continue
        if section == "?" and code == 2:
            section = raw.decode("ascii", "replace").strip()
            continue
        if section == "HEADER":
            if code == 9:
                pending = raw.decode("ascii", "replace").strip()
            elif pending == "$ACADVER" and code == 1:
                version = raw.decode("ascii", "replace").strip()
            elif pending == "$DWGCODEPAGE" and code == 3:
                codepage = raw.decode("ascii", "replace").strip()
            encoding = _encoding(version, codepage)
            continue
        if entity is None:
            continue
        value = raw.decode(encoding, "replace")
        if code == 8:
            entity["layer"] = value.strip() or "0"
        elif code == 2:
            entity["tag"] = value.strip()
            if entity["kind"] == "BLOCK":
                name = value.strip()
                skip_block = name.startswith("*") and not name.lower().startswith("*paper_space")
        elif code == 1:
            entity["value"] = value
        elif code == 3 and entity["kind"] == "MTEXT":
            entity["text"].append(value)
        if code == 1 and entity["kind"] == "MTEXT":
            entity["text"].append(value)


def _encoding(version: str, codepage: str | None) -> str:
    if version >= "AC1021":  # AutoCAD 2007 and later
        return "utf-8"
    m = re.fullmatch(r"(?:ANSI|DOS)_?(\d+)", (codepage or "").upper())
    if m:
        try:
            return codecs.lookup(f"cp{m[1]}").name
        except LookupError:
            pass
    return "cp1252"


def _hex(m: re.Match) -> str:
    return chr(int(m[1], 16))


def _special(text: str) -> str:
    def one(m: re.Match) -> str:
        code = m[1]
        return chr(int(code)) if code.isdigit() else _SPECIALS[code.lower()]

    return _SPECIAL.sub(one, text)


def _mtext(text: str) -> str:
    def one(m: re.Match) -> str:
        code = m[1]
        if code is None:
            return ""  # a brace that groups formatting
        if code in ("\\", "{", "}"):
            return code
        if code in ("P", "~"):
            return " "
        if m[2] is not None:  # a stack: 1/2, 1^2 and 1#2 all read as 1/2
            return re.sub(r"\s*[\^#]\s*", "/", m[2])
        return ""

    return _special(_MTEXT.sub(one, _UNICODE.sub(_hex, text)))
