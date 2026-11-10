"""Lessons Learned as the engineer sees and edits them (Phase 1, C7; contract rows 3–5). A lesson
is removed by a mark, the Undo entry holds its id only, and Undo clears the mark. Synthetic «عينة»
data only."""

import json

import pytest
from fastapi.testclient import TestClient

from qsone import copy, settings
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import kit
from qsone.journey import closing
from qsone.records import ledger
from qsone.tools.lessons import KIND
from tests.conftest import AUTH, SECRET
from tests.test_engine_runner import links

WORDS = "Check the BOQ units before pricing - sample."


@pytest.fixture
def client(data_dir):
    with TestClient(create_app(SECRET, data_dir=data_dir, connectors=links)) as found:
        yield found


def engineer(client):
    return client.app.state.engine.engineer_records()


def add(client, text: str, **more) -> str:
    fields = {"text": text, "kind": "method", **more}
    return ledger.add_item(engineer(client), kind=KIND, actor="engineer", fields=fields)


def listed(client) -> list[dict]:
    answer = client.get("/engineer/lessons", headers=AUTH)
    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store"
    return c.Lessons.model_validate_json(answer.text, strict=True).model_dump()["lessons"]


def test_lessons_are_listed_newest_first_with_their_tender(client):
    pid = client.post("/projects", json={"name": "فيلا - عينة"}, headers=AUTH).json()["id"]
    older = add(client, "Older lesson - sample.", from_project=pid, from_lesson="a" * 32)
    gone = add(client, "From a removed tender - sample.", from_project="f" * 32)
    home = add(client, "Saved from Home - sample.")
    found = listed(client)
    assert [x["id"] for x in found] == [home, gone, older]
    assert (found[2]["from_project_id"], found[2]["from_project_name"]) == (pid, "فيلا - عينة")
    assert (found[1]["from_project_id"], found[1]["from_project_name"]) == ("f" * 32, None)
    assert (found[0]["from_project_id"], found[0]["from_project_name"]) == (None, None)


def test_a_lesson_is_edited_in_place(client):
    lesson_id = add(client, "Old words - sample.")
    answer = client.patch(
        f"/engineer/lessons/{lesson_id}", json={"text": f"  {WORDS} "}, headers=AUTH
    )
    assert answer.status_code == 200
    assert c.Lesson.model_validate_json(answer.text, strict=True).text == WORDS
    assert listed(client)[0]["text"] == WORDS

    empty = client.patch(f"/engineer/lessons/{lesson_id}", json={"text": "   "}, headers=AUTH)
    long = client.patch(f"/engineer/lessons/{lesson_id}", json={"text": "x" * 2001}, headers=AUTH)
    unknown = client.patch(f"/engineer/lessons/{'e' * 32}", json={"text": WORDS}, headers=AUTH)
    assert (empty.status_code, empty.json()) == (422, {"error": copy.LESSON_EMPTY, "field": "text"})
    assert (long.status_code, long.json()) == (
        422,
        {"error": copy.LESSON_TOO_LONG, "field": "text"},
    )
    assert (unknown.status_code, unknown.json()) == (404, {"error": copy.ENGINEER_LESSON_NOT_FOUND})
    assert listed(client)[0]["text"] == WORDS  # nothing changed


def test_a_removed_lesson_is_marked_and_undo_puts_it_back(client):
    lesson_id = add(client, WORDS)
    removed = client.delete(f"/engineer/lessons/{lesson_id}", headers=AUTH)
    assert removed.status_code == 200
    undo = c.Undoable.model_validate_json(removed.text, strict=True)
    assert listed(client) == []
    app = client.app.state
    assert WORDS not in kit.text(app.projects, app.engine, None)  # the Lead no longer gets it
    held = json.dumps(settings.load()["trash"], ensure_ascii=False)
    assert lesson_id in held and WORDS not in held  # the Undo entry holds the id only
    with engineer(client).read() as conn:  # never deleted: marked
        (fields,) = conn.execute("SELECT fields FROM items WHERE id = ?", (lesson_id,)).fetchone()
    assert json.loads(fields)["removed_at"]

    again = client.delete(f"/engineer/lessons/{lesson_id}", headers=AUTH)
    edit = client.patch(f"/engineer/lessons/{lesson_id}", json={"text": WORDS}, headers=AUTH)
    assert again.status_code == edit.status_code == 404

    assert client.post(f"/undo/{undo.undo}", headers=AUTH).status_code == 204
    assert [x["id"] for x in listed(client)] == [lesson_id]


def test_a_carried_lesson_removed_later_is_still_carried(client, rec):
    lesson_id = ledger.add_item(
        rec, kind=KIND, actor="lead", fields={"text": WORDS, "kind": "method"}
    )
    assert closing.carry(rec, engineer(client), lesson_id, carry=True)
    carried = listed(client)[0]["id"]
    assert client.delete(f"/engineer/lessons/{carried}", headers=AUTH).status_code == 200
    lessons = closing.checklist(rec, engineer(client))["lessons"]
    assert [x["carried"] for x in lessons] == [True]  # not offered again
