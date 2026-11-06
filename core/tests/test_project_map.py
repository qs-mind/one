"""Local map tests: synthetic source documents, no AI."""

import json
import time
from pathlib import Path

from qsone.records import files, ocr
from qsone.records.mapping import store, worker
from tests.samples import sample_pdf, sample_xlsx


def drain(rec):
    original = worker.FilePass()
    while worker.step(rec, original=original):
        pass


def test_text_pdf_and_duplicate(rec):
    data = sample_pdf([["Sample conditions", "14.2 Advance payment"]])
    f = files.add_file(rec, "sample.pdf", data, actor="engineer")
    assert files.add_file(rec, "copy.pdf", data, actor="engineer").id == f.id
    drain(rec)
    row = store.detail(rec, f.id)
    assert row["local_state"] == "done"
    assert row["read_how"] == "text" and row["pages"] == 1
    assert row["structure"]["pages"][0]["page"] == 1
    assert store.list_map(rec)["status"]["total"] == 1
    assert set(store.list_map(rec)["status"]["line"]) == {"en", "ar"}


def test_scanned_page_stores_searchable_boxes(rec, monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda _, **kw: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(
        ocr,
        "read_image",
        lambda *a, **kw: ocr.Page([ocr.Word("Concrete", [10, 10, 80, 30], 95)], False),
    )
    f = files.add_file(rec, "scan.pdf", sample_pdf([[]]), actor="engineer")
    drain(rec)
    row = store.detail(rec, f.id)
    assert row["scanned_pages"] == row["ocr_done_pages"] == [1]
    assert row["read_how"] == "ocr"
    with rec.read() as c:
        text, loc = c.execute("SELECT text,locator FROM chunks WHERE file_id=?", (f.id,)).fetchone()
        assert c.execute("SELECT count(*) FROM chunks_fts").fetchone()[0] == 1
    assert text == "Concrete" and json.loads(loc)["box"] == [10, 10, 80, 30]


def test_excel_boq_and_replacement(rec):
    f = files.add_file(
        rec,
        "sample.xlsx",
        sample_xlsx(
            {
                "BOQ": [
                    ["Description", "Unit", "Quantity", "Rate", "Amount"],
                    ["Concrete sample", "m3", 10, 20, 200],
                    ["Total", "", "", "", 200],
                ]
            }
        ),
        actor="engineer",
        folder="Tender",
    )
    drain(rec)
    row = store.detail(rec, f.id)
    table = row["tables"][0]
    assert table["looks_like_boq"] and table["column_guess"]["quantity"] == "C"
    assert row["structure"]["sheets"][0]["totals_rows"] == [3]
    new = files.add_file(
        rec,
        "sample.xlsx",
        sample_xlsx({"BOQ": [["New sample"]]}),
        actor="engineer",
        folder="Tender",
    )
    assert store.detail(rec, f.id)["valid_until"] is not None
    assert store.detail(rec, f.id)["tables"][0]["valid_until"] is not None
    drain(rec)
    assert store.list_map(rec)["status"]["total"] == 1
    assert store.detail(rec, new.id)["local_state"] == "done"


def test_resume_and_missing_ocr(rec, monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    f = files.add_file(rec, "scan.pdf", sample_pdf([[]]), actor="engineer")
    assert worker.step(rec)
    assert store.detail(rec, f.id)["local_state"] == "reading"
    # A fresh worker has no in-memory progress and resumes the persisted row.
    drain(rec)
    row = store.detail(rec, f.id)
    assert row["local_state"] == "failed" and set(row["note"]) == {"en", "ar"}


def test_paging_2000_files(rec):
    with rec.write("engineer") as c:
        c.executemany(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "VALUES (?,?, 'txt',1,?,'stored',?,'engineer')",
            ((f"{i:05}", f"sample {i}", f"hash{i}", rec.clock()) for i in range(2000)),
        )
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qsone.records.mapping.routes import router

    app = FastAPI()
    app.include_router(router(SimpleNamespace(get=lambda _: rec)))
    with TestClient(app) as client:
        start = time.monotonic()
        page = client.get(f"/projects/{rec.id}/map", params={"limit": 31}).json()
        assert time.monotonic() - start < 2
        assert len(page["files"]) == 31 and page["status"]["total"] == 2000
        second = client.get(
            f"/projects/{rec.id}/map", params={"limit": 31, "cursor": page["next_cursor"]}
        ).json()
        assert not ({f["file_id"] for f in page["files"]} & {f["file_id"] for f in second["files"]})


def test_api_groups_facts_links_and_old_project(rec):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qsone.records.mapping.routes import router

    f = files.add_file(rec, "sample.txt", b"sample", actor="engineer", folder="Contract/Parts")
    app = FastAPI()

    class Projects:
        def get(self, pid):
            assert pid == rec.id
            return rec

    app.include_router(router(Projects()))
    with TestClient(app) as client:
        root = f"/projects/{rec.id}/map"
        assert client.get(root).json()["groups"][0]["path"] == "Contract"
        assert (
            client.get(root, params={"parent": "Contract"}).json()["groups"][0]["path"]
            == "Contract/Parts"
        )
        assert (
            client.get(root, params={"parent": "Contract/Parts/txt"}).json()["files"][0]["file_id"]
            == f.id
        )
        assert client.get(root + "/facts").json() == {"facts": [], "next_cursor": None}
        assert client.get(root + "/links").json() == {"links": [], "next_cursor": None}
        assert client.get(root + "/files/" + f.id).json()["local_state"] == "waiting"
        assert client.get(root, params={"limit": 201}).status_code == 422


def test_pdf_boq_table(rec):
    import typst

    data = typst.compile(b"""#set page(width: 600pt, height: 300pt)
#table(columns: 5, [Description], [Unit], [Quantity], [Rate], [Amount],
[Concrete sample], [m3], [10], [20], [200])""")
    f = files.add_file(rec, "sample.pdf", data, actor="engineer")
    drain(rec)
    row = store.detail(rec, f.id)
    assert row["local_state"] == "done"
    assert any(t["looks_like_boq"] and t["column_guess"]["quantity"] == "C" for t in row["tables"])
    assert row["tables"][0]["locator"]["page"] == 1
    assert len(row["tables"][0]["locator"]["box"]) == 4


def test_cancel_does_not_read_and_foreground_yields(rec):
    f = files.add_file(rec, "sample.txt", b"sample", actor="engineer")
    assert not worker.step(rec, cancelled=lambda: True)
    assert store.detail(rec, f.id)["local_state"] == "waiting"


def test_facts_links_are_audited_and_expire(rec):
    f = files.add_file(rec, "sample.txt", b"old sample", actor="engineer")
    with rec.write("engineer") as c:
        store.write(
            c,
            rec,
            "map_facts",
            {
                "id": "fact",
                "name": {"en": "Currency", "ar": "العملة"},
                "file_id": f.id,
                "locator": {},
                "state": "blank",
            },
            actor="engineer",
        )
        store.write(
            c,
            rec,
            "map_links",
            {
                "id": "link",
                "from_file_id": f.id,
                "to_file_id": f.id,
                "from_locator": {},
                "to_locator": {},
                "kind": "reference",
                "words": {"en": "See clause", "ar": "راجع البند"},
                "evidence": {},
                "by": "one",
            },
        )
    assert store.entries(rec, "facts")["facts"][0]["name"] == {"en": "Currency", "ar": "العملة"}
    files.add_file(rec, "sample.txt", b"new sample", actor="engineer")
    assert store.entries(rec, "facts")["facts"] == []
    assert store.entries(rec, "links")["links"] == []


def test_group_paging_is_independent_of_file_ids(rec):
    for i in range(5):
        files.add_file(
            rec, f"sample{i}.txt", f"sample {i}".encode(), actor="engineer", folder=f"Folder{i}"
        )
    page = store.list_map(rec, limit=2)
    groups = [g["path"] for g in page["groups"]]
    seen = [f["file_id"] for f in page["files"]]
    while page["next_cursor"]:
        page = store.list_map(rec, limit=2, cursor=page["next_cursor"])
        groups.extend(g["path"] for g in page["groups"])
        seen.extend(f["file_id"] for f in page["files"])
    assert len(groups) == len(set(groups)) == 5
    assert len(seen) == len(set(seen)) == 5


def test_inspector_scan_with_partial_text_still_gets_ocr(rec, monkeypatch):
    import types

    import pdf_inspector

    monkeypatch.setattr(
        pdf_inspector,
        "classify_pdf_bytes",
        lambda _: types.SimpleNamespace(pages_needing_ocr=[0], page_count=1),
    )
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda _, **kw: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(
        ocr,
        "read_image",
        lambda *a, **kw: ocr.Page([ocr.Word("Scanned sample", [10, 10, 80, 30], 95)], False),
    )
    f = files.add_file(rec, "partial.pdf", sample_pdf([["Only header"]]), actor="engineer")
    drain(rec)
    with rec.read() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM chunks WHERE file_id=? AND text='Scanned sample'", (f.id,)
            ).fetchone()[0]
            == 1
        )


