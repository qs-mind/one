"""The Backup routes of the HTTP contract (Plan 8, Task 4), over the bearer secret."""

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.backup import keys, store
from tests.conftest import AUTH, SECRET
from tests.samples import sample_xlsx

BOQ = "جدول الكميات - عينة.xlsx"


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


@pytest.fixture
def project(client):
    pid = client.post("/projects", json={"name": "برج - عينة"}, headers=AUTH).json()["id"]
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف", "م3", 120]]})
    r = client.post(f"/projects/{pid}/files", params={"name": BOQ}, content=data, headers=AUTH)
    assert r.status_code == 201
    return pid


def test_routes(client, project, tmp_path, data_dir, memory_keyring):
    usb = tmp_path / "usb"
    usb.mkdir()
    status = client.get("/backup", headers=AUTH).json()
    assert status["folder"] is None and status["reachable"] is False and status["note"] is None
    assert status["backup_key"] == {"local": True, "in_account": False, "code_saved": False}
    assert status["projects"] == [{"id": project, "last_backup": None, "confidential": False}]

    r = client.put("/backup/folder", json={"path": "not/absolute"}, headers=AUTH)
    assert r.status_code == 400 and r.json()["error"] == copy.BACKUP_FOLDER_NOT_WRITABLE
    status = client.put("/backup/folder", json={"path": str(usb)}, headers=AUTH).json()
    assert status["folder"] == str(usb) and status["reachable"] is True
    assert list(usb.iterdir()) == []  # the test file is gone

    assert client.post("/backup/run", headers=AUTH).json() == {"backed_up": 2}  # + engineer
    assert client.post("/backup/run", json={"project_id": project}, headers=AUTH).json() == {
        "backed_up": 0
    }
    assert client.get("/backup", headers=AUTH).json()["projects"][0]["last_backup"]

    r = client.post("/backup/recovery-code", headers=AUTH)
    code = r.json()["code"]
    assert r.headers["cache-control"] == "no-store"
    r = client.post("/backup/recovery-code/confirm", json={"last_group": "....."}, headers=AUTH)
    assert r.status_code == 400 and r.json()["error"] == copy.RECOVERY_LAST_GROUP_WRONG
    r = client.post("/backup/recovery-code/confirm", json={"last_group": code[-5:]}, headers=AUTH)
    assert r.json() == {"saved": True}
    assert client.get("/backup", headers=AUTH).json()["backup_key"]["code_saved"] is True
    assert (store.base(usb) / keys.BACKUP_KEY_FILE).is_file()

    r = client.put(f"/projects/{project}/confidential", json={"on": True}, headers=AUTH)
    secret_code = r.json()["code"]
    assert r.json()["confidential"] is True and r.headers["cache-control"] == "no-store"
    r = client.post(
        f"/projects/{project}/confidential/confirm", json={"last_group": "00000"}, headers=AUTH
    )
    assert r.status_code == 400 or secret_code.endswith("00000")
    r = client.post(
        f"/projects/{project}/confidential/confirm",
        json={"last_group": secret_code[-5:]},
        headers=AUTH,
    )
    assert r.json() == {"saved": True}
    assert client.get("/projects", headers=AUTH).json()["projects"][0]["confidential"] is True
    off = client.put(f"/projects/{project}/confidential", json={"on": False}, headers=AUTH)
    assert off.json() == {"confidential": False}

    found = client.get("/backup/found", params={"path": str(usb)}, headers=AUTH).json()
    by_id = {p["id"]: p for p in found["projects"]}
    assert by_id[project] == {
        "id": project,
        "name": "برج - عينة",
        "last_backup": by_id[project]["last_backup"],
        "needs": None,
    }
    assert "engineer" in by_id  # the Engineer Records travel too

    r = client.post("/backup/restore", json={"path": str(usb), "project_id": project}, headers=AUTH)
    assert r.json() == {"id": project, "name": "برج - عينة"}
    assert client.post(f"/projects/{project}/open", headers=AUTH).json()["name"] == "برج - عينة"
    hits = client.get(f"/projects/{project}/search", params={"q": "03/02"}, headers=AUTH).json()
    assert hits["results"]

    r = client.post(
        "/backup/restore", json={"path": str(usb), "project_id": "engineer"}, headers=AUTH
    )
    assert r.json() == {"id": "engineer", "name": "Engineer Records"}
    assert client.app.state.engine.engineer_records().is_open  # opened again when needed

    r = client.post("/backup/restore", json={"path": str(usb), "project_id": "../x"}, headers=AUTH)
    assert r.status_code == 404
    for word in ("خرسانة مسلحة", "03/02", "عينة", code, secret_code):
        assert word.encode() not in b"".join(p.read_bytes() for p in usb.rglob("*") if p.is_file())
        assert word not in (data_dir / "settings.json").read_text(encoding="utf-8")


def test_every_backup_route_needs_the_secret(client):
    for method, path in [
        ("get", "/backup"),
        ("put", "/backup/folder"),
        ("post", "/backup/run"),
        ("get", "/backup/found?path=/x"),
        ("post", "/backup/restore"),
        ("post", "/backup/recovery-code"),
        ("post", "/backup/recovery-code/confirm"),
    ]:
        assert getattr(client, method)(path).status_code == 401


def test_a_wrong_code_in_a_restore_is_plain_words(client, project, tmp_path):
    usb = tmp_path / "usb"
    usb.mkdir()
    client.put(f"/projects/{project}/confidential", json={"on": True}, headers=AUTH)
    client.put("/backup/folder", json={"path": str(usb)}, headers=AUTH)
    client.post("/backup/run", headers=AUTH)
    body = {"path": str(usb), "project_id": project, "code": keys.new_recovery_code()}
    r = client.post("/backup/restore", json=body, headers=AUTH)
    assert r.status_code == 400 and r.json() == {"error": copy.RECOVERY_CODE_WRONG}
