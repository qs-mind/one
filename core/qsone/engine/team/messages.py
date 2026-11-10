"""The team room's messages (Phase 1, C6), kept in the project file (`room_messages`), apart
from the engineer's conversation and from the Coordination Room of older Briefs
(`team_messages`, which holds names, not member ids).

- A message goes from a member (`lead-qs` or a member's id; the Checking QS never writes) or the
  engineer, to a member, the whole team (`team`) or the engineer, with the places in the
  tender's files it rests on (`sources`, the contract's `Source`).
- `kind` (say, assign, ask, object, resolve) and `thread` (the id of the exchange's first
  message) are the room's own: the screen does not draw them (the contract's Q12). They count
  the rounds of a disagreement (`objections`).
- `raised` follows what the Lead raised to the engineer, a Finding or a card: `{id, answered}`,
  or null for an ordinary message and again when the card was withdrawn.
- A page is newest first, in the order the messages were written; its cursor names the oldest
  message of the page, opaquely."""

import base64
import binascii
import json
from collections.abc import Iterable
from uuid import uuid4

from qsone import activity, copy
from qsone.engine import findings
from qsone.engine.findings import Place
from qsone.engine.types import Data
from qsone.records.project import Records, RecordsError

ENGINEER, TEAM = "engineer", "team"
PART = "room"  # the `data-room` part
MAX_TEXT = 20_000  # what the engineer may write (ROOM_TOO_LONG)
_ACTOR = "engine"
_COLUMNS = "id, from_id, to_id, text, sources, at, raised_id, raised_answered"
_CURSOR = "room:"


def _message(row) -> dict:
    """A stored row as the contract's `RoomMessage`."""
    message_id, from_id, to_id, text, sources, at, raised_id, answered = row
    raised = None if raised_id is None else {"id": raised_id, "answered": bool(answered)}
    return {
        "id": message_id,
        "from_id": from_id,
        "to_id": to_id,
        "text": text,
        "sources": json.loads(sources),
        "at": at,
        "raised": raised,
    }


def _one(conn, message_id: str) -> dict:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM room_messages WHERE id = ?", (message_id,)
    ).fetchone()
    return _message(row)


def checked_text(text: str) -> str:
    """The engineer's message as it is stored. Raises `RecordsError` (422, field "text")."""
    if not text:
        raise RecordsError(copy.ROOM_EMPTY, status=422, field="text")
    if len(text) > MAX_TEXT:
        raise RecordsError(copy.ROOM_TOO_LONG, status=422, field="text")
    return text


def sources_of(rec: Records, places: Iterable[Place], finding_id: str | None = None) -> list:
    """The places as `Source`s, then the sources of the Finding the message cites. Raises
    `RecordsError` for a place outside the project's files or an unknown Finding."""
    with rec.read() as conn:
        found = [findings._source(conn, place) for place in places]
        if finding_id is not None:
            cited = findings._one(conn, finding_id)
            if cited is None:
                raise RecordsError(copy.FINDING_NOT_FOUND, status=404, field="finding_id")
            found += [s for s in cited["sources"] if s not in found]
    return found


def write(
    rec: Records,
    *,
    from_id: str,
    to_id: str,
    text: str,
    sources: list | None = None,
    brief_id: str | None = None,
    kind: str = "say",
    reply_to: str | None = None,
    raised_id: str | None = None,
    message_id: str | None = None,
) -> dict:
    """A new message, as the contract's `RoomMessage`. A reply to an unknown message starts a
    thread of its own."""
    message_id = message_id or uuid4().hex
    with rec.write(_ACTOR) as conn:
        thread = message_id
        if reply_to is not None:
            row = conn.execute(
                "SELECT thread FROM room_messages WHERE id = ?", (reply_to,)
            ).fetchone()
            thread = message_id if row is None else row[0]
        conn.execute(
            "INSERT INTO room_messages (id, brief_id, at, from_id, to_id, text, sources, kind,"
            " thread, raised_id, raised_answered) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, brief_id, rec.clock(), from_id, to_id, text,
             json.dumps(sources or [], ensure_ascii=False), kind, thread, raised_id,
             None if raised_id is None else 0),
        )  # fmt: skip
        return _one(conn, message_id)


def set_brief(rec: Records, message_id: str, brief_id: str) -> None:
    """The Brief the message steered or started: its reply shows the message."""
    with rec.write(_ACTOR) as conn:
        conn.execute("UPDATE room_messages SET brief_id = ? WHERE id = ?", (brief_id, message_id))


