"""A tender folder comes in (Plan 8, Task 6): each file keeps its folder, a zip is opened in
memory with Arabic names, and a zip that is too big or unsafe is kept and not opened. Synthetic
«عينة» files only."""

import io
import zipfile
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.records import files, unzip
from qsone.records.files import add_file
from qsone.records.project import RecordsError
from tests.conftest import AUTH, SECRET
from tests.samples import sample_pdf, sample_xlsx, sample_zip

BOQ = sample_xlsx({"BOQ": [["03/02", "خرسانة", "م3", 1]]})


def test_folder_is_kept_with_the_file(rec):
    f = add_file(rec, "جدول الكميات - عينة.xlsx", BOQ, actor="engineer", folder="المناقصة/02 جداول")
    assert f.folder == "المناقصة/02 جداول"
    assert files.file_info(rec, f.id).folder == "المناقصة/02 جداول"
    assert [x.folder for x in files.list_files(rec)] == ["المناقصة/02 جداول"]


def test_a_folder_never_climbs_and_a_plain_file_has_none(rec):
    assert files.clean_folder("..\\المناقصة//./02 جداول/") == "المناقصة/02 جداول"
    assert files.clean_folder(" / ") is None
    assert add_file(rec, "عقد - عينة.txt", b"contract", actor="engineer").folder is None


def test_the_same_name_in_two_folders_is_two_files(rec):
    a = add_file(rec, "BOQ - عينة.txt", b"one", actor="engineer", folder="مبنى أ")
    b = add_file(rec, "BOQ - عينة.txt", b"two", actor="engineer", folder="مبنى ب")
    assert b.replaces is None and {f.id for f in files.list_files(rec)} == {a.id, b.id}
    c = add_file(rec, "BOQ - عينة.txt", b"three", actor="engineer", folder="مبنى أ")
    assert c.replaces == a.id  # a new version in the same folder


@pytest.mark.parametrize("encoding", ["cp720", "cp1256", None])
def test_zip_members_come_in_with_arabic_names(encoding):
    pdf = sample_pdf([["Specification"]])
    data = sample_zip({"مواصفات/عامة - عينة.pdf": pdf}, encoding=encoding)
    got = list(unzip.members("المناقصة.zip", data))
    assert [g[:2] for g in got] == [("المناقصة.zip/مواصفات", "عامة - عينة.pdf")]
    assert got[0][2] == pdf


def test_zip_bomb_is_refused():
    bomb = sample_zip({"a.txt": b"0" * 1_000_000})  # about 1000:1
    with pytest.raises(RecordsError) as e:
        list(unzip.members("x.zip", bomb))
    assert e.value.text is copy.ZIP_UNSAFE
    many = sample_zip({f"{i}.txt": str(i).encode() for i in range(5001)}, compression=0)
    with pytest.raises(RecordsError) as e:
        list(unzip.members("x.zip", many))
    assert e.value.text is copy.ZIP_UNSAFE


def test_a_member_never_climbs_out():
    data = sample_zip({"../../x - عينة.txt": b"x", "C:/y.txt": b"y"})
    assert [g[:2] for g in unzip.members("رسومات.zip", data)] == [
        ("رسومات.zip", "x - عينة.txt"),
        ("رسومات.zip", "y.txt"),
    ]


def test_too_big_in_all_and_too_big_a_member(monkeypatch):
    data = sample_zip({"a.txt": b"a" * 100, "b.txt": b"b" * 10}, compression=0)
    monkeypatch.setattr(unzip, "MAX_TOTAL", 50)
    with pytest.raises(RecordsError) as e:
        list(unzip.members("x.zip", data))
    assert e.value.text is copy.ZIP_TOO_BIG
    monkeypatch.setattr(unzip, "MAX_TOTAL", 1000)
    monkeypatch.setattr(unzip, "MAX_MEMBER", 50)
    assert [(n, b) for _, n, b in unzip.members("x.zip", data)] == [
        ("a.txt", None),
        ("b.txt", b"b" * 10),
    ]


def test_rar_is_kept_not_read(rec):
    f = add_file(rec, "رسومات - عينة.rar", b"Rar!\x1a\x07\x00 sample", actor="engineer")
    assert f.status == "stored" and f.note == "FILE_NOT_READ_YET"


# The upload route ----------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(create_app(SECRET, connectors=lambda: [])) as c:
        yield c


@pytest.fixture
def project(client) -> str:
    return client.post("/projects", json={"name": "مناقصة - عينة"}, headers=AUTH).json()["id"]


def upload(client, project: str, name: str, data: bytes, folder: str | None = None):
    url = f"/projects/{project}/files?name={quote(name)}"
    if folder is not None:
        url += f"&folder={quote(folder)}"
    return client.post(url, content=data, headers=AUTH)


def test_upload_with_folder_param(client, project):
    r = upload(client, project, "BOQ - عينة.xlsx", BOQ, folder="مناقصة/02 جداول")
    assert r.status_code == 201 and r.json()["folder"] == "مناقصة/02 جداول"
    listed = client.get(f"/projects/{project}/files", headers=AUTH).json()["files"]
    assert listed[0]["folder"] == "مناقصة/02 جداول"


def test_a_zip_answers_with_every_file_in_it(client, project):
    inner = sample_zip({"x.txt": b"inner"})
    data = sample_zip(
        {
            "مواصفات/عامة - عينة.txt": b"spec",
            "رسومات/قديم.zip": inner,  # a zip in a zip stays a file
            "فاضي.txt": b"",
        }
    )
    r = upload(client, project, "المناقصة.zip", data, folder="مناقصة")
    assert r.status_code == 201
    body = r.json()
    assert body["zip"] is True
    assert [(f["folder"], f["name"]) for f in body["files"]] == [
        ("مناقصة/المناقصة.zip/مواصفات", "عامة - عينة.txt"),
        ("مناقصة/المناقصة.zip/رسومات", "قديم.zip"),
    ]
    assert body["skipped"] == [
        {"name": "فاضي.txt", "folder": "مناقصة/المناقصة.zip", "error": copy.FILE_EMPTY}
    ]
    names = {
        f["name"] for f in client.get(f"/projects/{project}/files", headers=AUTH).json()["files"]
    }
    assert names == {"عامة - عينة.txt", "قديم.zip"}  # the opened zip itself is not kept


def test_an_unsafe_zip_is_kept_as_a_file_not_opened(client, project):
    bomb = sample_zip({"a.txt": b"0" * 1_000_000})
    r = upload(client, project, "مضغوط - عينة.zip", bomb)
    assert r.status_code == 201
    body = r.json()
    assert "zip" not in body and body["name"] == "مضغوط - عينة.zip"
    assert body["note"] == copy.ZIP_UNSAFE


def test_a_damaged_zip_is_kept_too(client, project):
    data = sample_zip({"a.txt": b"abc" * 100})
    broken = data[:40] + b"\x00" * 20 + data[60:]  # the member's packed bytes are hit
    if not zipfile.is_zipfile(io.BytesIO(broken)):
        pytest.skip("the damage hit the directory")
    r = upload(client, project, "تالف - عينة.zip", broken)
    assert r.status_code == 201 and r.json()["note"] == copy.ZIP_UNSAFE
