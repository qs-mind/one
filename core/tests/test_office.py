"""LibreOffice conversion; all documents and numbers here are sample data."""

import io
import socket
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from qsone import copy, projects
from qsone.app import create_app
from qsone.records import office, report
from qsone.records.extract import extract
from qsone.records.files import add_file, read_original
from qsone.records.project import RecordsError
from tests.conftest import AUTH, SECRET
from tests.samples import sample_xlsx


def word():
    doc = Document()
    doc.add_paragraph("Sample specification concrete")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.mark.parametrize("suffix", ["doc", "xls", "ods", "ppt", "pptx", "odt", "rtf"])
def test_missing_office_is_stored_and_reported(rec, monkeypatch, suffix):
    monkeypatch.setattr(office, "find_soffice", lambda: None)
    data = b"sample"
    f = add_file(rec, f"sample.{suffix}", data, actor="engineer")
    assert (f.kind, f.status, f.note) == (suffix, "stored", "FILE_LIBREOFFICE_MISSING")
    assert read_original(rec, f.id) == data
    lines = report.make(rec, [f.id])["lines"]
    for lang in ("en", "ar"):
        assert any(copy.FILE_LIBREOFFICE_MISSING[lang] in line[lang] for line in lines)
        assert office.DOWNLOAD_URL in copy.FILE_LIBREOFFICE_MISSING[lang]
    assert office.to_pdf(data, f"sample.{suffix}") is None


def test_timeout_cleans_source_output_and_profile(monkeypatch):
    monkeypatch.setattr(office, "find_soffice", lambda: "/sample/soffice")
    seen = []

    def timeout(args, **kwargs):
        source = Path(args[-1])
        seen.append(source.parent)
        assert source.read_bytes() == b"private sample"
        assert "--headless" in args
        assert any(a.startswith("-env:UserInstallation=file:///") for a in args)
        assert kwargs["timeout"] > 0
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(office, "_run", timeout)
    assert office.to_pdf(b"private sample", "../../sample.docx") is None
    assert seen and all(not p.exists() for p in seen)
    x = extract("sample.odt", b"private sample")
    assert x.note == "FILE_OFFICE_CONVERSION_FAILED"


@pytest.mark.parametrize("source,target", [("docx", "odt"), ("xlsx", "ods")])
def test_real_open_document_is_read_and_original_is_kept(rec, source, target):
    if office.find_soffice() is None:
        pytest.skip("LibreOffice is not installed")
    require_local_sockets()
    data = word() if source == "docx" else sample_xlsx({"Sample": [["Sample concrete", 12]]})
    original = office.convert(data, f"sample.{source}", target)
    assert original is not None
    f = add_file(rec, f"sample.{target}", original, actor="engineer")
    assert f.status == "read" and f.kind == target
    assert read_original(rec, f.id) == original
    x = extract(f.name, original)
    assert "concrete" in x.pieces[0].text
    assert x.pieces[0].locator == (
        {"page": 1} if target == "odt" else {"sheet": "Sample", "row": 1}
    )
    pdf = office.to_pdf(original, f.name)
    assert pdf and pdf.startswith(b"%PDF-")


def test_pdf_route_and_missing_converter(data_dir, monkeypatch):
    require_local_sockets()
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        pid = client.post("/projects", json={"name": "Sample"}, headers=AUTH).json()["id"]
        f = client.post(
            f"/projects/{pid}/files", params={"name": "sample.docx"}, content=word(), headers=AUTH
        ).json()
        url = f"/projects/{pid}/files/{f['id']}/pdf"
        assert client.post(url).status_code == 401
        monkeypatch.setattr(office, "find_soffice", lambda: None)
        response = client.post(url, headers=AUTH)
        assert response.status_code == 503
        assert office.DOWNLOAD_URL in response.text
        monkeypatch.setattr(office, "find_soffice", lambda: "sample-soffice")
        monkeypatch.setattr(office, "to_pdf", lambda data, name: b"%PDF-sample")
        response = client.post(url, headers=AUTH)
        assert response.status_code == 200 and response.content == b"%PDF-sample"
        assert response.headers["content-type"] == "application/pdf"
        assert client.post(f"/projects/{pid}/files/missing/pdf", headers=AUTH).status_code == 404


def require_local_sockets():
    if not hasattr(socket, "AF_UNIX"):
        return
    with tempfile.TemporaryDirectory(prefix="qsone-socket-probe-") as folder:
        with socket.socket(socket.AF_UNIX) as probe:
            try:
                probe.bind(str(Path(folder) / "probe"))
            except PermissionError:
                pytest.skip("Execution sandbox denies local sockets needed by integration tests")


