"""Undo after an accept: the Deliverable goes back to the version before it, by new entries (nothing
is edited or deleted), and the changes it held wait again (synthetic «عينة» data only)."""

import pytest
from fastapi.testclient import TestClient

from qsone import copy
from qsone.app import create_app
from qsone.deliverables import revert
from qsone.deliverables.changes import accept, list_changes, pending, propose
from qsone.deliverables.store import view
from qsone.records import ledger
from qsone.records.project import RecordsError
from tests.conftest import AUTH, SECRET
from tests.samples import sample_sheet, sample_source


def row_by_code_in(v: dict, code: str) -> dict:
    return next(r for r in v["rows"] if r.get("code") == code)


def shown(v: dict) -> dict:
    """What the engineer sees: each row's name and cell values, the columns and the total; not
    the ids the ledger gives each new entry."""

    def value(cell):
        if cell is None:
            return None
        return cell.get("value", cell.get("text"))

    return {
        "columns": [c["key"] for c in v["columns"]],
        "rows": [
            (r.get("code") or r["title"], {k: value(c) for k, c in r["cells"].items()})
            for r in v["rows"]
        ],
        "total": value(v["total"]),
    }


def set_number(row: dict, name: str, value: str, **extra) -> dict:
    cell = row["cells"].get(name)
    expect = cell.get("number_id") if isinstance(cell, dict) else None
    return {"op": "set_number", "row": row["id"], "name": name, "value": value, "expect": expect}


def test_undo_one_accepted_change_restores_the_version_before(rec):
    d = sample_sheet(rec)
    before = view(rec, d)
    row = row_by_code_in(before, "03/02")
    [ch] = propose(
        rec, d, [{**set_number(row, "rate", "40000.00"), "source_id": sample_source(rec)}],
        actor="lead_qs",
    )  # fmt: skip
    assert accept(rec, d, [ch.id], actor="engineer")["version"] == 2
    assert row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["value"] == "40000.00"

    out = revert.undo_accept(rec, d, 2, actor="engineer")
    assert out == {"version": 3, "pending": [ch.id]}
    now = view(rec, d)
    assert now["version"] == 3 and shown(now) == shown(before)
    assert now["total"]["value"] == before["total"]["value"]
    # the change waits again, and can be accepted again: nothing it was made against is stale
    [again] = pending(rec, d)
    assert again.id == ch.id and again.status == "pending" and again.version_n is None
    assert accept(rec, d, [ch.id], actor="engineer")["accepted"] == [ch.id]
    assert row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["value"] == "40000.00"


def test_undo_writes_new_entries_and_keeps_history(rec):
    d = sample_sheet(rec)
    row = row_by_code_in(view(rec, d), "03/02")
    old_rate = row["cells"]["rate"]["number_id"]
    [ch] = propose(rec, d, [set_number(row, "rate", "40000.00")], actor="engineer")
    accept(rec, d, [ch.id], actor="engineer")
    revert.undo_accept(rec, d, 2, actor="engineer")
    with rec.read() as c:
        rates = c.execute(
            "select value, valid_until is null, reason from numbers where item_id = ?"
            " and name = 'rate' order by recorded_at, rowid",
            (row["item_id"],),
        ).fetchall()
        actions = {
            a for (a,) in c.execute("select action from audit where table_name = 'versions'")
        }
    # the first entry, the accepted one, and the undo's: each kept, only the last current
    assert [(v, current) for v, current, _ in rates] == [
        ("39850.50", False),
        ("40000.00", False),
        ("39850.50", True),
    ]
    assert rates[-1][2] == copy.fill(copy.UNDO_ACCEPT_REASON, title="جدول الكميات - عينة")["ar"]
    assert actions == {"create"}
    assert view(rec, d, version=2)["version"] == 2  # the undone version is still there to compare
    assert row_by_code_in(view(rec, d, version=2), "03/02")["cells"]["rate"]["value"] == "40000.00"
    assert row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["number_id"] != old_rate


def test_undo_accept_all_of_many_kinds(rec):
    d = sample_sheet(rec)
    before = view(rec, d)
    concrete = row_by_code_in(before, "03/02")
    rate_only = row_by_code_in(before, "2-4")  # a rate and no quantity: a new number
    gone = row_by_code_in(before, "1-2")
    moved = row_by_code_in(before, "2-3")
    ops_ = [
        set_number(concrete, "rate", "41000"),
        set_number(rate_only, "quantity", "10"),
        {
            "op": "set_field",
            "row": concrete["id"],
            "key": "description",
            "value": "خرسانة - عينة معدلة",
        },
        {"op": "remove_row", "row": gone["id"]},
        {"op": "move_row", "row": moved["id"], "after": None},
        {"op": "add_section", "after": None, "title": "أعمال تمهيدية - عينة", "level": 1},
    ]
    made = propose(rec, d, ops_, actor="engineer")
    out = accept(rec, d, [c.id for c in made], actor="engineer")
    assert out["version"] == 2 and len(out["accepted"]) == len(ops_)
    assert shown(view(rec, d)) != shown(before)

    undone = revert.undo_accept(rec, d, 2, actor="engineer")
    assert undone["version"] == 3 and set(undone["pending"]) == {c.id for c in made}
    assert shown(view(rec, d)) == shown(before)  # the new quantity is gone: «فئة فقط» again
    # accepted again, every one of them still applies
    again = accept(rec, d, [c.id for c in made], actor="engineer")
    assert again["stale"] == [] and len(again["accepted"]) == len(ops_)


