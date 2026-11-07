import hashlib
from types import SimpleNamespace

import httpx
import pytest
from pypdfium2 import PdfiumError

from qsone.cli.commands import Commands
from qsone.records import files
from qsone.records.mapping import worker


def test_upload_timeout_reconciles(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_bytes(b"sample")

    def request(*args, **kwargs):
        assert kwargs["timeout"] == 300
        raise httpx.ReadTimeout("sample")

    client = SimpleNamespace(
        request=request,
        get=lambda *a, **k: {
            "files": [
                {
                    "name": path.name,
                    "sha256": hashlib.sha256(b"sample").hexdigest(),
                    "status": "read",
                }
            ]
        },
    )
    assert Commands(client, {}, None).files_add("p", [path])["added"] == 1


def test_download_directory_and_file(tmp_path):
    response = httpx.Response(200, content=b"sample")
    client = SimpleNamespace(
        http=SimpleNamespace(request=lambda *a, **k: response), check=lambda r: None
    )
    command = Commands(client, {}, None)
    result = command.download("/projects/p/files/f/pdf", tmp_path, method="POST")
    assert (tmp_path / "f.pdf").read_bytes() == b"sample"
    assert result["out"] == str(tmp_path / "f.pdf")
    target = tmp_path / "chosen.pdf"
    assert command.download("/pdf", target)["out"] == str(target)


def test_rejected_proposal_fields():
    proposal = dict(
        name={"en": "Sample", "ar": "عينة"},
        value="9%",
        file_id="f",
        locator={"page": 2},
        evidence="sample 9%",
    )
    client = SimpleNamespace(
        get=lambda *a, **k: {"rejected": [{"proposal": proposal, "reason": "not_grounded"}]}
    )
    row = Commands(client, {}, None).map_entries("p", "facts", rejected=True)["rejected"][0]
    assert all(row[k] == v for k, v in proposal.items())
    assert row["reason"] == "not_grounded"


@pytest.mark.parametrize("cause", [OSError, PdfiumError])
def test_local_map_transient_retry_once(rec, monkeypatch, cause):
    info = files.add_file(rec, "sample.txt", b"sample", actor="engineer")

    def fail(*args):
        raise cause("sample transient failure")

    monkeypatch.setattr(worker, "_structure", fail)
    worker.step(rec)
    with rec.read() as c:
        assert (
            c.execute("SELECT local_state FROM map_files WHERE file_id=?", (info.id,)).fetchone()[0]
            == "waiting"
        )
    worker.step(rec)
    with rec.read() as c:
        assert (
            c.execute("SELECT local_state FROM map_files WHERE file_id=?", (info.id,)).fetchone()[0]
            == "failed"
        )


def test_rejected_file_name(rec):
    from qsone.records.mapping import store

    info = files.add_file(rec, "sample.txt", b"sample", actor="engineer")
    proposal = {"file_id": info.id, "name": {"en": "Sample", "ar": "عينة"}, "value": "9%"}
    store.retain_rejected(rec, [(proposal, "not_grounded")])
    assert store.rejected_entries(rec)["rejected"][0]["file"] == info.name


def test_local_map_retry_recovers(rec, monkeypatch):
    from qsone.records.mapping import store

    info = files.add_file(rec, "sample.txt", b"sample", actor="engineer")
    structure = worker._structure
    calls = 0

    def once(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("sample transient failure")
        return structure(*args)

    monkeypatch.setattr(worker, "_structure", once)
    for _ in range(3):
        worker.step(rec)  # A fresh worker resumes persisted retry state.
    row = store.detail(rec, info.id)
    assert calls == 2 and row["local_state"] == "done"
    assert row["note"] is None
