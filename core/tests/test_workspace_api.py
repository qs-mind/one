"""The workspace in the core (Workspace plan, Task 2): the project's open document, its status,
and a PDF's pages as images and text. Synthetic «عينة» data only."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from qsone import copy, workspace
from qsone.app import create_app
from qsone.records import schema
from qsone.records.project import Records
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_sheet, sample_xlsx


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


@pytest.fixture
def project(client):
    return client.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]


def put_open(client, project, body):
    return client.put(f"/projects/{project}/workspace", json=body, headers=AUTH)


def workspace_of(client, project) -> dict:
    return client.get(f"/projects/{project}/workspace", headers=AUTH).json()


def upload(client, project, name, data):
    r = client.post(f"/projects/{project}/files", params={"name": name}, content=data, headers=AUTH)
    assert r.status_code == 201
    return r.json()["id"]


def set_meta(client, project, **values):
    rec = client.app.state.projects.get(project)
    with rec.write("engineer") as conn:
        for key, value in values.items():
            rec.set_meta(conn, key, value)


# The open document -------------------------------------------------------------------------------


def test_open_document_round_trips(client, project):
    body = {"open": "deliverable:abc", "anchor": {"row": "3/02"}}
    r = put_open(client, project, body)
    assert r.status_code == 200 and r.json() == {"ok": True}
    got = workspace_of(client, project)
    assert got["open"] == "deliverable:abc" and got["anchor"] == {"row": "3/02"}
    assert got["client_boqs"] == []


def test_open_document_survives_a_restart(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as c:
        pid = c.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]
        put_open(c, pid, {"open": "file:f1", "anchor": None})
    with TestClient(create_app(SECRET, data_dir=data_dir)) as c:
        c.post(f"/projects/{pid}/open", headers=AUTH)
        got = workspace_of(c, pid)
        assert got["open"] == "file:f1" and got["anchor"] is None


def test_nothing_open_is_null(client, project):
    got = workspace_of(client, project)
    assert got["open"] is None and got["anchor"] is None


def test_a_later_save_replaces_the_earlier(client, project):
    put_open(client, project, {"open": "files:all", "anchor": {"page": 2}})
    put_open(client, project, {"open": "clientboq:f2", "anchor": None})
    got = workspace_of(client, project)
    assert got["open"] == "clientboq:f2" and got["anchor"] is None


def test_unknown_key_is_refused(client, project):
    r = put_open(client, project, {"open": "desk:x"})
    assert r.status_code == 422
    assert r.json() == {"error": copy.WORKSPACE_BAD, "field": "open"}
    assert workspace_of(client, project)["open"] is None


@pytest.mark.parametrize(
    "bad", ["", "FILE:a", "files:other", "file:", "file:" + "a" * 65, "../x", "file:a/b", None]
)
def test_bad_keys_are_refused(client, project, bad):
    r = put_open(client, project, {"open": bad, "anchor": None})
    assert r.status_code == 422 and r.json()["field"] == "open"


@pytest.mark.parametrize("bad", [[1], "row", 3, {"note": "x" * 2100}])
def test_bad_anchor_is_refused(client, project, bad):
    r = put_open(client, project, {"open": "files:all", "anchor": bad})
    assert r.status_code == 422
    assert r.json() == {"error": copy.WORKSPACE_BAD, "field": "anchor"}


def test_missing_open_is_refused(client, project):
    r = put_open(client, project, {"anchor": None})
    assert r.status_code == 422 and r.json()["field"] == "open"


def test_canvas_routes_are_gone(client, project):
    assert client.get(f"/projects/{project}/canvas", headers=AUTH).status_code == 404
    assert client.put(f"/projects/{project}/canvas/view", json={}, headers=AUTH).status_code == 404


def test_workspace_needs_an_open_project(client, project):
    client.post(f"/projects/{project}/close", headers=AUTH)
    for r in (
        client.get(f"/projects/{project}/workspace", headers=AUTH),
        put_open(client, project, {"open": "files:all", "anchor": None}),
        client.get(f"/projects/{project}/status", headers=AUTH),
    ):
        assert r.status_code == 409 and r.json()["error"] == copy.PROJECT_NOT_OPEN


def test_open_document_not_readable_on_disk(client, project, data_dir):
    put_open(client, project, {"open": "deliverable:secretname", "anchor": None})
    client.post(f"/projects/{project}/close", headers=AUTH)
    for path in data_dir.rglob("*"):
        if path.is_file():
            assert b"deliverable:secretname" not in path.read_bytes(), path


def test_project_responses_are_never_cached(client, project):
    for path in [
        f"/projects/{project}/workspace",
        f"/projects/{project}/files",
        f"/projects/{project}/status",
        "/projects",
        "/chat/general/messages",
    ]:
        assert client.get(path, headers=AUTH).headers["cache-control"] == "no-store", path
    assert "no-store" not in client.get("/health", headers=AUTH).headers.get("cache-control", "")


def test_saving_the_open_document_leaves_no_audit_row(client, project):
    put_open(client, project, {"open": "files:all", "anchor": None})
    rec = client.app.state.projects.get(project)
    with rec.read() as conn:
        tables = [t for (t,) in conn.execute("SELECT table_name FROM audit")]
    assert "workspace" not in tables


# The status --------------------------------------------------------------------------------------


def test_status_has_only_what_is_known(client, project, monkeypatch):
    assert client.get(f"/projects/{project}/status", headers=AUTH).json() == {}
    today = date(2026, 11, 4)
    monkeypatch.setattr(workspace, "today", lambda: today)
    due = (today + timedelta(days=14)).isoformat()
    stage = {"en": "Tender", "ar": "مناقصة"}
    set_meta(client, project, submission_date=due, stage=json.dumps(stage, ensure_ascii=False))
    got = client.get(f"/projects/{project}/status", headers=AUTH).json()
    assert got == {"submission_date": due, "days_left": 14, "stage": stage}


def test_status_names_the_boq_value_by_its_deliverable(client, project):
    d = sample_sheet(client.app.state.projects.get(project))
    got = client.get(f"/projects/{project}/status", headers=AUTH).json()
    assert got == {
        "boq_value": {
            "value": "5182755.00",
            "currency": "EGP",
            "deliverable_id": d,
            "revision": None,
            "status": "draft",
            "sample": True,  # the sample sheet's rates come from a sample source
            "items": 6,  # what the total covers: the Sheet's items (no client BOQ imported here)
        }
    }


def test_the_boq_value_says_how_much_of_the_clients_boq_it_covers(client, project):
    """Tender day: «المقايسة لحد دلوقتي 1.4 مليون» came from a 4-row draft of a 325-item BOQ."""
    from qsone.records import ledger

    rec = client.app.state.projects.get(project)
    for n, import_id in enumerate(["old", "new", "new", "new", "new"]):  # the newest import counts
        ledger.add_item(rec, kind="boq_item", actor="lead_qs", code=f"9-{n}",
                        fields={"description": "بند - عينة", "import_id": import_id})  # fmt: skip
    sample_sheet(rec)
    boq = client.get(f"/projects/{project}/status", headers=AUTH).json()["boq_value"]
    assert (boq["items"], boq["of"]) == (6, 4)


def test_status_skips_what_does_not_read(client, project):
    set_meta(client, project, submission_date="18 Nov", stage="Tender")
    assert client.get(f"/projects/{project}/status", headers=AUTH).json() == {}


# File pages and text -----------------------------------------------------------------------------


def test_pages_and_text_of_a_pdf(client, project):
    fid = upload(client, project, "مواصفات - عينة.pdf", sample_pdf([["Page one"], ["Page two"]]))
    base = f"/projects/{project}/files/{fid}"
    assert client.get(f"{base}/pages", headers=AUTH).json() == {"pages": 2}
    pieces = client.get(f"{base}/text", params={"page": 2}, headers=AUTH).json()["pieces"]
    assert pieces == [{"locator": {"page": 2}, "text": "Page two"}]
    everything = client.get(f"{base}/text", headers=AUTH).json()["pieces"]
    assert [p["locator"]["page"] for p in everything] == [1, 2]


def test_text_of_a_sheet_keeps_sheet_and_row(client, project):
    data = sample_xlsx({"BOQ": [["Code", "Item"], ["3/02", "خرسانة - عينة"]]})
    fid = upload(client, project, "مقايسة - عينة.xlsx", data)
    base = f"/projects/{project}/files/{fid}"
    assert client.get(f"{base}/pages", headers=AUTH).json() == {"pages": 0}
    pieces = client.get(f"{base}/text", headers=AUTH).json()["pieces"]
    assert any(p["locator"].get("sheet") == "BOQ" and "خرسانة" in p["text"] for p in pieces)


def test_unknown_file(client, project):
    nowhere = "0" * 32
    for path in ("pages", "text", "pages/1"):
        r = client.get(f"/projects/{project}/files/{nowhere}/{path}", headers=AUTH)
        assert r.status_code == 404 and r.json() == {"error": copy.FILE_NOT_FOUND, "field": "file"}


# The migration -----------------------------------------------------------------------------------


def test_migration_drops_canvas_tables(tmp_path, monkeypatch):
    before = schema.MIGRATIONS.index(schema.WORKSPACE_SQL)
    monkeypatch.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:before])
    rec = Records.create(tmp_path / "p", name="عينة", actor="engineer")
    with rec.write("engineer") as conn:
        conn.execute(
            "INSERT INTO items(id, kind, code, created_at, created_by, updated_at, updated_by)"
            " VALUES ('i1', 'boq', '03/02', 't', 'e', 't', 'e')"
        )
        conn.execute(
            "INSERT INTO canvas_frames(key, x, y, w, h, updated_at)"
            " VALUES ('files:all', 0, 0, 300, 200, 't')"
        )
    rec.close()
    monkeypatch.undo()
    rec = Records.open(tmp_path / "p")
    try:
        with rec.read() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == len(schema.MIGRATIONS)
            assert conn.execute("SELECT code FROM items").fetchall() == [("03/02",)]
            tables = {t for (t,) in conn.execute("SELECT name FROM sqlite_master")}
            assert "canvas_frames" not in tables and "canvas_view" not in tables
            assert conn.execute("SELECT count(*) FROM workspace").fetchone() == (0,)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(briefs)")]
            assert "selection" in columns
    finally:
        rec.close()