def test_actual_restart_resumes_reading(rec):
    from qsone.records.project import Records

    f = files.add_file(rec, "sample.txt", b"sample restart", actor="engineer")
    assert worker.step(rec)
    assert store.detail(rec, f.id)["local_state"] == "reading"
    folder = rec.folder
    rec.close()
    reopened = Records.open(folder)
    try:
        drain(reopened)
        assert store.detail(reopened, f.id)["local_state"] == "done"
    finally:
        reopened.close()


def test_old_project_is_backfilled_in_bounded_batches(rec):
    with rec.write("engineer") as c:
        c.executemany(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "VALUES (?,?, 'txt',1,?,'stored',?,'engineer')",
            ((f"old{i}", f"sample {i}", f"oldhash{i}", rec.clock()) for i in range(205)),
        )
    assert store.seed(rec) == 100
    assert store.seed(rec) == 100
    assert store.seed(rec) == 5
    assert store.seed(rec) == 0
    drain(rec)
    assert store.list_map(rec)["status"]["done"] == 205


def test_word_headings_and_clauses(rec):
    from tests.samples import sample_docx

    data = sample_docx([("h1", "Sample conditions"), ("p", "14.2 Advance payment")])
    f = files.add_file(rec, "sample.docx", data, actor="engineer")
    drain(rec)
    structure = store.detail(rec, f.id)["structure"]
    assert structure["headings"][0]["text"] == "Sample conditions"
    assert structure["numbered_clauses"][0]["paragraph"] == 2


