"""Comments on a Deliverable: One's notes and Review comments, with replies and open/closed status.

Two kinds (decisions.md §9). A note is One's: an agent writes it, it has no code and never blocks.
A Review comment comes from the engineer or the Checking QS and may carry Code B or C; an open
Code C comment blocks Sign-off. Replies take their thread's kind and place.

A comment sits on part ids and column keys, never on A1 addresses:
  {"type": "cell", "row": part, "column": key}
  {"type": "range", "from": {"row", "column"}, "to": {"row", "column"}}
  {"type": "row", "row": part}                     (a Sheet row or a Document block)
  {"type": "text", "block": part, "start", "end", "quote"}
  {"type": "deliverable"}
Each thread also carries `anchor_now`, its place in the current version. A text anchor is found
again by its quoted words; one whose words are gone falls back to its block, and one whose row or
block was removed falls back to the whole Deliverable. Both are marked "moved": a comment is never
lost. A block's text, for offsets, is its text leaves joined in order (a number reference adds
nothing).
"""

import json
from uuid import uuid4

from qsone import copy
from qsone.deliverables import compare, events, ops, store
from qsone.records import audit
from qsone.records.project import Records, RecordsError

ENGINEER = ops.ENGINEER
CHECKER = "checking_qs"  # the Checking QS, the other author of Review comments
KINDS = ("note", "review")
_REVIEWERS = (ENGINEER, CHECKER)
_COLUMNS = (
    "id",
    "deliverable_id",
    "parent_id",
    "kind",
    "anchor",
    "body",
    "author",
    "code",
    "check_id",
    "status",
    "version_n",
    "created_at",
    "closed_at",
    "closed_by",
    "fix_asked_at",
)
_MOVED = {"type": "deliverable", "moved": True}


def _refuse(text: dict, field: str | None, status: int = 422) -> RecordsError:
    return RecordsError(text, status=status, field=field)


def check_body(body) -> str:
    if not isinstance(body, str) or not body.strip():
        raise _refuse(copy.COMMENT_NEEDS_TEXT, "body")
    return body.strip()


def check_kind(kind, actor: str, code) -> None:
    """A note is an agent's, with no code; a Review comment is the engineer's or the Checking
    QS's, with no code or Code B or C."""
    if kind not in KINDS:
        raise _refuse(copy.COMMENT_KIND_NOT_ALLOWED, "kind")
    if (kind == "note") == (actor in _REVIEWERS):
        raise _refuse(copy.COMMENT_KIND_NOT_ALLOWED, "kind")
    if code not in ((None,) if kind == "note" else (None, "B", "C")):
        raise _refuse(copy.COMMENT_KIND_NOT_ALLOWED, "code")


# Anchors.


def _part(conn, head: dict, part_id, field: str, *, current: bool) -> dict:
    """A part of this Deliverable, read at its current row version (every part keeps one, even
    once removed): not removed, unless not `current` (a check may be about an older version)."""
    kinds = {"block"} if head["kind"] == "document" else {"item", "section"}
    part = store.part_now(conn, part_id) if isinstance(part_id, str) else None
    ok = part is not None and part["deliverable_id"] == head["id"] and part["kind"] in kinds
    if ok and (not current or not part["removed"]):
        return part
    raise _refuse(copy.ANCHOR_NOT_FOUND, field)


def _column(head: dict, key, field: str) -> str:
    if key not in {c["key"] for c in head["template"].get("columns", [])}:
        raise _refuse(copy.ANCHOR_NOT_FOUND, field)
    return key


def _units(text: str) -> int:
    """`text.length` as the Document viewer counts it: UTF-16 code units, so a character past
    U+FFFF (an emoji) counts two. A text anchor's offsets are in these units."""
    return len(text.encode("utf-16-le")) // 2


def _index(text: str, units: int) -> int:
    """The Python index of the character at `units` UTF-16 code units into `text`."""
    count = 0
    for i, ch in enumerate(text):
        if count >= units:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def _found(text: str, quote: str, near: int) -> int | None:
    """Where `quote` is in `text`, the place nearest `near`, in UTF-16 units; None when it is
    not there."""
    places, at = [], text.find(quote)
    while at != -1:
        places.append(_units(text[:at]))
        at = text.find(quote, at + 1)
    return min(places, key=lambda p: (abs(p - near), p)) if places else None


