"""Findings (Phase 1, C4): a conflict or risk in the tender, with the places in its files that
show it. The two tools are in `finding_tools`; importing it registers them.

- `record_finding` (the Lead and any specialist): an `open` Finding. Each source must be a page,
  a sheet row or another place inside a file of the project; its title and file name come from
  the file, never from the model. At most `MAX_UNSETTLED` wait in one tender.
- `raise_finding` (the Lead): returns at once, so it never holds the Lead's run. The Finding is
  `raised`, or `queued` behind the one raised (one at a time); a `data-finding` part, a pointer,
  places it in the reply.
- `decide` (route 14) settles the raised one with the engineer's choice, and `close` settles one
  without it (`chosen` null, a `note` says how). The oldest queued one is then raised by code.

Every change is published on the tender's activity channel as a `finding` event. The Findings are
the team's shared memory: `search_records` returns those that match (`matching`)."""

import json
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from qsone import activity, copy
from qsone.engine.tools import ModelRetry
from qsone.engine.tools_records.shared import _json
from qsone.engine.tools_records.source_evidence import _inside, _no_evidence, _place
from qsone.engine.types import Data
from qsone.records import arabic, audit
from qsone.records.project import Records, RecordsError

MAX_UNSETTLED = 100  # Findings not settled in one tender (the contract's Q22)
PART = "finding"  # the `data-finding` part
_COLUMNS = "id, title, text, sources, status, opinion, options, chosen, item_ids, note, settled_at"
_JSON = {"title", "sources", "options", "item_ids", "note"}

Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class Name(BaseModel):
    """A short name for the screen, in both languages."""

    model_config = ConfigDict(extra="forbid")

    en: Short
    ar: Short