def test_pdf_route_handler(rec, monkeypatch):
    f = add_file(rec, "sample.docx", word(), actor="engineer")
    router = projects.router(SimpleNamespace(get=lambda pid: rec))
    endpoint = next(
        r.endpoint for r in router.routes if getattr(r, "path", "").endswith("/{file_id}/pdf")
    )
    monkeypatch.setattr(office, "find_soffice", lambda: None)
    with pytest.raises(RecordsError) as error:
        endpoint(rec.id, f.id)
    assert error.value.status == 503
    monkeypatch.setattr(office, "find_soffice", lambda: "sample-soffice")
    monkeypatch.setattr(office, "to_pdf", lambda data, name: None)
    with pytest.raises(RecordsError) as error:
        endpoint(rec.id, f.id)
    assert error.value.status == 422
    monkeypatch.setattr(office, "to_pdf", lambda data, name: b"%PDF-sample")
    response = endpoint(rec.id, f.id)
    assert response.body == b"%PDF-sample" and response.media_type == "application/pdf"
    with pytest.raises(RecordsError) as error:
        endpoint(rec.id, "missing")
    assert error.value.status == 404


@pytest.mark.parametrize("suffix,target", list(office.READ_TARGETS.items()))
def test_converted_reading_retains_original_kind_and_locator(monkeypatch, suffix, target):
    from tests.samples import sample_pdf

    monkeypatch.setattr(office, "find_soffice", lambda: "sample-soffice")
    converted = (
        sample_xlsx({"Sample": [["Sample concrete", 12]]})
        if target == "xlsx"
        else sample_pdf([["Sample concrete 12"]])
    )
    calls = []

    def convert(data, name, to):
        calls.append((data, name, to))
        return converted

    monkeypatch.setattr(office, "convert", convert)
    result = extract(f"sample.{suffix}", b"original sample")
    assert calls == [(b"original sample", f"sample.{suffix}", target)]
    assert result.kind == suffix and result.status == "read"
    assert "12" in result.pieces[0].text
    assert result.pieces[0].locator == (
        {"sheet": "Sample", "row": 1} if target == "xlsx" else {"page": 1}
    )


def test_successful_conversion_cleans_all_temporary_files(monkeypatch):
    monkeypatch.setattr(office, "find_soffice", lambda: "sample-soffice")
    roots = []

    def run(args, **kwargs):
        source = Path(args[-1])
        roots.append(source.parent)
        output = Path(args[args.index("--outdir") + 1])
        (output / "source.pdf").write_bytes(b"%PDF-sample")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(office, "_run", run)
    assert office.to_pdf(b"private sample", "C:\\other\\sample.docx") == b"%PDF-sample"
    assert all(not root.exists() for root in roots)


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_standard_installation_discovery(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(office.shutil, "which", lambda name: None)
    monkeypatch.setattr(office.sys, "platform", platform)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    expected = (
        tmp_path / "LibreOffice/program/soffice.exe"
        if platform == "win32"
        else Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    )
    monkeypatch.setattr(Path, "is_file", lambda p: p == expected)
    assert office.find_soffice() == str(expected)


def test_runner_reaps_its_timed_out_process():
    import sys

    with pytest.raises(subprocess.TimeoutExpired):
        office._run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.05,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


@pytest.mark.parametrize("soffice", [None, "sample-soffice"])
def test_native_xls_is_unchanged_and_never_converted(rec, monkeypatch, soffice):
    from qsone.records.extract import Extracted, Piece
    from tests.samples import sample_xls
    from tests.test_files_report import BOQ_ROWS

    monkeypatch.setattr(office, "find_soffice", lambda: soffice)

    def unexpected_conversion(*args):
        pytest.fail("A readable XLS must never reach LibreOffice")

    monkeypatch.setattr(office, "convert", unexpected_conversion)
    data = sample_xls({"Sample": [["Sample concrete", 4.77, 39850.5]]})
    assert extract("sample.xls", data) == Extracted(
        "xls",
        "read",
        1,
        [Piece({"sheet": "Sample", "row": 1}, "Sample concrete | 4.77 | 39850.5")],
        None,
        [],
    )
    f = add_file(rec, "BOQ sample.xls", sample_xls({"BOQ": BOQ_ROWS}), actor="engineer")
    assert f.note is None
    lines = report.make(rec, [f.id])["lines"]
    assert lines[1]["en"].endswith(": BOQ.")
    assert lines[2]["en"].startswith("Sheet «BOQ»: 3 items in 2 sections")
    assert all("LibreOffice" not in line[lang] for line in lines for lang in ("en", "ar"))


def test_failed_xls_conversion_keeps_native_failure(monkeypatch):
    from qsone.records.extract import _reader

    monkeypatch.setattr(office, "find_soffice", lambda: "sample-soffice")
    calls = []

    def failed_conversion(*args):
        calls.append(args)
        return None

    monkeypatch.setattr(office, "convert", failed_conversion)
    data = b"\xd0\xcf\x11\xe0 broken sample"
    native = _reader("xls", data)
    assert native.status == "unreadable"
    assert extract("sample.xls", data) == native
    assert calls == [(data, "sample.xls", "xlsx")]