def check_anchor(conn, head: dict, anchor, *, current: bool = True) -> dict:
    """The anchor checked against the Deliverable (ANCHOR_NOT_FOUND, field `anchor.<key>`) and
    rebuilt with its own keys only. A text anchor's offsets are set to where its quote is."""
    kind = anchor.get("type") if isinstance(anchor, dict) else None
    if kind not in head["template"].get("anchors", []):
        raise _refuse(copy.ANCHOR_NOT_FOUND, "anchor.type")
    if kind == "deliverable":
        return {"type": "deliverable"}
    if kind == "row":
        _part(conn, head, anchor.get("row"), "anchor.row", current=current)
        return {"type": "row", "row": anchor["row"]}
    if kind == "cell":
        _part(conn, head, anchor.get("row"), "anchor.row", current=current)
        column = _column(head, anchor.get("column"), "anchor.column")
        return {"type": "cell", "row": anchor["row"], "column": column}
    if kind == "range":
        ends = {}
        for end in ("from", "to"):
            given = anchor.get(end)
            given = given if isinstance(given, dict) else {}
            _part(conn, head, given.get("row"), f"anchor.{end}.row", current=current)
            column = _column(head, given.get("column"), f"anchor.{end}.column")
            ends[end] = {"row": given["row"], "column": column}
        return {"type": "range", **ends}
    # text
    part = _part(conn, head, anchor.get("block"), "anchor.block", current=current)
    quote, start, end = anchor.get("quote"), anchor.get("start"), anchor.get("end")
    if not (isinstance(quote, str) and quote) or not all(
        isinstance(n, int) and not isinstance(n, bool) for n in (start, end)
    ):
        raise _refuse(copy.ANCHOR_NOT_FOUND, "anchor.quote")
    found = _found(compare.block_text(part["node"]), quote, start)
    if found is None and current:  # a check's quote may be from the older version it read
        raise _refuse(copy.ANCHOR_NOT_FOUND, "anchor.quote")
    start = start if found is None else found
    return {
        "type": "text",
        "block": part["id"],
        "start": start,
        "end": start + _units(quote),
        "quote": quote,
    }


def _now(anchor: dict, parts: dict, columns: set[str]) -> dict:
    """The anchor in the current version: `parts` are the Deliverable's current parts by id,
    `columns` its current column keys."""

    def alive(part_id) -> bool:
        return part_id in parts and not parts[part_id]["removed"]

    kind = anchor["type"]
    if kind == "row":
        return anchor if alive(anchor["row"]) else _MOVED
    if kind == "cell":
        if not alive(anchor["row"]):
            return _MOVED
        if anchor["column"] in columns:
            return anchor
        return {"type": "row", "row": anchor["row"], "moved": True}
    if kind == "range":
        ends = (anchor["from"], anchor["to"])
        rows = [end["row"] for end in ends if alive(end["row"])]
        if not rows:
            return _MOVED
        if len(rows) == 2 and all(end["column"] in columns for end in ends):
            return anchor
        return {"type": "row", "row": rows[0], "moved": True}
    if kind == "text":
        if not alive(anchor["block"]):
            return _MOVED
        text = compare.block_text(parts[anchor["block"]]["node"])
        if text[_index(text, anchor["start"]) : _index(text, anchor["end"])] == anchor["quote"]:
            return anchor
        start = _found(text, anchor["quote"], anchor["start"])
        if start is None:
            return {"type": "row", "block": anchor["block"], "moved": True}
        return {**anchor, "start": start, "end": start + _units(anchor["quote"])}
    return anchor  # the whole Deliverable; "pdf_region" and "drawing_point" are reserved


# Reading.


def _row(found) -> dict:
    comment = dict(zip(_COLUMNS, found, strict=True))
    comment["anchor"] = json.loads(comment["anchor"])
    return comment


def read_threads(conn, head: dict, *, status: str | None = None) -> list[dict]:
    """Inside a read or write: the Deliverable's threads, oldest first, each with its replies
    (oldest first) and `anchor_now`. With `status`, only the threads that are open or closed."""
    rows = [
        _row(found)
        for found in conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM comments WHERE deliverable_id = ?"
            " ORDER BY created_at, rowid",
            (head["id"],),
        )
    ]
    parts = {
        part_id: {"kind": kind, "node": json.loads(node), "removed": bool(removed)}
        for part_id, kind, node, removed in conn.execute(
            "SELECT id, kind, node, removed FROM parts WHERE deliverable_id = ?"
            " AND valid_until IS NULL",
            (head["id"],),
        )
    }
    columns = {c["key"] for c in head["template"].get("columns", [])}
    threads = {
        c["id"]: {**c, "anchor_now": _now(c["anchor"], parts, columns), "replies": []}
        for c in rows
        if c["parent_id"] is None
    }
    for c in rows:
        if c["parent_id"] in threads:
            threads[c["parent_id"]]["replies"].append(c)
    return [t for t in threads.values() if status is None or t["status"] == status]