def set_raised(rec: Records, message_id: str, raised: dict | None) -> dict:
    """The message with `raised` as given ({id, answered} or None)."""
    raised_id = None if raised is None else raised["id"]
    answered = None if raised is None else int(raised["answered"])
    with rec.write(_ACTOR) as conn:
        conn.execute(
            "UPDATE room_messages SET raised_id = ?, raised_answered = ? WHERE id = ?",
            (raised_id, answered, message_id),
        )
        return _one(conn, message_id)


def answered(rec: Records, raised_id: str) -> list[dict]:
    """Every message that raised `raised_id`, now answered; the ones that changed."""
    with rec.write(_ACTOR) as conn:
        rows = conn.execute(
            "SELECT id FROM room_messages WHERE raised_id = ? AND raised_answered = 0",
            (raised_id,),
        ).fetchall()
        conn.execute(
            "UPDATE room_messages SET raised_answered = 1 WHERE raised_id = ?", (raised_id,)
        )
        return [_one(conn, message_id) for (message_id,) in rows]


def objections(rec: Records, thread: str) -> list[tuple[str, str, list]]:
    """(from_id, text, sources) of each objection in the thread since it was last resolved,
    oldest first."""
    with rec.read() as conn:
        (since,) = conn.execute(
            "SELECT coalesce(max(rowid), 0) FROM room_messages"
            " WHERE thread = ? AND kind = 'resolve'",
            (thread,),
        ).fetchone()
        rows = conn.execute(
            "SELECT from_id, text, sources FROM room_messages WHERE thread = ? AND kind = 'object'"
            " AND rowid > ? ORDER BY rowid",
            (thread, since),
        ).fetchall()
    return [(from_id, text, json.loads(sources)) for from_id, text, sources in rows]


def thread_of(rec: Records, message_id: str) -> str:
    with rec.read() as conn:
        (thread,) = conn.execute(
            "SELECT thread FROM room_messages WHERE id = ?", (message_id,)
        ).fetchone()
    return thread


# Reading the room ------------------------------------------------------------------------------


def _cursor(rowid: int) -> str:
    return base64.urlsafe_b64encode(f"{_CURSOR}{rowid}".encode()).decode().rstrip("=")


def _before(cursor: str) -> int:
    """The rowid a cursor names. Raises `RecordsError` (422, field "cursor")."""
    try:
        said = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        rowid = int(said.removeprefix(_CURSOR)) if said.startswith(_CURSOR) else 0
    except (binascii.Error, UnicodeDecodeError, ValueError):
        rowid = 0
    if rowid <= 0:
        raise RecordsError(copy.ROOM_CURSOR_INVALID, status=422, field="cursor")
    return rowid


def page(rec: Records, cursor: str | None, limit: int) -> dict:
    """The contract's `RoomPage`: the newest `limit` messages before the cursor, newest first."""
    before = _before(cursor) if cursor is not None else None
    with rec.read() as conn:
        rows = conn.execute(
            f"SELECT rowid, {_COLUMNS} FROM room_messages"
            + ("" if before is None else " WHERE rowid < ?")
            + " ORDER BY rowid DESC LIMIT ?",
            (limit + 1,) if before is None else (before, limit + 1),
        ).fetchall()
    shown = rows[:limit]
    more = len(rows) > limit
    return {
        "messages": [_message(row[1:]) for row in shown],
        "next_cursor": _cursor(shown[-1][0]) if more else None,
    }


def in_brief(rec: Records, brief_id: str) -> list[dict]:
    """The messages written during a Brief, oldest first."""
    with rec.read() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM room_messages WHERE brief_id = ? ORDER BY rowid", (brief_id,)
        ).fetchall()
    return [_message(row) for row in rows]


# What the screen is told -----------------------------------------------------------------------


def part(brief_id: str, message: dict) -> Data:
    """The `data-room` part of the reply the message was written in."""
    return Data(brief_id, PART, message["id"], message)


def stored_parts(rec: Records, brief_id: str) -> list[Data]:
    """The `data-room` parts of a stored reply, from the room's messages of that Brief."""
    return [part(brief_id, message) for message in in_brief(rec, brief_id)]


def publish(project_id: str, changed: list[dict]) -> None:
    """A `room` event for each message written or whose `raised` changed. Call it on the
    core's event loop."""
    for message in changed:
        activity.publish(project_id, {"type": "room", "message": message})
