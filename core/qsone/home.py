"""Home and a tender's header (Phase 1, C7): what GET /home and GET /projects/{id}/tender answer.

A tender's row has two halves. What its Project Records hold (files, the submission date, the
plan, the last work, the waiting items that survive a restart) is read by `snapshot` each time
`Projects._remember` reads the project, and kept with it: a closed project is never opened to
draw Home. What runs now (Briefs, the cards they wait on, their Progress Lines) is the engine's
memory. `_row` joins the two, and `TenderRow.state` is the first rule of the contract that holds.

The plan and the Findings are read through `plan_reader` and `waiting_readers`, which the jobs
that keep them set when their module is imported; until then a tender has no plan."""

import json
from collections.abc import Callable

from qsone import copy, settings
from qsone.engine.plan import claims
from qsone.engine.store import UNFINISHED
from qsone.home_block import lead_block, tender_block
from qsone.records.project import Records, RecordsError

GENERAL = "general"  # the Home conversation's chat
LAST = "last_project_id"  # settings.json: the tender last opened (POST /projects/{id}/open)


def _no_plan(rec: Records) -> dict | None:
    return None


# The tender plan as `TenderPlan` JSON, or None (C2 sets it).
plan_reader: Callable[[Records], dict | None] = _no_plan
# Durable `WaitingItem`s as JSON: a proposed plan, a stage to sign off, a Suggested change (C2),
# the raised Finding (C4).
waiting_readers: list[Callable[[Records], list[dict]]] = []


def item(
    kind: str,
    item_id: str,
    project_id: str | None,
    title: dict,
    since: str,
    *,
    blocking: bool = True,
    text: str | None = None,
) -> dict:
    """One `WaitingItem` as JSON."""
    return {
        "id": item_id,
        "kind": kind,
        "project_id": project_id,
        "title": title,
        "text": text,
        "since": since,
        "blocking": blocking,
    }


# What the project holds --------------------------------------------------------------------


def _source(source: dict) -> dict:
    """A tender fact's source as a contract `Source`: a file with its name and place, or the
    engineer's own value with the day it was given."""
    empty = {"file_name": None, "file_id": None, "url": None, "dated": None, "quote": None}
    if source.get("kind") == "file":
        name = source.get("file_name")
        return empty | {
            "kind": "file",
            "title": name or "",
            "file_name": name,
            "file_id": source.get("file_id"),
            "locator": source.get("locator") or {},
        }
    return empty | {"kind": "engineer", "title": "", "locator": {}, "dated": source.get("date")}


def _submission(rec: Records) -> tuple[str | None, dict | None]:
    from qsone.journey import understand

    fact = understand.facts(rec)["facts"].get("submission_date")
    if fact is None or not fact["value"]:
        return None, None
    return fact["value"], _source(fact["source"])


def _plan(found: dict | None) -> dict | None:
    if found is None:
        return None
    stages = found["stages"]
    now = next((s for s in stages if s["status"] in ("now", "waiting_engineer")), None)
    done = found["status"] == "approved" and all(s["status"] == "approved" for s in stages)
    return {
        "stages": [s["status"] for s in stages],
        "stage": now["title"] if now else None,
        "finished": bool(stages) and done,
    }