def list_comments(rec: Records, deliverable_id: str, *, status: str | None = None) -> list[dict]:
    """The Deliverable's threads, oldest first; each with its replies and `anchor_now`."""
    with rec.read() as conn:
        return read_threads(conn, ops.deliverable(conn, deliverable_id), status=status)


def _root(conn, comment_id) -> dict:
    """The thread a comment belongs to (the comment itself when it opens one)."""
    found = None
    if isinstance(comment_id, str):
        found = conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM comments WHERE id ="
            " (SELECT coalesce(parent_id, id) FROM comments WHERE id = ?)",
            (comment_id,),
        ).fetchone()
    if found is None:
        raise _refuse(copy.COMMENT_NOT_FOUND, "comment", status=404)
    return _row(found)


# Writing, inside a write.


def insert(
    conn,
    rec: Records,
    head: dict,
    *,
    kind: str,
    anchor: dict,
    body: str,
    actor: str,
    code: str | None,
    check_id: str | None,
    version_n: int,
    parent_id: str | None = None,
) -> str:
    """Inside a write: stores one comment, already checked, with its audit row."""
    row = {
        "id": uuid4().hex,
        "deliverable_id": head["id"],
        "parent_id": parent_id,
        "kind": kind,
        "anchor": anchor,
        "body": body,
        "author": actor,
        "code": code,
        "check_id": check_id,
        "status": "open",
        "version_n": version_n,
        "created_at": rec.clock(),
        "closed_at": None,
        "closed_by": None,
        "fix_asked_at": None,
    }
    stored = {**row, "anchor": json.dumps(anchor, ensure_ascii=False)}
    conn.execute(
        f"INSERT INTO comments ({', '.join(stored)}) VALUES ({', '.join('?' * len(stored))})",
        tuple(stored.values()),
    )
    audit.record(
        conn,
        at=row["created_at"],
        actor=actor,
        action="create",
        table="comments",
        row_id=row["id"],
        before=None,
        after=row,
    )
    return row["id"]


def _update(conn, rec, comment: dict, actor: str, **change) -> None:
    sets = ", ".join(f"{k} = ?" for k in change)
    conn.execute(f"UPDATE comments SET {sets} WHERE id = ?", (*change.values(), comment["id"]))
    audit.record(
        conn,
        at=rec.clock(),
        actor=actor,
        action="update",
        table="comments",
        row_id=comment["id"],
        before={"id": comment["id"], **{k: comment[k] for k in change}},
        after={"id": comment["id"], **change},
    )


# The calls.


def add(
    rec: Records,
    deliverable_id: str,
    *,
    kind: str,
    anchor: dict,
    body: str,
    actor: str,
    code: str | None = None,
    check_id: str | None = None,
) -> str:
    """A new thread on the latest version. Refusals: COMMENT_KIND_NOT_ALLOWED (a note from the
    engineer or the Checking QS, a note with a code, a Review comment from the team),
    COMMENT_NEEDS_TEXT, ANCHOR_NOT_FOUND (`anchor.<key>`), DELIVERABLE_NOT_FOUND."""
    check_kind(kind, actor, code)
    body = check_body(body)
    with rec.write(actor) as conn:
        head = ops.deliverable(conn, deliverable_id)
        if (
            check_id is not None
            and not conn.execute(
                "SELECT 1 FROM checks WHERE id = ? AND deliverable_id = ?", (check_id, head["id"])
            ).fetchone()
        ):
            raise ValueError("a comment's check is one of this Deliverable's checks")
        comment_id = insert(
            conn,
            rec,
            head,
            kind=kind,
            anchor=check_anchor(conn, head, anchor),
            body=body,
            actor=actor,
            code=code,
            check_id=check_id,
            version_n=ops.latest_version(conn, head["id"]),
        )
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return comment_id


