"""The plan driver's claims: which Brief does a stage's work, one per stage and attempt.

A claim is written in the same transaction as its Brief's row (`tender_stage_briefs`, records
schema), so a power cut keeps both or neither and a stage never starts twice. Claims are never
changed or deleted: the table's triggers refuse it. What a stage waits for is read from its
latest claim's Brief each time, so it cannot drift."""

from qsone.engine.types import Data
from qsone.records.project import Records

TABLE = "tender_stage_briefs"


def latest(conn, stage_id: str) -> dict | None:
    """The stage's latest claim with its Brief's state, or None: `{"attempt", "brief_id",
    "status", "began"}`; `began` is False while the Brief has no agent run yet."""
    found = conn.execute(
        f"SELECT k.attempt, k.brief_id, b.status, EXISTS (SELECT 1 FROM agent_runs r"
        f" WHERE r.brief_id = k.brief_id) FROM {TABLE} k JOIN briefs b ON b.id = k.brief_id"
        " WHERE k.stage_id = ? ORDER BY k.attempt DESC LIMIT 1",
        (stage_id,),
    ).fetchone()
    if found is None:
        return None
    attempt, brief_id, status, began = found
    return {"attempt": attempt, "brief_id": brief_id, "status": status, "began": bool(began)}


def add(conn, stage_id: str, attempt: int, brief_id: str, at: str) -> None:
    conn.execute(f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?)", (stage_id, attempt, brief_id, at))


def every(conn, stage_id: str) -> list[tuple[str, str]]:
    """(Brief id, when claimed) of each of the stage's attempts, first first."""
    found = conn.execute(
        f"SELECT brief_id, created_at FROM {TABLE} WHERE stage_id = ? ORDER BY attempt",
        (stage_id,),
    )
    return [(brief_id, at) for brief_id, at in found.fetchall()]


def worked(conn, stage_id: str) -> list[str]:
    """Every Brief whose work counts for the stage, in order: its attempts, and the tender's
    other Briefs since its first (a Finding's decision, "I have notes", the engineer's own)."""
    attempts = every(conn, stage_id)
    if not attempts:
        return []
    found = conn.execute(
        f"SELECT b.id FROM briefs b WHERE b.id IN (SELECT brief_id FROM {TABLE} WHERE stage_id = ?)"
        f" OR (b.created_at >= ? AND NOT EXISTS (SELECT 1 FROM {TABLE} k WHERE k.brief_id = b.id))"
        " ORDER BY b.created_at, b.rowid",
        (stage_id, attempts[0][1]),
    )
    return [r[0] for r in found.fetchall()]


def stage_of(conn, brief_id: str) -> str | None:
    """The stage whose work the Brief is, or None for any other Brief."""
    found = conn.execute(f"SELECT stage_id FROM {TABLE} WHERE brief_id = ?", (brief_id,))
    row = found.fetchone()
    return None if row is None else row[0]


def place(rec: Records, brief_id: str) -> tuple[int, int] | None:
    """(n, total): the stage of the current plan whose work the Brief is, or None."""
    from qsone.engine.plan import store  # the plan's store reads the runner's tables too

    with rec.read() as conn:
        stage_id = stage_of(conn, brief_id)
    plan = None if stage_id is None else store.current(rec)
    found = [s.id for s in plan.stages] if plan is not None else []
    return (found.index(stage_id) + 1, len(found)) if stage_id in found else None


def driven(conn) -> set[str]:
    """Every Brief that is a stage's work; none while a file older than the driver is brought
    up to date."""
    known = conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (TABLE,)).fetchone()
    return set() if known is None else {r[0] for r in conn.execute(f"SELECT brief_id FROM {TABLE}")}


def stage_part(brief_id: str, stage_id: str) -> Data:
    """`data-stage`: this reply ends the stage's work and asks for its sign-off. A pointer: the
    screen draws the sign-off block from the plan it holds."""
    return Data(brief_id, "stage", stage_id, {"stage_id": stage_id})


def ended(rec: Records, brief: dict) -> str | None:
    """The stage a Brief that ended done ends again, or None: its own stage for a stage's
    Brief; for any other, the stage that waits for its sign-off when the Brief came after
    that stage's first Brief (its work counts for it, `worked`)."""
    from qsone.engine.plan import store

    if brief["status"] != "done":
        return None
    with rec.read() as conn:
        stage_id = stage_of(conn, brief["id"])
    if stage_id is not None:
        return stage_id
    plan = store.current(rec)
    waiting = [] if plan is None else [s for s in plan.stages if s.status == "waiting_engineer"]
    if not waiting:
        return None
    with rec.read() as conn:
        attempts = every(conn, waiting[0].id)
    return waiting[0].id if attempts and brief["created_at"] >= attempts[0][1] else None


def stored_parts(rec: Records, brief: dict) -> list[Data]:
    """The `data-stage` part of a stored Brief that ended a stage, as it was sent live."""
    stage_id = ended(rec, brief)
    return [] if stage_id is None else [stage_part(brief["id"], stage_id)]
