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


def stage_of(conn, brief_id: str) -> str | None:
    """The stage whose work the Brief is, or None for any other Brief."""
    found = conn.execute(f"SELECT stage_id FROM {TABLE} WHERE brief_id = ?", (brief_id,))
    row = found.fetchone()
    return None if row is None else row[0]


def stage_part(brief_id: str, stage_id: str) -> Data:
    """`data-stage`: this reply ends the stage's work and asks for its sign-off. A pointer: the
    screen draws the sign-off block from the plan it holds."""
    return Data(brief_id, "stage", stage_id, {"stage_id": stage_id})


def stored_parts(rec: Records, brief: dict) -> list[Data]:
    """The `data-stage` part of a stored stage Brief that ended done, as it was sent live."""
    if brief["status"] != "done":
        return []
    with rec.read() as conn:
        stage_id = stage_of(conn, brief["id"])
    return [] if stage_id is None else [stage_part(brief["id"], stage_id)]