def reply(rec: Records, comment_id: str, *, body: str, actor: str) -> str:
    """A reply in the comment's thread, of the thread's kind and at its place."""
    body = check_body(body)
    with rec.write(actor) as conn:
        root = _root(conn, comment_id)
        head = ops.deliverable(conn, root["deliverable_id"])
        reply_id = insert(
            conn,
            rec,
            head,
            kind=root["kind"],
            anchor=root["anchor"],
            body=body,
            actor=actor,
            code=None,
            check_id=None,
            version_n=ops.latest_version(conn, head["id"]),
            parent_id=root["id"],
        )
    events.publish_deliverable(rec, rec.id, root["deliverable_id"])
    return reply_id


def _set_status(rec: Records, comment_id: str, status: str, actor: str) -> None:
    with rec.write(actor) as conn:
        root = _root(conn, comment_id)
        if root["kind"] == "review" and actor not in _REVIEWERS:
            raise ValueError("only the engineer or the Checking QS closes a Review comment")
        if root["status"] == status:
            return
        closed = (rec.clock(), actor) if status == "closed" else (None, None)
        _update(conn, rec, root, actor, status=status, closed_at=closed[0], closed_by=closed[1])
    events.publish_deliverable(rec, rec.id, root["deliverable_id"])


def close(rec: Records, comment_id: str, *, actor: str) -> None:
    """Closes the comment's thread. A Review comment is closed only by the engineer or the
    Checking QS (ValueError otherwise), so the team cannot clear a Code C to unblock Sign-off."""
    _set_status(rec, comment_id, "closed", actor)


def reopen(rec: Records, comment_id: str, *, actor: str) -> None:
    """Opens the comment's thread again; the same people as `close`."""
    _set_status(rec, comment_id, "open", actor)


# "Fix it".


def _label(v: dict, part_id: str) -> str:
    """How the engineer names a row or block: an item's code, a section's title, or the first
    words of a block."""
    for row in v.get("rows", []):
        if row["id"] == part_id:
            return row["title"] if row["kind"] == "section" else row.get("code") or ""
    for block in v.get("blocks", []):
        if block["id"] == part_id:
            text = compare.block_text(block["node"])
            return text if len(text) <= 60 else text[:60].rsplit(" ", 1)[0] + " …"
    return part_id


def _place(v: dict, anchor: dict) -> dict:
    labels = {c["key"]: c["label"] for c in v.get("columns", [])}
    kind = anchor["type"]
    if kind == "cell":
        return copy.fill(
            copy.FIX_PLACE_CELL,
            row=_label(v, anchor["row"]),
            column=labels[anchor["column"]],
            id=anchor["row"],
        )
    if kind == "range":
        start, end = anchor["from"], anchor["to"]
        return copy.fill(
            copy.FIX_PLACE_RANGE,
            start=_label(v, start["row"]),
            end=_label(v, end["row"]),
            first=labels[start["column"]],
            last=labels[end["column"]],
            ids=f"{start['row']}, {end['row']}",
        )
    if kind == "row":
        part_id = anchor.get("row") or anchor["block"]
        return copy.fill(copy.FIX_PLACE_ROW, row=_label(v, part_id), id=part_id)
    if kind == "text":
        return copy.fill(copy.FIX_PLACE_TEXT, quote=anchor["quote"], id=anchor["block"])
    return copy.FIX_PLACE_DELIVERABLE


def fix_text(rec: Records, comment_id: str, *, lang: str) -> str:
    """The message the screen sends to the Lead QS for this comment's thread, in `lang`: the
    comment and Deliverable ids, the Revision and version, the place (item code and column label,
    or the quoted words) and the comment's words. Marks the thread "fix asked"."""
    if lang not in store.LANGUAGES:
        raise ValueError(f"lang must be one of {store.LANGUAGES}")
    with rec.write(ENGINEER) as conn:
        root = _root(conn, comment_id)
        head = ops.deliverable(conn, root["deliverable_id"])
        v = store.view(rec, head["id"])
        [thread] = [t for t in read_threads(conn, head) if t["id"] == root["id"]]
        at = (
            copy.fill(copy.FIX_AT_REVISION, no=v["revision"]["no"], n=v["version"])
            if v["revision"]
            else copy.fill(copy.FIX_AT_VERSION, n=v["version"])
        )
        text = copy.fill(
            copy.FIX_REQUEST,
            comment=root["id"],
            title=v["title"],
            deliverable=head["id"],
            at=at,
            place=_place(v, thread["anchor_now"]),
            body=root["body"],
        )[lang]
        _update(conn, rec, root, ENGINEER, fix_asked_at=rec.clock())
    events.publish_deliverable(rec, rec.id, head["id"])
    return text