def test_missing_arabic_download_failure_uses_english(rec, monkeypatch, tmp_path):
    from qsone import copy

    system = tmp_path / "system"
    system.mkdir()
    (system / "eng.traineddata").touch()
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "system_folders", lambda _: [system])

    def refuse():
        raise ocr.download.DownloadError(copy.MEANING_DOWNLOAD_FAILED)

    monkeypatch.setattr(ocr, "ensure_models", refuse)
    languages = []

    def read(*args, **kwargs):
        languages.append(kwargs["languages"])
        return ocr.Page([ocr.Word("Sample", [10, 10, 80, 30], 95)], False)

    monkeypatch.setattr(ocr, "read_image", read)
    f = files.add_file(rec, "sample.pdf", sample_pdf([[], []]), actor="engineer")
    drain(rec)
    row = store.detail(rec, f.id)
    assert languages == ["eng", "eng"]
    assert row["local_state"] == "done" and row["ocr_done_pages"] == [1, 2]
    assert row["note"] == copy.MAP_ARABIC_MISSING


def test_missing_arabic_download_success_uses_both(rec, monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "system_folders", lambda _: [])
    downloaded = []

    def ensure():
        downloaded.append(True)
        return tmp_path

    monkeypatch.setattr(ocr, "ensure_models", ensure)
    languages = []

    def read(*args, **kwargs):
        languages.append(kwargs["languages"])
        return ocr.Page([ocr.Word("Sample", [10, 10, 80, 30], 95)], False)

    monkeypatch.setattr(ocr, "read_image", read)
    f = files.add_file(rec, "sample.pdf", sample_pdf([[]]), actor="engineer")
    drain(rec)
    row = store.detail(rec, f.id)
    assert downloaded and languages == ["ara+eng"]
    assert row["local_state"] == "done" and row["note"] is None


