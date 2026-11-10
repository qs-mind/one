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
  or null for an ordinary message and again when the card was withdrawn. A withdrawn one keeps
  its `raised_id` (with `raised_answered` null), so the redone call finds it and raises it again
  (`redone`, `withdrawn_raise`).
- A page is newest first, in the order the messages were written; its cursor names the oldest
  message of the page, opaquely."""

import asyncio
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
    raised = None if answered is None else {"id": raised_id, "answered": bool(answered)}
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


def set_raised(rec: Records, message_id: str, raised: dict) -> dict:
    """The message with `raised` as given ({id, answered})."""
    with rec.write(_ACTOR) as conn:
        conn.execute(
            "UPDATE room_messages SET raised_id = ?, raised_answered = ? WHERE id = ?",
            (raised["id"], int(raised["answered"]), message_id),
        )
        return _one(conn, message_id)


def answered(rec: Records, raised_id: str) -> list[dict]:
    """Every message that raised `raised_id`, now answered; the ones that changed."""
    return _waiting_now(rec, [raised_id], 1)


def withdrawn(rec: Records, card_ids: list[str]) -> list[dict]:
    """Every message that raised one of these cards, back to `raised` null: the cards were
    withdrawn. The ones that changed."""
    return _waiting_now(rec, card_ids, None)


def _waiting_now(rec: Records, raised_ids: list[str], answered: int | None) -> list[dict]:
    """The messages still waiting on one of `raised_ids`, with `raised_answered` set."""
    if not raised_ids:
        return []
    marks = ", ".join("?" * len(raised_ids))
    waiting = f"WHERE raised_answered = 0 AND raised_id IN ({marks})"
    with rec.write(_ACTOR) as conn:
        rows = conn.execute(f"SELECT id FROM room_messages {waiting}", raised_ids).fetchall()
        conn.execute(f"UPDATE room_messages SET raised_answered = ? {waiting}",
                     (answered, *raised_ids))  # fmt: skip
        return [_one(conn, message_id) for (message_id,) in rows]


def cards_withdrawn(rec: Records, card_ids: list[str]) -> None:
    """The store withdrew these cards (a restart, a Stop, «Leave it»): their messages are back
    to `raised` null. The room is told when this runs on the core's event loop; off it (a sync
    route's thread) the room reads the change on its next page."""
    changed = withdrawn(rec, card_ids)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    publish(rec.id, changed)


def redone(rec: Records, brief_id: str, *, from_id: str, to_id: str, text: str, kind: str):
    """The message a redone call wrote before it was cut off: the same words in this Brief, in a
    thread whose raise was withdrawn. None when there is none."""
    with rec.read() as conn:
        row = conn.execute(
            "SELECT m.id FROM room_messages m WHERE m.brief_id = ? AND m.from_id = ?"
            " AND m.to_id = ? AND m.text = ? AND m.kind = ? AND EXISTS (SELECT 1 FROM"
            " room_messages w WHERE w.brief_id = m.brief_id AND w.thread = m.thread"
            " AND w.rowid >= m.rowid AND w.raised_id IS NOT NULL AND w.raised_answered IS NULL)"
            " ORDER BY m.rowid DESC LIMIT 1",
            (brief_id, from_id, to_id, text, kind),
        ).fetchone()
        return None if row is None else _one(conn, row[0])


def withdrawn_raise(rec: Records, brief_id: str, thread: str) -> dict | None:
    """The Lead's message of this thread whose card was withdrawn: the redone call raises it
    again instead of writing another."""
    with rec.read() as conn:
        row = conn.execute(
            "SELECT id FROM room_messages WHERE brief_id = ? AND thread = ?"
            " AND raised_id IS NOT NULL AND raised_answered IS NULL"
            " ORDER BY rowid DESC LIMIT 1",
            (brief_id, thread),
        ).fetchone()
        return None if row is None else _one(conn, row[0])


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
