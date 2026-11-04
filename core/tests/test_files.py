"""Files into Project Records: originals kept exactly in pieces, versions, refusals, audit."""

import pytest

from qsone import copy
from qsone.records import audit, files
from qsone.records.files import add_file, list_files, read_original
from qsone.records.project import Records, RecordsError
from tests.doubles import ConceptEmbedder
from tests.samples import sample_pdf, sample_xlsx


@pytest.fixture
def rec(tmp_path):
    rec = Records.create(tmp_path / "p", name="مشروع - عينة", actor="engineer")
    yield rec
    rec.close()


def test_original_kept_exactly_and_text_indexed(rec):
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف", "م3", 120]]})
    f = add_file(rec, "جدول الكميات - عينة.xlsx", data, actor="engineer")
    assert f.status == "read" and f.chunks == 1 and read_original(rec, f.id) == data
    assert (f.kind, f.size, f.pages, f.duplicate) == ("xlsx", len(data), 1, False)
    with rec.read() as c:
        assert c.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 1
    assert rec.meta()["normaliser_version"] == "1"


def test_same_bytes_twice_is_one_file(rec):
    data = sample_pdf([["Sub-Clause 14.2 Advance Payment"]])
    first = add_file(rec, "Conditions - sample.pdf", data, actor="engineer")
    again = add_file(rec, "Conditions copy - sample.pdf", data, actor="engineer")
    assert again.duplicate and again.id == first.id and again.name == first.name
    assert len(list_files(rec)) == 1


def test_same_name_new_bytes_is_a_new_version(rec):
    old = add_file(rec, "عينة.txt", "خرسانة قديمة".encode(), actor="engineer")
    new = add_file(rec, "عينة.txt", "خرسانة جديدة".encode(), actor="engineer")
    assert new.replaces == old.id and new.valid_until is None
    assert [f.id for f in list_files(rec)] == [new.id]
    both = {f.id: f for f in list_files(rec, include_old=True)}
    assert len(both) == 2 and both[old.id].valid_until is not None
    with rec.read() as c:
        assert [h["action"] for h in audit.history(c, old.id)] == ["create", "replace"]


def test_big_file_in_pieces_round_trips(rec):
    data = bytes(range(256)) * (9 * 1024 * 1024 // 256)
    f = add_file(rec, "نموذج - عينة.bin", data, actor="engineer")
    assert (f.status, f.note, f.chunks) == ("stored", "FILE_NOT_READ_YET", 0)
    with rec.read() as c:
        n = c.execute("SELECT count(*) FROM file_pieces WHERE sha256 = ?", (f.sha256,)).fetchone()
    assert n[0] == 3
    assert read_original(rec, f.id) == data


def test_too_big_and_empty_are_refused(rec, monkeypatch):
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 10)
    with pytest.raises(RecordsError) as e:
        add_file(rec, "عينة.txt", b"x" * 11, actor="engineer")
    assert e.value.text == copy.FILE_TOO_BIG and e.value.status == 413
    with pytest.raises(RecordsError) as e:
        add_file(rec, "عينة.txt", b"", actor="engineer")
    assert e.value.text == copy.FILE_EMPTY and e.value.status == 422
    assert list_files(rec, include_old=True) == []
    with rec.read() as c:
        assert c.execute("SELECT count(*) FROM file_pieces").fetchone()[0] == 0


def test_path_in_the_name_is_dropped(rec):
    f = add_file(rec, "../../عينة.pdf", sample_pdf([["text"]]), actor="engineer")
    assert f.name == "عينة.pdf"
    g = add_file(rec, "C:\\Users\\x\\عينة.txt", b"x", actor="engineer")
    assert g.name == "عينة.txt"
    long = add_file(rec, "ع" * 300 + ".txt", b"y", actor="engineer")
    assert len(long.name) == 255


def test_add_file_is_audited(rec):
    f = add_file(rec, "عينة.txt", b"x", actor="engineer")
    with rec.read() as c:
        rows = audit.history(c, f.id)
    assert [(r["action"], r["actor"], r["table"]) for r in rows] == [
        ("create", "engineer", "files")
    ]


def test_scanned_pdf_keeps_its_note(rec):
    f = add_file(rec, "عينة.pdf", sample_pdf([["Page one text"], []]), actor="engineer")
    assert (f.status, f.note, f.pages, f.chunks) == ("partly_read", "FILE_SCANNED_PAGES", 2, 1)


def test_with_an_embedder_vectors_are_made_after_the_commit(rec):
    emb = ConceptEmbedder()
    add_file(rec, "عينة.txt", "عزل الرطوبة\nحديد التسليح".encode(), actor="engineer", embedder=emb)
    with rec.read() as c:
        assert c.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 2


def test_file_text_index_and_vectors_not_readable_on_disk(rec):
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف", "م3", 120]]})
    add_file(rec, "جدول سري - عينة.xlsx", data, actor="engineer", embedder=ConceptEmbedder())
    for phase in ("open", "closed"):
        blob = b"".join(p.read_bytes() for p in rec.folder.rglob("*") if p.is_file())
        for word in ["جدول سري", "خرسانة مسلحة", "خرسان", "03/02", "sharedStrings"]:
            assert word.encode() not in blob, (phase, word)
        rec.close()
