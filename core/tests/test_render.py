"""PDF pages as PNG images, in memory (Plan 7's `records/render.py`, added early by Plan 5)."""

import struct
import tempfile
import zlib

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.records import render
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_xlsx


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


# The route: GET /projects/{id}/files/{file_id}/pages/{n} (Plan 7, Task 2) -----------------------


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


@pytest.fixture
def project(client):
    return client.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]


def _upload(client, project, name, data) -> str:
    r = client.post(f"/projects/{project}/files", params={"name": name}, content=data, headers=AUTH)
    return r.json()["id"]


def test_page_image_route_is_a_png_of_the_asked_width(client, project):
    fid = _upload(client, project, "مواصفات - عينة.pdf", sample_pdf([["Page one"], ["ط.م ٥١٩٣"]]))
    r = client.get(f"/projects/{project}/files/{fid}/pages/2", params={"width": 400}, headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">I", r.content[16:20])[0] == 400


def test_missing_page_and_non_pdf(client, project):
    fid = _upload(client, project, "مواصفات - عينة.pdf", sample_pdf([["Page one"], ["Page two"]]))
    r = client.get(f"/projects/{project}/files/{fid}/pages/3", headers=AUTH)
    assert r.status_code == 404 and r.json() == {"error": copy.PAGE_NOT_FOUND, "field": "page"}
    sheet = _upload(client, project, "مقايسة - عينة.xlsx", sample_xlsx({"BOQ": [["3/02"]]}))
    r = client.get(f"/projects/{project}/files/{sheet}/pages/1", headers=AUTH)
    assert r.status_code == 409 and r.json() == {"error": copy.FILE_HAS_NO_PAGES, "field": "file"}


@pytest.mark.parametrize("width", [199, 5601])  # 5,600 px: sharp pages when zoomed
def test_page_width_is_bounded(client, project, width):
    fid = _upload(client, project, "مواصفات - عينة.pdf", sample_pdf([["Page one"]]))
    url = f"/projects/{project}/files/{fid}/pages/1"
    assert client.get(url, params={"width": width}, headers=AUTH).status_code == 422


def test_no_temp_files_while_the_route_renders(client, project, monkeypatch):
    fid = _upload(client, project, "مواصفات - عينة.pdf", sample_pdf([["Page one"]]))

    def refuse(*args, **kwargs):
        raise AssertionError("the route wrote a temp file")

    for name in ("mkstemp", "mkdtemp", "NamedTemporaryFile", "TemporaryFile"):
        monkeypatch.setattr(tempfile, name, refuse)
    r = client.get(f"/projects/{project}/files/{fid}/pages/1", headers=AUTH)
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