def snapshot(rec: Records) -> dict:
    """The half of the tender's row its Project Records hold, read from the open file."""
    marks = ", ".join("?" * len(UNFINISHED))
    with rec.read() as conn:
        states = dict(
            conn.execute(
                "SELECT m.local_state, count(*) FROM files f"
                " JOIN map_files m ON m.file_id = f.id AND m.valid_until IS NULL"
                " WHERE f.valid_until IS NULL GROUP BY m.local_state"
            ).fetchall()
        )
        (total,) = conn.execute("SELECT count(*) FROM files WHERE valid_until IS NULL").fetchone()
        sample = conn.execute("SELECT 1 FROM sources WHERE kind = 'sample' LIMIT 1").fetchone()
        last = conn.execute(
            "SELECT id, status, step FROM briefs WHERE chat_id = ?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (rec.id,),
        ).fetchone()
        cut = conn.execute(
            f"SELECT id, updated_at FROM briefs WHERE chat_id = ? AND status IN ({marks})"
            " ORDER BY created_at, rowid",
            (rec.id, *UNFINISHED),
        ).fetchall()
        driven = claims.driven(conn)  # a tender stage's work resumes by itself: never listed
    cut = [(i, at) for i, at in cut if i not in driven]
    date, source = _submission(rec)
    durable = [item("unfinished", i, rec.id, copy.WAITING_UNFINISHED, at) for i, at in cut]
    for read in waiting_readers:
        durable += read(rec)
    return {
        "sample": sample is not None,
        "submission_date": date,
        "submission_source": source,
        "files_total": total,
        "files_read": states.get("done", 0) + states.get("failed", 0),
        "files_reading": states.get("waiting", 0) + states.get("reading", 0) > 0,
        "plan": _plan(plan_reader(rec)),
        "last": None
        if last is None
        else {"id": last[0], "status": last[1], "step": json.loads(last[2]) if last[2] else None},
        "waiting": durable,
    }


# What runs now -------------------------------------------------------------------------------


def _asked_at(brief, card_id: str) -> str:
    with brief.store.rec.read() as conn:
        found = conn.execute("SELECT asked_at FROM approvals WHERE id = ?", (card_id,)).fetchone()
    return found[0] if found else brief.store.rec.clock()


def _cards(briefs: list, project_id: str | None) -> list[dict]:
    found = []
    for brief in briefs:
        for card_id, (card, _) in tuple(brief.waiting.items()):
            questions = (card.payload or {}).get("questions") or [{}]
            text = questions[0].get("text") if card.kind == "question" else None
            since = _asked_at(brief, card_id)
            found.append(item(card.kind, card_id, project_id, card.title, since, text=text))
    return found


def _live(durable: list[dict], briefs: list, project_id: str | None) -> list[dict]:
    """The waiting items of a conversation now, oldest first: its durable ones (a cut-off
    Brief this core runs again is not one) and the cards its running Briefs wait on."""
    running = {b.brief_id for b in briefs}
    found = [
        i | {"blocking": not briefs} if i["kind"] == "decision" else i
        for i in durable
        if not (i["kind"] == "unfinished" and i["id"] in running)
    ]
    return sorted(found + _cards(briefs, project_id), key=lambda i: i["since"])


def _reading(brief) -> bool:
    from qsone.journey import understand

    return brief.state in ("queued", "running") and (
        brief.mapping_files is not None or brief.instruction == understand.INSTRUCTION
    )


def _state(known: dict, snap: dict, briefs: list, items: list[dict]) -> tuple[str, dict | None]:
    """`TenderRow.state` and `line`: the first rule of the contract's order that holds."""
    blocking = [i for i in items if i["blocking"]]
    states = {b.state for b in briefs}
    step = next((b.step for b in briefs), None)  # the newest Progress Line
    plan, last = snap["plan"], snap["last"]
    if known.get("archived_at"):
        return "archived", None
    if "waiting_engineer" in states or (not briefs and blocking):
        return "waiting", blocking[0]["title"] if blocking else step
    if "paused_cap" in states:
        return "paused", step
    if "waiting_connection" in states:
        return "offline", step
    if plan is None and (snap["files_reading"] or any(_reading(b) for b in briefs)):
        return "reading", step
    if briefs:
        return "working", step
    if plan is not None and plan["finished"]:
        return "finished", None
    if last is not None and last["status"] in ("failed", "stopped"):
        return last["status"], last["step"]
    return ("no_plan", None) if plan is None else ("working", None)