def test_undo_of_a_columns_change(rec):
    d = sample_sheet(rec)
    before = view(rec, d)
    columns = [
        {"key": "code", "label": {"en": "Item", "ar": "البند"}, "from": "code", "frozen": True},
        {"key": "rate", "label": {"en": "Rate", "ar": "الفئة"}, "from": "number:rate"},
    ]
    [ch] = propose(rec, d, [{"op": "set_columns", "columns": columns}], actor="lead_qs")
    accept(rec, d, [ch.id], actor="engineer")
    assert [c["key"] for c in view(rec, d)["columns"]] == ["code", "rate"]
    revert.undo_accept(rec, d, 2, actor="engineer")
    assert [c["key"] for c in view(rec, d)["columns"]] == [c["key"] for c in before["columns"]]
    assert accept(rec, d, [ch.id], actor="engineer")["stale"] == []


def test_too_late_once_anything_moved_since(rec):
    d = sample_sheet(rec)
    row = row_by_code_in(view(rec, d), "03/02")
    [ch] = propose(rec, d, [set_number(row, "rate", "40000")], actor="engineer")
    accept(rec, d, [ch.id], actor="engineer")
    # Project Records corrected the same number after the accept
    now = row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["number_id"]
    ledger.correct_number(
        rec, now, value="40500", reason="عرض جديد - عينة", source_id=sample_source(rec),
        dated="2026-11-04", actor="estimator",
    )  # fmt: skip
    with pytest.raises(RecordsError) as e:
        revert.undo_accept(rec, d, 2, actor="engineer")
    assert e.value.text == copy.UNDO_TOO_LATE and e.value.status == 409


def test_too_late_after_another_version(rec):
    d = sample_sheet(rec)
    v = view(rec, d)
    [a] = propose(
        rec, d, [set_number(row_by_code_in(v, "03/02"), "rate", "40000")], actor="engineer"
    )
    accept(rec, d, [a.id], actor="engineer")
    [b] = propose(rec, d, [set_number(row_by_code_in(v, "2-1"), "rate", "2700")], actor="engineer")
    accept(rec, d, [b.id], actor="engineer")
    with pytest.raises(RecordsError) as e:
        revert.undo_accept(rec, d, 2, actor="engineer")
    assert e.value.text == copy.UNDO_TOO_LATE
    assert revert.undo_accept(rec, d, 3, actor="engineer")["pending"] == [b.id]


def test_an_update_from_project_records_is_not_undone_here(rec):
    d = sample_sheet(rec)
    number = row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["number_id"]
    ledger.correct_number(
        rec, number, value="40500", reason="عرض جديد - عينة", source_id=sample_source(rec),
        dated="2026-11-04", actor="estimator",
    )  # fmt: skip
    [update] = pending(rec, d)
    accept(rec, d, [update.id], actor="engineer")
    assert not revert.undoable(rec, d, 2)
    with pytest.raises(RecordsError) as e:
        revert.undo_accept(rec, d, 2, actor="engineer")
    assert e.value.text == copy.UNDO_RECORDS


def test_only_the_engineer_undoes_and_only_an_accept(rec):
    d = sample_sheet(rec)
    assert not revert.undoable(rec, d, 1)  # version 1 was made, not accepted
    with pytest.raises(RecordsError) as e:
        revert.undo_accept(rec, d, 1, actor="engineer")
    assert e.value.text == copy.UNDO_TOO_LATE
    row = row_by_code_in(view(rec, d), "03/02")
    [ch] = propose(rec, d, [set_number(row, "rate", "40000")], actor="engineer")
    accept(rec, d, [ch.id], actor="engineer")
    assert revert.undoable(rec, d, 2)
    with pytest.raises(ValueError):
        revert.undo_accept(rec, d, 2, actor="lead_qs")
    revert.undo_accept(rec, d, 2, actor="engineer")
    assert [c.status for c in list_changes(rec, d)] == ["pending"]


# Through the core API: the accept answers an Undo token, as a removal does -------------------


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        yield client


