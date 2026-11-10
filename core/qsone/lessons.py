"""Lessons Learned as the engineer sees and edits them (Phase 1, C7; contract rows 3–5).

A lesson is an item of kind `lesson` in Engineer Records: carried from a tender at close-out
(`journey/closing.carry`: `from_project`, `from_lesson`), or saved by the Lead from Home (no
`from_project`). Items are never deleted there, so removing one sets `removed_at` on it: it is
no longer listed and the Lead's kit leaves it out. The Undo entry holds the lesson's id only,
never its words (the Undo list is plain settings.json; the lesson is in the encrypted file), and
Undo clears the mark. `closing.checklist` still counts a removed lesson as carried, so it is not
offered again."""

import json
from collections.abc import Collection

from qsone import copy
from qsone.records import ledger
from qsone.records.project import Records, RecordsError
from qsone.tools.lessons import KIND

ENGINEER = "engineer"
REMOVED = "removed_at"
TOO_LONG = 2000  # characters, as note_lesson takes


def _found(engineer: Records, lesson_id: str) -> dict | None:
    """The lesson's item, removed or not."""
    with engineer.read() as conn:
        row = conn.execute(
            "SELECT fields, created_at FROM items WHERE id = ? AND kind = ?", (lesson_id, KIND)
        ).fetchone()
    return None if row is None else {"id": lesson_id, "fields": json.loads(row[0]), "at": row[1]}


def _lesson(found: dict, names: dict[str, str]) -> dict:
    project = found["fields"].get("from_project")
    return {
        "id": found["id"],
        "text": found["fields"]["text"],
        "from_project_id": project,
        "from_project_name": names.get(project) if project else None,
        "at": found["at"],
    }


def kept(engineer: Records, hidden: Collection[str] = ()) -> list[dict]:
    """The lessons that are not removed, newest first, as {"id", "fields", "at"}; none carried
    from a project in `hidden` (a Confidential one: it may have been marked so after)."""
    with engineer.read() as conn:
        rows = conn.execute(
            "SELECT id, fields, created_at FROM items WHERE kind = ?"
            " ORDER BY created_at DESC, rowid DESC",
            (KIND,),
        ).fetchall()
    found = [{"id": i, "fields": json.loads(f), "at": at} for i, f, at in rows]
    return [
        x
        for x in found
        if not x["fields"].get(REMOVED) and x["fields"].get("from_project") not in hidden
    ]


def listed(engineer: Records, names: dict[str, str], hidden: Collection[str] = ()) -> list[dict]:
    """`Lesson`s as JSON, newest first. `names`: each readable project's name, by id; `hidden`:
    the Confidential projects, whose lessons are not listed."""
    return [_lesson(x, names) for x in kept(engineer, hidden)]


def _current(engineer: Records, lesson_id: str) -> dict:
    found = _found(engineer, lesson_id)
    if found is None or found["fields"].get(REMOVED):
        raise RecordsError(copy.ENGINEER_LESSON_NOT_FOUND, status=404)
    return found


def edit(engineer: Records, lesson_id: str, text: str, names: dict[str, str]) -> dict:
    """The lesson with its new words. Raises `RecordsError`: ENGINEER_LESSON_NOT_FOUND (404),
    LESSON_EMPTY or LESSON_TOO_LONG (422, field "text")."""
    found = _current(engineer, lesson_id)
    if not text:
        raise RecordsError(copy.LESSON_EMPTY, status=422, field="text")
    if len(text) > TOO_LONG:
        raise RecordsError(copy.LESSON_TOO_LONG, status=422, field="text")
    if text != found["fields"]["text"]:
        found["fields"] = found["fields"] | {"text": text}
        ledger.update_item(engineer, lesson_id, fields=found["fields"], actor=ENGINEER)
    return _lesson(found, names)


def remove(engineer: Records, lesson_id: str) -> None:
    """Marks the lesson removed. Raises `RecordsError` ENGINEER_LESSON_NOT_FOUND (404)."""
    found = _current(engineer, lesson_id)
    fields = found["fields"] | {REMOVED: engineer.clock()}
    ledger.update_item(engineer, lesson_id, fields=fields, actor=ENGINEER)


def put_back(engineer: Records, lesson_id: str) -> bool:
    """Clears the mark (Undo); False when no such lesson is kept."""
    found = _found(engineer, lesson_id)
    if found is None:
        return False
    if REMOVED in found["fields"]:
        fields = {k: v for k, v in found["fields"].items() if k != REMOVED}
        ledger.update_item(engineer, lesson_id, fields=fields, actor=ENGINEER)
    return True