def _row(known: dict, snap: dict, engine, blocked: dict | None) -> tuple[dict, list[dict]]:
    briefs = engine.running(known["id"])
    items = _live(snap["waiting"], briefs, known["id"])
    state, line = _state(known, snap, briefs, items)
    plan = snap["plan"]
    row = {
        "project_id": known["id"],
        "name": known["name"],
        "name_pair": known.get("name_pair"),
        "confidential": known["confidential"],
        "sample": snap["sample"],
        "state": state,
        "line": line,
        "blocked": tender_block(engine, known["confidential"], blocked),
        "stage": plan["stage"] if plan else None,
        "stages": plan["stages"] if plan else [],
        "submission_date": snap["submission_date"],
        "submission_source": snap["submission_source"],
        "waiting": len(items),
        "files_read": snap["files_read"],
        "files_total": snap["files_total"],
    }
    return row, items


# The answers ---------------------------------------------------------------------------------


def _home_waiting(engine) -> list[dict]:
    """What waits in the Home conversation: its cut-off work and its cards."""
    try:
        rec = engine.engineer_records()
    except RecordsError:
        return []
    marks = ", ".join("?" * len(UNFINISHED))
    with rec.read() as conn:
        cut = conn.execute(
            f"SELECT id, updated_at FROM briefs WHERE chat_id = ? AND status IN ({marks})",
            (GENERAL, *UNFINISHED),
        ).fetchall()
    durable = [item("unfinished", i, None, copy.WAITING_UNFINISHED, at) for i, at in cut]
    return _live(durable, engine.running(GENERAL), None)


def _ordered(rows: list[tuple[dict, str]]) -> list[dict]:
    """Not finished with a date, nearest first; then no date, newest first; then finished,
    latest date first. `rows` are (row, created_at)."""
    dated = [(r, at) for r, at in rows if r["state"] != "finished" and r["submission_date"]]
    undated = [(r, at) for r, at in rows if r["state"] != "finished" and not r["submission_date"]]
    done = [(r, at) for r, at in rows if r["state"] == "finished"]
    dated.sort(key=lambda x: x[0]["submission_date"])
    undated.sort(key=lambda x: x[1], reverse=True)
    done.sort(key=lambda x: (x[0]["submission_date"] or "", x[1]), reverse=True)
    return [r for r, _ in dated + undated + done]


def tenders(projects, engine, blocked: dict | None) -> tuple[list[dict], list[dict], list[dict]]:
    """(rows in Home's order, their waiting items, the unreadable projects)."""
    rows, waiting, unreadable = [], [], []
    for known in projects.list():
        if "error" in known:
            unreadable.append({"project_id": known["id"], "reason": known["error"]})
            continue
        if known.get("archived_at"):
            continue
        row, items = _row(known, projects.tenders[known["id"]], engine, blocked)
        rows.append((row, known["created_at"]))
        waiting += items
    return _ordered(rows), waiting, unreadable


def home(projects, engine) -> dict:
    """The `Home` answer. It never refuses: what cannot be read is said inside it."""
    from qsone import home_summary

    blocked = lead_block(engine)
    rows, waiting, unreadable = tenders(projects, engine, blocked)
    waiting = sorted(waiting + _home_waiting(engine), key=lambda i: i["since"])
    last = settings.load().get(LAST)
    return {
        "summary": home_summary.current(engine, rows, waiting),
        "blocked": blocked,
        "last_project_id": last if any(r["project_id"] == last for r in rows) else None,
        "waiting": waiting,
        "tenders": rows,
        "unreadable": unreadable,
    }


def tender(projects, engine, project_id: str) -> dict:
    """The `TenderView` of one tender, from what the core holds. Raises `RecordsError`:
    PROJECT_NOT_FOUND, or the refusal opening its file gives."""
    from qsone.records.project import FILE_NAME

    if not (projects._folder(project_id) / FILE_NAME).is_file():
        raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
    known = next(p for p in projects.list() if p["id"] == project_id)
    if "error" in known:
        projects.open_file(project_id).close()  # raises the refusal `open` gives
        projects.forget(project_id)
        known = next(p for p in projects.list() if p["id"] == project_id)
    row, items = _row(known, projects.tenders[project_id], engine, lead_block(engine))
    return {"tender": row, "waiting": items}