def test_the_accept_answers_an_undo_and_undo_puts_the_version_back(client):
    project = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    d = sample_sheet(rec)
    path = f"/projects/{project}/deliverables/{d}"
    before = client.get(path, headers=AUTH).json()
    row = row_by_code_in(before, "03/02")
    [ch] = propose(rec, d, [set_number(row, "rate", "40000")], actor="engineer")

    answer = client.post(f"{path}/changes/accept", json={"ids": [ch.id]}, headers=AUTH).json()
    assert answer["version"] == 2 and answer["accepted"] == [ch.id]
    assert answer["window_ms"] == 6000 and len(answer["undo"]) == 32

    assert client.post(f"/undo/{answer['undo']}", headers=AUTH).status_code == 204
    now = client.get(path, headers=AUTH).json()
    assert now["version"] == 3 and shown(now) == shown(before) and now["pending"] == 1
    gone = client.post(f"/undo/{answer['undo']}", headers=AUTH)
    assert gone.status_code == 404  # once only


def test_the_reject_answers_an_undo_and_undo_makes_the_change_wait_again(client):
    """Tender day: after Reject there was no Undo. A reject is taken back like an accept: the
    change waits again, once only, and nothing else moved."""
    project = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    d = sample_sheet(rec)
    path = f"/projects/{project}/deliverables/{d}"
    before = client.get(path, headers=AUTH).json()
    [ch] = propose(rec, d, [set_number(row_by_code_in(before, "03/02"), "rate", "40000")], actor="engineer")

    answer = client.post(f"{path}/changes/reject", json={"ids": [ch.id]}, headers=AUTH).json()
    assert answer["rejected"] == [ch.id]
    assert answer["window_ms"] == 6000 and len(answer["undo"]) == 32
    assert [c.status for c in list_changes(rec, d)] == ["rejected"]

    assert client.post(f"/undo/{answer['undo']}", headers=AUTH).status_code == 204
    assert [c.id for c in pending(rec, d)] == [ch.id]
    now = client.get(path, headers=AUTH).json()
    assert now["version"] == before["version"] and shown(now) == shown(before) and now["pending"] == 1
    assert client.post(f"/undo/{answer['undo']}", headers=AUTH).status_code == 404  # once only


def test_an_undo_that_comes_too_late_says_why(client):
    project = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    d = sample_sheet(rec)
    path = f"/projects/{project}/deliverables/{d}"
    v = client.get(path, headers=AUTH).json()
    [a] = propose(
        rec, d, [set_number(row_by_code_in(v, "03/02"), "rate", "40000")], actor="engineer"
    )
    first = client.post(f"{path}/changes/accept", json={"ids": [a.id]}, headers=AUTH).json()
    [b] = propose(rec, d, [set_number(row_by_code_in(v, "2-1"), "rate", "2700")], actor="engineer")
    client.post(f"{path}/changes/accept", json={"ids": [b.id]}, headers=AUTH)
    late = client.post(f"/undo/{first['undo']}", headers=AUTH)
    assert late.status_code == 409 and late.json()["error"] == copy.UNDO_TOO_LATE


def test_an_accepted_update_from_project_records_answers_no_undo(client):
    project = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    d = sample_sheet(rec)
    path = f"/projects/{project}/deliverables/{d}"
    number = row_by_code_in(view(rec, d), "03/02")["cells"]["rate"]["number_id"]
    ledger.correct_number(
        rec, number, value="40500", reason="عرض جديد - عينة", source_id=sample_source(rec),
        dated="2026-11-04", actor="estimator",
    )  # fmt: skip
    [update] = pending(rec, d)
    answer = client.post(f"{path}/changes/accept", json={"ids": [update.id]}, headers=AUTH).json()
    assert answer["version"] == 2 and "undo" not in answer


def test_a_change_names_the_source_of_its_new_number(client):
    project = client.post("/projects", json={"name": "مدرسة - عينة"}, headers=AUTH).json()["id"]
    rec = client.app.state.projects.get(project)
    d = sample_sheet(rec)
    path = f"/projects/{project}/deliverables/{d}"
    v = view(rec, d)
    source = sample_source(rec)
    agent = {**set_number(row_by_code_in(v, "03/02"), "rate", "40000"), "source_id": source}
    propose(rec, d, [agent], actor="lead_qs")
    propose(rec, d, [set_number(row_by_code_in(v, "2-1"), "rate", "2700")], actor="engineer")
    listed = client.get(f"{path}/changes", params={"status": "pending"}, headers=AUTH).json()
    sourced, typed = listed["changes"]
    assert sourced["after"]["source"] == source and sourced["sources"][source]["kind"] == "sample"
    assert typed["after"]["source"] is None  # the engineer's own: its source comes with the accept