class Place(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(min_length=1, max_length=64)
    locator: dict = Field(min_length=1, max_length=8)
    kind: str = Field("file", min_length=1, max_length=40)  # boq, specification, contract…


class RecordArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Name
    text: str = Field(min_length=1, max_length=4000)
    sources: list[Place] = Field(min_length=1, max_length=20)
    item_ids: list[str] = Field(default_factory=list, max_length=500)


class RaiseArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    finding_id: str = Field(min_length=1, max_length=64)
    opinion: str = Field(min_length=1, max_length=4000)
    options: list[Name] = Field(min_length=2, max_length=2)


# The stored Findings ----------------------------------------------------------------------------


def _finding(row) -> dict:
    """A stored row as the contract's `Finding`."""
    found = dict(zip(_COLUMNS.split(", "), row, strict=True))
    return found | {k: json.loads(found[k]) for k in _JSON if found[k] is not None}


def _one(conn, finding_id: str) -> dict | None:
    row = conn.execute(f"SELECT {_COLUMNS} FROM findings WHERE id = ?", (finding_id,)).fetchone()
    return None if row is None else _finding(row)


def listed(rec: Records) -> list[dict]:
    """Every Finding of the tender, oldest first."""
    with rec.read() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM findings ORDER BY recorded_at, rowid")
        return [_finding(row) for row in rows.fetchall()]


def _set(conn, at: str, actor: str, before: dict, **changes) -> dict:
    """Writes `changes` to the Finding, with its audit row; the Finding as it is now."""
    stored = {k: _json(v) if k in _JSON and v is not None else v for k, v in changes.items()}
    conn.execute(
        f"UPDATE findings SET {', '.join(f'{k} = ?' for k in stored)} WHERE id = ?",
        (*stored.values(), before["id"]),
    )
    after = before | {k: v for k, v in changes.items() if k in before}
    audit.record(
        conn, at=at, actor=actor, action="update", table="findings", row_id=before["id"],
        before=before, after=after,
    )  # fmt: skip
    return after


def _raise_next(conn, at: str, actor: str) -> list[dict]:
    """The oldest queued Finding, now raised; [] when none waits."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM findings WHERE status = 'queued' ORDER BY raised_at, rowid"
    ).fetchone()
    if row is None:
        return []
    return [_set(conn, at, actor, _finding(row), status="raised", note=copy.FINDING_WAITING)]


def _source(conn, place: Place) -> dict:
    """The place as a `Source`. Raises `RecordsError` unless it is inside a file of the project."""
    row = conn.execute("SELECT name, pages FROM files WHERE id = ?", (place.file_id,)).fetchone()
    if row is None:
        raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=422, field="sources")
    name, pages = row
    where = _place(place.locator)
    if not where:
        raise _no_evidence("locator")
    _inside(conn, place.file_id, pages, where)
    return {
        "kind": place.kind,
        "title": name,
        "file_name": name,
        "file_id": place.file_id,
        "locator": where,
        "url": None,
        "dated": None,
        "quote": None,
    }


def record(rec: Records, args: RecordArgs, *, actor: str, brief_id: str | None = None) -> dict:
    """A new `open` Finding. Raises `RecordsError`."""
    with rec.write(actor) as conn:
        (waiting,) = conn.execute(
            "SELECT count(*) FROM findings WHERE status != 'settled'"
        ).fetchone()
        if waiting >= MAX_UNSETTLED:
            raise RecordsError(copy.FINDINGS_TOO_MANY)
        sources = [_source(conn, place) for place in args.sources]
        item_ids = list(dict.fromkeys(args.item_ids))
        for item_id in item_ids:
            if conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone() is None:
                text = copy.fill(copy.FINDING_ITEM_UNKNOWN, item_id=item_id)
                raise RecordsError(text, status=422, field="item_ids")
        at, finding_id = rec.clock(), uuid4().hex
        conn.execute(
            "INSERT INTO findings (id, title, text, sources, status, item_ids, recorded_at,"
            " recorded_by, brief_id) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)",
            (finding_id, _json(args.title.model_dump()), args.text, _json(sources),
             _json(item_ids), at, actor, brief_id),
        )  # fmt: skip
        found = _one(conn, finding_id)
        audit.record(
            conn, at=at, actor=actor, action="insert", table="findings", row_id=finding_id,
            before=None, after=found,
        )  # fmt: skip
    return found


def raise_finding(rec: Records, args: RaiseArgs, *, actor: str) -> tuple[dict, int]:
    """The Finding, now raised or queued, and how many queued ones are ahead of it."""
    with rec.write(actor) as conn:
        found = _one(conn, args.finding_id)
        if found is None:
            raise RecordsError(copy.FINDING_NOT_FOUND, status=404, field="finding_id")
        if found["status"] != "open":
            raise ModelRetry(
                f"raise_finding: the Finding {args.finding_id} is {found['status']} already; "
                "raise each Finding once."
            )
        busy = conn.execute("SELECT 1 FROM findings WHERE status = 'raised'").fetchone()
        (ahead,) = conn.execute("SELECT count(*) FROM findings WHERE status = 'queued'").fetchone()
        at = rec.clock()
        options = [option.model_dump() for option in args.options]
        changed = _set(
            conn, at, actor, found, status="queued" if busy else "raised", opinion=args.opinion,
            options=options, note=None if busy else copy.FINDING_WAITING, raised_at=at,
        )  # fmt: skip
    return changed, ahead if busy else 0


def _settle(rec: Records, finding_id: str, actor: str, decide) -> tuple[dict, list[dict]]:
    with rec.write(actor) as conn:
        found = _one(conn, finding_id)
        if found is None:
            raise RecordsError(copy.FINDING_NOT_FOUND, status=404)
        changes = decide(found)
        if changes is None:  # the same answer again
            return found, []
        at = rec.clock()
        settled = _set(conn, at, actor, found, status="settled", settled_at=at, **changes)
        later = _raise_next(conn, at, actor) if found["status"] == "raised" else []
        return settled, [settled, *later]


def decide(rec: Records, finding_id: str, choice: int) -> tuple[dict, list[dict]]:
    """The engineer's choice for the raised Finding: (the Finding, every Finding it changed,
    the next one raised too). The same choice again changes nothing. Raises `RecordsError`:
    FINDING_NOT_FOUND (404), FINDING_NOT_RAISED or FINDING_SETTLED (409)."""

    def chosen(found: dict) -> dict | None:
        if found["status"] == "settled":
            if found["chosen"] == choice:
                return None
            raise RecordsError(copy.FINDING_SETTLED)
        if found["status"] != "raised":
            raise RecordsError(copy.FINDING_NOT_RAISED)
        return {"chosen": choice, "note": None}

    return _settle(rec, finding_id, "engineer", chosen)


def close(rec: Records, finding_id: str, note: dict, *, actor: str) -> list[dict]:
    """Settles a Finding without the engineer's choice (an addendum settled it, the consultant
    replied): `chosen` stays null and `note` says how. The Findings it changed."""

    def closed(found: dict) -> dict:
        if found["status"] == "settled":
            raise RecordsError(copy.FINDING_SETTLED)
        return {"chosen": None, "note": note}

    return _settle(rec, finding_id, actor, closed)[1]


def matching(rec: Records, words: list[str], most: int) -> list[dict]:
    """The Findings whose title or text holds one of `words`, oldest first, at most `most`."""
    terms = [t for t in (arabic.normalise(w.strip('"')) for w in words) if t]
    found = []
    for f in listed(rec):
        said = arabic.normalise(" ".join((f["title"]["en"], f["title"]["ar"], f["text"])))
        if any(term in said for term in terms):
            places = [
                {"file_id": s["file_id"], "file": s["file_name"], "locator": s["locator"]}
                for s in f["sources"]
            ]
            found.append(
                {
                    "finding_id": f["id"],
                    "title": f["title"],
                    "text": f["text"],
                    "status": f["status"],
                    "chosen": f["chosen"],
                    "sources": places,
                }
            )
    return found[:most]


def publish(project_id: str, changed: list[dict]) -> None:
    """A `finding` event for each changed Finding. Call it on the core's event loop."""
    for finding in changed:
        activity.publish(project_id, {"type": "finding", "finding": finding})


def stored_parts(brief_id: str, results: list[tuple[str, str]]) -> list[Data]:
    """The `data-finding` parts again, from the Lead's stored tool results."""
    found = []
    for name, text in results:
        if name != "raise_finding":
            continue
        try:
            finding_id = json.loads(text)["finding_id"]
        except (ValueError, KeyError, TypeError):
            continue
        found.append(Data(brief_id, PART, finding_id, {"finding_id": finding_id}))
    return found
