"""The Project Canvas in the core (Plan 7, Task 2): the layout, the project's status, and a PDF's
pages as images and text for its file frame. Synthetic «عينة» data only."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from qsone import canvas, copy
from qsone.app import create_app
from qsone.records import schema
from qsone.records.project import Records
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_sheet, sample_xlsx

D1 = "deliverable:d1"
FRAMES = [
    {"key": D1, "x": 120.5, "y": -40, "w": 960, "h": 640, "z": 2, "collapsed": False},
    {"key": "files:all", "x": -420, "y": 0, "w": 360, "h": 520, "z": 0, "collapsed": True},
]


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


@pytest.fixture
def project(client):
    return client.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]


def put_frames(client, project, frames, removed=()):
    body = {"frames": frames, "removed": list(removed)}
    return client.put(f"/projects/{project}/canvas/frames", json=body, headers=AUTH)


def layout(client, project) -> dict:
    return client.get(f"/projects/{project}/canvas", headers=AUTH).json()


def upload(client, project, name, data):
    r = client.post(f"/projects/{project}/files", params={"name": name}, content=data, headers=AUTH)
    assert r.status_code == 201
    return r.json()["id"]


def set_meta(client, project, **values):
    rec = client.app.state.projects.get(project)
    with rec.write("engineer") as conn:
        for key, value in values.items():
            rec.set_meta(conn, key, value)


# The layout --------------------------------------------------------------------------------------


def test_layout_round_trips_and_survives_a_restart(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as c:
        pid = c.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]
        assert layout(c, pid) == {"frames": [], "view": None, "client_boqs": []}
        r = put_frames(c, pid, FRAMES)
        assert r.status_code == 200 and r.json() == {"ok": True}
        view = {"x": -300, "y": 80, "zoom": 0.85}
        r = c.put(f"/projects/{pid}/canvas/view", json=view, headers=AUTH)
        assert r.status_code == 200 and r.json() == {"ok": True}
    with TestClient(create_app(SECRET, data_dir=data_dir)) as c:
        c.post(f"/projects/{pid}/open", headers=AUTH)
        got = layout(c, pid)
        assert sorted(f["key"] for f in got["frames"]) == ["deliverable:d1", "files:all"]
        assert {f["key"]: f for f in got["frames"]} == {f["key"]: f for f in FRAMES}
        assert got["view"] == {"x": -300, "y": 80, "zoom": 0.85}


def test_removed_frames_go(client, project):
    put_frames(client, project, FRAMES)
    assert put_frames(client, project, [], removed=["files:all"]).status_code == 200
    assert [f["key"] for f in layout(client, project)["frames"]] == [D1]


def test_upsert_keeps_one_row_per_key(client, project):
    put_frames(client, project, FRAMES[:1])
    moved = FRAMES[0] | {"x": 7.25, "y": 8, "collapsed": True}
    put_frames(client, project, [moved])
    frames = layout(client, project)["frames"]
    assert frames == [moved | {"x": 7.2}]  # one decimal


@pytest.mark.parametrize(
    "bad",
    [
        {"w": 0},
        {"h": 8001},
        {"x": float("inf")},
        {"y": float("nan")},
        {"x": 1_000_001},
        {"key": "../x"},
        {"key": "FILE:a"},
        {"key": "plan:a"},
        {"key": "file:" + "a" * 65},
        {"z": 1.5},
        {"collapsed": "yes"},
    ],
)
def test_bad_layout_is_refused_in_plain_words(client, project, bad):
    body = json.dumps({"frames": [FRAMES[1], FRAMES[0] | bad], "removed": []})  # Infinity, NaN
    r = client.put(f"/projects/{project}/canvas/frames", content=body, headers=AUTH)
    assert r.status_code == 422
    assert r.json()["error"] == copy.CANVAS_BAD_LAYOUT and r.json()["field"].startswith("frames.1")
    assert layout(client, project)["frames"] == []  # nothing stored


@pytest.mark.parametrize("view", [{"x": 0, "y": 0, "zoom": 0.05}, {"x": 0, "y": 0, "zoom": 3}])
def test_bad_view_is_refused(client, project, view):
    r = client.put(f"/projects/{project}/canvas/view", json=view, headers=AUTH)
    assert r.status_code == 422 and r.json() == {"error": copy.CANVAS_BAD_LAYOUT, "field": "zoom"}


def test_a_bad_removed_key_is_refused(client, project):
    r = put_frames(client, project, [], removed=["../etc"])
    assert r.status_code == 422 and r.json()["field"] == "removed.0"


def test_too_many_frames(client, project):
    many = [FRAMES[0] | {"key": f"file:f{i}"} for i in range(canvas.MAX_FRAMES + 1)]
    r = put_frames(client, project, many)
    assert r.status_code == 422 and r.json()["error"] == copy.CANVAS_BAD_LAYOUT
    assert r.json()["field"] == "frames"


def test_layout_needs_an_open_project(client, project):
    client.post(f"/projects/{project}/close", headers=AUTH)
    for r in (
        client.get(f"/projects/{project}/canvas", headers=AUTH),
        put_frames(client, project, FRAMES),
        client.get(f"/projects/{project}/status", headers=AUTH),
    ):
        assert r.status_code == 409 and r.json()["error"] == copy.PROJECT_NOT_OPEN


def test_layout_not_readable_on_disk(client, project, data_dir):
    put_frames(client, project, FRAMES)
    client.post(f"/projects/{project}/close", headers=AUTH)
    for path in data_dir.rglob("*"):
        if path.is_file():
            assert b"deliverable:d1" not in path.read_bytes(), path


def test_project_responses_are_never_cached(client, project):
    for path in [
        f"/projects/{project}/canvas",
        f"/projects/{project}/files",
        f"/projects/{project}/status",
        "/projects",
        "/chat/general/messages",
    ]:
        assert client.get(path, headers=AUTH).headers["cache-control"] == "no-store", path
    assert "no-store" not in client.get("/health", headers=AUTH).headers.get("cache-control", "")


def test_layout_writes_leave_no_audit_row(client, project):
    put_frames(client, project, FRAMES)
    rec = client.app.state.projects.get(project)
    with rec.read() as conn:
        tables = [t for (t,) in conn.execute("SELECT table_name FROM audit")]
    assert "canvas_frames" not in tables


# The status --------------------------------------------------------------------------------------


def test_status_has_only_what_is_known(client, project, monkeypatch):
    assert client.get(f"/projects/{project}/status", headers=AUTH).json() == {}
    today = date(2026, 11, 4)
    monkeypatch.setattr(canvas, "today", lambda: today)
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


def test_migration_adds_canvas_tables_and_keeps_data(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "MIGRATIONS", schema.MIGRATIONS[:1])
    rec = Records.create(tmp_path / "p", name="عينة", actor="engineer")
    with rec.write("engineer") as conn:
        conn.execute(
            "INSERT INTO items(id, kind, code, created_at, created_by, updated_at, updated_by)"
            " VALUES ('i1', 'boq', '03/02', 't', 'e', 't', 'e')"
        )
    rec.close()
    monkeypatch.undo()
    rec = Records.open(tmp_path / "p")
    try:
        with rec.read() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == len(schema.MIGRATIONS)
            assert conn.execute("SELECT code FROM items").fetchall() == [("03/02",)]
            assert conn.execute("SELECT count(*) FROM canvas_frames").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM canvas_view").fetchone() == (0,)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(briefs)")]
            assert "selection" in columns
    finally:
        rec.close()
