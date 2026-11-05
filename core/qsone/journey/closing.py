"""Close a project and archive it (Plan 8, Task 7).

The checklist never blocks: open comments and Deliverables not signed off are listed, and the
engineer may archive anyway; the archive's audit row keeps what was open. One proposes Lessons
Learned about method and corrections only (decisions §5); the engineer carries them to Engineer
Records one at a time. A Confidential Project shares nothing, so it has no lessons to carry.

Archiving sets `meta.archived_at` first and then takes the final backup, so the backup holds the
archived project and the next timer run has nothing new to copy. If the backup is not made, the
project is archived all the same and the answer says so."""

import json

from qsone import copy, usage
from qsone.backup.runner import Backups
from qsone.deliverables import store
from qsone.journey import setup_state, understand
from qsone.records import audit, ledger
from qsone.records.project import Records, RecordsError
from qsone.tools.lessons import KIND as LESSON

ENGINEER = "engineer"
ARCHIVED = "archived_at"

INSTRUCTION = """Close-out. Look back over this project: the engineer's corrections, the \
checks that caught a mistake, and the methods that worked. For each lesson worth keeping for the \
engineer's next projects, call note_lesson with kind method or correction. Write only how the work \
is done, never the client, the project's name, its places, prices or people: a lesson may go to \
every project. Skip a lesson already noted. Then say in one line how many you noted."""


def _confidential(rec: Records) -> bool:
    return rec.meta().get("confidential") == "1"


def _carried(engineer: Records, project_id: str) -> set[str]:
    """The ids of this project's lessons already in Engineer Records."""
    with engineer.read() as conn:
        rows = conn.execute(
            "SELECT json_extract(fields, '$.from_lesson') FROM items WHERE kind = ?"
            " AND json_extract(fields, '$.from_project') = ?",
            (LESSON, project_id),
        ).fetchall()
    return {r[0] for r in rows}


def _lessons(rec: Records) -> list[dict]:
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT id, fields FROM items WHERE kind = ? ORDER BY created_at, rowid", (LESSON,)
        ).fetchall()
    return [{"id": i, **json.loads(f)} for i, f in rows]


def _open_comments(rec: Records) -> int:
    with rec.read() as conn:
        (n,) = conn.execute(
            "SELECT count(*) FROM comments WHERE status = 'open' AND parent_id IS NULL"
        ).fetchone()
    return n


def waiting(rec: Records, cards: int) -> int:
    """What waits for the engineer in the project chat: `cards`, the running Briefs' cards, and
    the "I understood this" card while it is there and not approved."""
    found = understand.facts(rec)
    there = bool(found["facts"] or found["files"] or found["missing"])
    return cards + int(there and not found["approved"])


def checklist(rec: Records, engineer: Records) -> dict:
    """The GET /closing answer: open comments, the Deliverables not signed off, each
    Deliverable's newest Review report, Confidential, the archive time, and the lessons with
    whether each is already in Engineer Records."""
    listed = store.list_deliverables(rec)
    with rec.read() as conn:
        newest = dict(
            conn.execute(
                "SELECT deliverable_id, max(revision_no) FROM review_reports"
                " GROUP BY deliverable_id"
            ).fetchall()
        )
    carried = _carried(engineer, rec.id)
    return {
        "open_comments": _open_comments(rec),
        "unsigned": [
            {"id": d["id"], "name": d["title"]} for d in listed if d["status"] != "signed_off"
        ],
        "reports": [
            {"id": d["id"], "name": d["title"], "revision": newest[d["id"]]}
            for d in listed
            if d["id"] in newest
        ],
        "confidential": _confidential(rec),
        "archived_at": rec.archived_at,
        "lessons": [
            {"id": x["id"], "text": x["text"], "kind": x["kind"], "carried": x["id"] in carried}
            for x in _lessons(rec)
        ],
    }


async def propose_lessons(rec: Records, engine) -> str | None:
    """Starts the lessons Brief and returns its id; None for a Confidential Project. Raises what
    `Engine.start_brief` raises."""
    if _confidential(rec):
        return None
    text = copy.LESSONS_BRIEF[setup_state.language()]
    return await engine.start_brief(rec.id, text, instruction=INSTRUCTION)


def carry(rec: Records, engineer: Records, lesson_id: str, *, carry: bool) -> bool:
    """Carries one lesson to Engineer Records, by "engineer", once; returns whether it is there
    now. `carry=False` (keep it in the project) writes nothing, and a lesson already carried
    stays carried. The lesson's text and kind go, with the project's id; its source does not.
    Refuses (409) for a Confidential Project, (404) for an unknown lesson."""
    if _confidential(rec):
        raise RecordsError(copy.LESSON_STAYS_CONFIDENTIAL)
    found = next((x for x in _lessons(rec) if x["id"] == lesson_id), None)
    if found is None:
        raise RecordsError(copy.LESSON_NOT_FOUND, status=404, field="lesson_id")
    if lesson_id in _carried(engineer, rec.id):
        return True
    if not carry:
        return False
    fields = {
        "text": found["text"],
        "kind": found["kind"],
        "from_project": rec.id,
        "from_lesson": lesson_id,
    }
    ledger.add_item(engineer, kind=LESSON, actor=ENGINEER, fields=fields)
    return True


def archive(rec: Records, backups: Backups | None) -> dict:
    """{"archived_at", "backed_up", "note"}: archives the project (audited, with what was still
    open), then takes the final backup. Archiving again changes nothing."""
    if rec.archived_at is not None:
        return {"archived_at": rec.archived_at, "backed_up": None, "note": None}
    understand.project_new_once(rec)  # old work is archived without the understanding step
    unsigned = [d["id"] for d in store.list_deliverables(rec) if d["status"] != "signed_off"]
    still = {"open_comments": _open_comments(rec), "unsigned": unsigned}
    at = rec.clock()
    with rec.write(ENGINEER, archive_change=True) as conn:
        rec.set_meta(conn, ARCHIVED, at)
        audit.record(
            conn,
            at=at,
            actor=ENGINEER,
            action="archive",
            table="meta",
            row_id=rec.id,
            before={ARCHIVED: None},
            after={ARCHIVED: at, **still},
        )
    rec.archived_at = at
    # The audit trail just grew, so a reachable Backup folder always gets a new copy: no copy
    # means the backup was not made (no folder, folder away, or the copy failed).
    backed_up = backups is not None and backups.run(rec.id, reason="archive") > 0
    usage.track("project_archived")
    return {
        "archived_at": at,
        "backed_up": backed_up,
        "note": None if backed_up else copy.ARCHIVE_BACKUP_FAILED,
    }


def unarchive(rec: Records) -> None:
    """Makes the project changeable again, audited. Safe on a project that is not archived."""
    before = rec.archived_at
    if before is None:
        return
    with rec.write(ENGINEER, archive_change=True) as conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (ARCHIVED,))
        audit.record(
            conn,
            at=rec.clock(),
            actor=ENGINEER,
            action="unarchive",
            table="meta",
            row_id=rec.id,
            before={ARCHIVED: before},
            after={ARCHIVED: None},
        )
    rec.archived_at = None