def test_mapping_failure_logs_type_without_private_content(rec, monkeypatch, caplog):
    import logging

    from qsone import copy

    f = files.add_file(rec, "private-name.txt", b"sample", actor="engineer")

    def fail(*args):
        raise ValueError("private file content")

    monkeypatch.setattr(worker, "_structure", fail)
    with caplog.at_level(logging.WARNING):
        assert worker.step(rec)
    assert "ValueError" in caplog.text
    assert "private file content" not in caplog.text and "private-name" not in caplog.text
    assert store.detail(rec, f.id)["note"] == copy.MAP_FAILED


def test_ocr_file_pass_reads_original_once(rec, monkeypatch):
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda _: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(ocr, "read_image", lambda *a, **kw: ocr.Page([], True))
    f = files.add_file(rec, "sample.pdf", sample_pdf([[], [], []]), actor="engineer")
    reads = []
    original = files.read_original

    def counted(*args):
        reads.append(args[1])
        return original(*args)

    monkeypatch.setattr(files, "read_original", counted)
    current = worker.FilePass()
    while worker.step(rec, original=current):
        pass
    assert reads == [f.id]
    assert store.detail(rec, f.id)["ocr_done_pages"] == [1, 2, 3]


def test_aligned_prose_is_not_a_table(rec):
    f = files.add_file(
        rec,
        "sample.pdf",
        sample_pdf([["This is a sample sentence about concrete work."] * 10]),
        actor="engineer",
    )
    drain(rec)
    assert store.detail(rec, f.id)["tables"] == []


def test_upload_and_open_wake_worker_without_running_it(data_dir):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qsone.projects import Projects, router

    registry = Projects(data_dir)

    class Wake:
        count = 0

        def wake(self):
            self.count += 1

    mapping = Wake()
    app = FastAPI()
    app.include_router(router(registry, mapping=mapping))
    with TestClient(app) as client:
        pid = client.post("/projects", json={"name": "Sample"}).json()["id"]
        uploaded = client.post(
            f"/projects/{pid}/files", params={"name": "sample.txt"}, content=b"sample"
        )
        assert uploaded.status_code == 201
        assert mapping.count == 1
        assert client.get(f"/projects/{pid}/map").json()["status"]["waiting"] == 1
        client.post(f"/projects/{pid}/open")
        assert mapping.count == 2
    registry.close_all()


def test_pending_file_does_not_rescan_all_files_for_backfill(rec, monkeypatch):
    files.add_file(rec, "sample.txt", b"sample", actor="engineer")

    def no_backfill(*args, **kwargs):
        raise AssertionError("pending queue must be used before scanning old files")

    monkeypatch.setattr(store, "seed", no_backfill)
    assert worker.step(rec)


