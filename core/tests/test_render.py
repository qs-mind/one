"""PDF pages as PNG images, in memory (Plan 7's `records/render.py`, added early by Plan 5)."""

import struct
import tempfile
import zlib

import pytest

from qsone.records import render
from tests.samples import sample_pdf


def _chunks(png: bytes) -> dict[bytes, bytes]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    out, at = {}, 8
    while at < len(png):
        (length,) = struct.unpack(">I", png[at : at + 4])
        kind, data = png[at + 4 : at + 8], png[at + 8 : at + 8 + length]
        (crc,) = struct.unpack(">I", png[at + 8 + length : at + 12 + length])
        assert crc == zlib.crc32(kind + data) & 0xFFFFFFFF
        out[kind] = out.get(kind, b"") + data
        at += 12 + length
    return out


def test_page_image_is_a_png_of_the_asked_width():
    pdf = sample_pdf([["Page one"], ["ط.م ٥١٩٣ ةناسرخ"]])
    png = render.page_png(pdf, 2, 400)
    width, height = struct.unpack(">II", _chunks(png)[b"IHDR"][:8])
    assert width == 400 and abs(height - 400 * 842 / 595) < 1
    assert render.page_count(pdf) == 2


def test_missing_page_is_refused():
    pdf = sample_pdf([["Page one"]])
    for page in (0, 2):
        with pytest.raises(IndexError):
            render.page_png(pdf, page, 400)


def test_png_writer_round_trips_with_zlib():
    rgba = bytes([255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 1, 2, 3, 4])
    chunks = _chunks(render._png(2, 2, rgba, 8))
    assert chunks[b"IHDR"] == struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0)
    assert zlib.decompress(chunks[b"IDAT"]) == b"\x00" + rgba[:8] + b"\x00" + rgba[8:]
    assert b"IEND" in chunks


def test_no_temp_files_while_rendering(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("render wrote a temp file")

    for name in (
        "mkstemp",
        "mkdtemp",
        "NamedTemporaryFile",
        "TemporaryFile",
        "SpooledTemporaryFile",
    ):
        monkeypatch.setattr(tempfile, name, refuse)
    assert render.page_png(sample_pdf([["عينة"]]), 1, 200)[:4] == b"\x89PNG"