def test_service_keeps_one_file_pass_across_open_projects(rec, tmp_path, monkeypatch):
    import threading
    from types import SimpleNamespace

    from qsone.records.mapping.service import Mapping
    from qsone.records.project import Records

    other = Records.create(tmp_path / "other", name="Sample", actor="engineer")
    first = files.add_file(rec, "sample.pdf", sample_pdf([[], []]), actor="engineer")
    second = files.add_file(other, "sample.pdf", sample_pdf([[], []]), actor="engineer")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda _: (Path("/fake"), "ara+eng"))
    monkeypatch.setattr(ocr, "read_image", lambda *a, **kw: ocr.Page([], True))
    reads = []
    original = files.read_original

    def counted(*args):
        reads.append(args[1])
        return original(*args)

    monkeypatch.setattr(files, "read_original", counted)
    done = set()
    finished = threading.Event()
    update = worker._update

    def observed(rec, file_id, fields, tables=None):
        update(rec, file_id, fields, tables)
        if fields.get("local_state") == "done":
            done.add(file_id)
            if len(done) == 2:
                finished.set()

    monkeypatch.setattr(worker, "_update", observed)
    service = Mapping(SimpleNamespace(opened=lambda: [(rec.id, rec), (other.id, other)]))
    try:
        service.start()
        assert finished.wait(5)
        assert reads == [first.id, second.id]
    finally:
        service.stop()
        other.close()


def test_no_ocr_languages_fails_with_bilingual_note(rec, monkeypatch):
    from qsone import copy

    monkeypatch.setattr(ocr, "find_tesseract", lambda: "fake")
    monkeypatch.setattr(ocr, "find_languages", lambda _: None)
    f = files.add_file(rec, "sample.pdf", sample_pdf([[]]), actor="engineer")
    drain(rec)
    row = store.detail(rec, f.id)
    assert row["local_state"] == "failed" and row["note"] == copy.OCR_TESSERACT_FAILED


def test_existing_exact_copy_reuses_local_map_without_reading(rec, monkeypatch):
    first = files.add_file(rec, "sample.txt", b"Sample conditions", actor="engineer")
    drain(rec)
    with rec.write("one") as c:
        c.execute(
            "INSERT INTO files(id,name,kind,size,sha256,status,added_at,added_by) "
            "SELECT 'copy','copy.txt',kind,size,sha256,status,added_at,added_by "
            "FROM files WHERE id=?",
            (first.id,),
        )
        store.enqueue(c, rec, "copy", "txt", None)
    monkeypatch.setattr(
        worker, "_structure", lambda *a: (_ for _ in ()).throw(AssertionError("copy read again"))
    )
    drain(rec)
    detail = store.detail(rec, "copy")
    assert detail["local_state"] == "done"
    assert detail["ai_state"] == "local"
    assert detail["structure"] == store.detail(rec, first.id)["structure"]


def test_ai_failure_is_not_resubmitted_until_wake(rec, monkeypatch):
    from concurrent.futures import Future
    from types import SimpleNamespace

    from qsone.records.mapping.service import Mapping

    f = files.add_file(rec, "sample.txt", b"Sample conditions", actor="engineer")
    other = files.add_file(rec, "other.txt", b"Sample other", actor="engineer")
    drain(rec)
    calls = []

    def completed(pid, pending):
        calls.append(pending)
        with rec.write("one") as c:
            store.write(c, rec, "map_files", {"file_id": other.id, "ai_state": "done"})
            store.write(c, rec, "map_files", {"file_id": f.id, "ai_state": "failed"})
        future = Future()
        future.set_result(False)
        return future

    service = Mapping(SimpleNamespace(opened=lambda: [(rec.id, rec)]), completed=completed)
    service._last_drop = 0
    monkeypatch.setattr("qsone.records.mapping.service.time.monotonic", lambda: 100)
    waits = []

    def wait(_):
        waits.append(1)
        if len(waits) == 3:
            service._quit.set()

    monkeypatch.setattr(service._wake, "wait", wait)
    service._work()
    assert len(calls) == 1 and set(calls[0]) == {f.id, other.id}
    service._quit.clear()
    waits.clear()
    service.wake()
    service._last_drop = 0
    service._work()
    assert len(calls) == 2 and calls[1] == [f.id]
