"""Checks, Close-out, Sign-off, Revisions and the Review report.

A check (code A, B or C, the checker's model, whether it shares the maker's provider) is recorded
only in-process, by the Checking QS: no HTTP route calls `record_check`, so the screen cannot fake
one. Plan 4's Checking QS, when it checks a Deliverable, records its Review through
`record_review`; Plan 4's own `reviews` table stays for agent drafts.

Status and Sign-off are decided here and in `store`, never by the screen. Sign-off is refused,
in this order: already signed off; a pending Suggested change (an unaccepted Update from Project
Records counts, so out-of-date numbers block); an open Code C comment; numbers and no check on the
current version; that check is Code C. A Revision freezes the view as it is issued (sorted JSON,
zlib-compressed) with its SHA-256, and freezes the Review report with it, so what was issued
stays exactly as issued.
"""

import hashlib
import json
import zlib
from uuid import uuid4

from qsone import copy
from qsone.deliverables import changes, events, ops, store
from qsone.deliverables import comments as threads
from qsone.records import audit
from qsone.records.project import Records, RecordsError

CODES = ("A", "B", "C")
CHECKER = threads.CHECKER
ENGINEER = ops.ENGINEER
_CHECK = ("id", "version_n", "code", "checker", "same_provider", "summary", "at")


def _dump(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode()


def _checks(conn, deliverable_id: str) -> list[dict]:
    """The Deliverable's checks, oldest first."""
    rows = conn.execute(
        f"SELECT {', '.join(_CHECK)} FROM checks WHERE deliverable_id = ? ORDER BY at, rowid",
        (deliverable_id,),
    ).fetchall()
    return [{**dict(zip(_CHECK, row, strict=True)), "same_provider": bool(row[4])} for row in rows]


# Checks.


def record_check(
    rec: Records,
    deliverable_id: str,
    *,
    version_n: int,
    code: str,
    checker: str,
    same_provider: bool,
    summary: str | None,
    comments: list[dict],
) -> str:
    """In-process only (the Checking QS): the check of Saved version `version_n` and its
    comments, in one write. Each comment is {"anchor", "body", "code": "B" | "C" | None}, stored
    as a Review comment by the Checking QS; a refusal names it (`comments[1].anchor.row`) and
    keeps nothing."""
    if code not in CODES:
        raise ValueError(f"a check's code is one of {CODES}")
    if not isinstance(comments, list) or not all(isinstance(c, dict) for c in comments):
        raise ValueError("a check's comments are a list of {anchor, body, code}")
    with rec.write(CHECKER) as conn:
        head = ops.deliverable(conn, deliverable_id)
        if not conn.execute(
            "SELECT 1 FROM versions WHERE deliverable_id = ? AND n = ?", (head["id"], version_n)
        ).fetchone():
            raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="version_n")
        row = {
            "id": uuid4().hex,
            "deliverable_id": head["id"],
            "version_n": version_n,
            "code": code,
            "checker": checker,
            "same_provider": int(bool(same_provider)),
            "summary": summary,
            "at": rec.clock(),
        }
        conn.execute(
            f"INSERT INTO checks ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
            tuple(row.values()),
        )
        audit.record(
            conn,
            at=row["at"],
            actor=CHECKER,
            action="create",
            table="checks",
            row_id=row["id"],
            before=None,
            after=row,
        )
        for i, comment in enumerate(comments):
            try:
                threads.check_kind("review", CHECKER, comment.get("code"))
                body = threads.check_body(comment.get("body"))
                anchor = threads.check_anchor(
                    conn, head, comment.get("anchor"), current=False, rec=rec
                )
            except RecordsError as e:
                e.field = f"comments[{i}]" + (f".{e.field}" if e.field else "")
                raise
            threads.insert(
                conn,
                rec,
                head,
                kind="review",
                anchor=anchor,
                body=body,
                actor=CHECKER,
                code=comment.get("code"),
                check_id=row["id"],
                version_n=version_n,
            )
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return row["id"]


def _not_in_client(rec: Records, deliverable_id: str, rows: list[dict]) -> list[dict]:
    """One open comment for each row not in the client's BOQ (`clientfile.imported`), on its
    row, in the Deliverable's language, with no code: it never blocks Sign-off by itself. A row
    the Checking QS has said this of before (whatever became of the comment) gets none again."""
    if not rows:
        return []
    with rec.read() as conn:
        language = ops.deliverable(conn, deliverable_id)["language"]
    said = {
        (t["anchor"].get("row"), t["body"])
        for t in threads.list_comments(rec, deliverable_id)
        if t["author"] == CHECKER and t["anchor"].get("type") == "row"
    }
    out = []
    for r in rows:
        text = copy.fill(copy.NOT_IN_CLIENT_BOQ, code=r["code"], description=r["description"])
        body = " ".join(text[language].split())
        if (r["row"], body) not in said:
            out.append({"anchor": {"type": "row", "row": r["row"]}, "body": body, "code": None})
    return out


def record_review(
    rec: Records, deliverable_id: str, review, *, version_n: int, not_in_client: list[dict] = ()
) -> str:
    """The hook for Plan 4's Checking QS: its `Review` (code, comments of {"about", "text"},
    checker model, same_provider) of Saved version `version_n`, recorded as a check. Each comment
    sits on the whole Deliverable, «about: text», and carries the check's code when it is B or C,
    so a Code C check's comments block Sign-off until the engineer closes them. `not_in_client`:
    the rows code found missing from the client's BOQ, each given its own comment on its row."""
    code = review.code if review.code in ("B", "C") else None
    comments = [
        {
            "anchor": {"type": "deliverable"},
            "body": f"{c['about']}: {c['text']}" if c.get("about") else c["text"],
            "code": code,
        }
        for c in review.comments
        if str(c.get("text", "")).strip()
    ]
    comments += _not_in_client(rec, deliverable_id, list(not_in_client))
    return record_check(
        rec,
        deliverable_id,
        version_n=version_n,
        code=review.code,
        checker=getattr(review.checker, "model", None) or str(review.checker),
        same_provider=review.same_provider,
        summary="\n".join(getattr(review, "checked", ())) or None,  # what the Checking QS checked
        comments=comments,
    )


# Close-out.


def _has_numbers(v: dict) -> bool:
    if v["kind"] == "pack":
        return True  # A tender submission always needs the Checking QS.
    if v["kind"] == "document":
        return bool(v["refs"])
    return v["total"] is not None or any(
        "number_id" in cell for row in v["rows"] for cell in row["cells"].values()
    )


def _gate(conn, rec: Records, head: dict) -> dict:
    """Inside a read or write: the view, what is open, and every reason Sign-off is refused, in
    the order `sign_off` refuses them."""
    v = store.view(rec, head["id"])
    (pending,) = conn.execute(
        "SELECT count(*) FROM changes WHERE deliverable_id = ? AND status = 'pending'",
        (head["id"],),
    ).fetchone()
    open_ = threads.read_threads(conn, head, status="open")
    blocking = [t for t in open_ if t["kind"] == "review" and t["code"] == "C"]
    checks = _checks(conn, head["id"])
    check = checks[-1] if checks else None  # the newest, as `store.status` reads it
    current = check is not None and check["version_n"] == v["version"]
    reasons = []
    if v["status"] == "signed_off":
        reasons.append(copy.ALREADY_SIGNED_OFF)
    if pending:
        reasons.append(copy.SIGNOFF_PENDING_CHANGES)
    if blocking:
        reasons.append(copy.SIGNOFF_OPEN_CODE_C)
    if _has_numbers(v) and not current:
        reasons.append(copy.SIGNOFF_NEEDS_CHECK)
    if current and check["code"] == "C":
        reasons.append(copy.SIGNOFF_CODE_C)
    return {
        "view": v,
        "pending": pending,
        "open": open_,
        "blocking": blocking,
        "check": check,
        "reasons": reasons,
    }


def closeout(rec: Records, deliverable_id: str) -> dict:
    """{"pending": n, "open": [thread], "blocking": [open Code C thread], "check": the newest
    check or None, "can_sign_off", "reasons": [{en, ar}]}, with the Update from Project Records
    made current first."""
    changes.refresh_records_change(rec, deliverable_id)
    with rec.read() as conn:
        gate = _gate(conn, rec, ops.deliverable(conn, deliverable_id))
    return {
        "pending": gate["pending"],
        "open": gate["open"],
        "blocking": gate["blocking"],
        "check": gate["check"],
        "can_sign_off": not gate["reasons"],
        "reasons": gate["reasons"],
    }


# Revisions and Sign-off.


def _report(conn, head: dict, revision: dict, v: dict) -> dict:
    accepted, rejected = conn.execute(
        "SELECT count(*) FILTER (WHERE status = 'accepted'),"
        " count(*) FILTER (WHERE status = 'rejected') FROM changes WHERE deliverable_id = ?",
        (head["id"],),
    ).fetchone()
    signed = revision["signed_off"]
    return {
        "deliverable": {
            "id": head["id"],
            "kind": head["kind"],
            "title": head["title"],
            "language": head["language"],
        },
        "revision": revision,
        "checks": _checks(conn, head["id"]),
        "threads": threads.read_threads(conn, head),
        "changes": {"accepted": accepted, "rejected": rejected},
        "signed_off": {"by": revision["issued_by"], "at": revision["issued_at"]}
        if signed
        else None,
        "sample": v["sample"],
    }


def _issue(rec: Records, deliverable_id: str, *, actor: str, signed: bool) -> int:
    if actor != ENGINEER:
        raise ValueError("only the engineer issues a Revision or signs off")
    changes.refresh_records_change(rec, deliverable_id)
    with rec.write(actor) as conn:
        head = ops.deliverable(conn, deliverable_id)
        gate = _gate(conn, rec, head)
        v = gate["view"]
        if signed and gate["reasons"]:
            raise RecordsError(gate["reasons"][0], status=409)
        if v["status"] == "signed_off":
            raise RecordsError(copy.ALREADY_SIGNED_OFF, status=409)
        (no,) = conn.execute(
            "SELECT coalesce(max(no), 0) + 1 FROM revisions WHERE deliverable_id = ?",
            (head["id"],),
        ).fetchone()
        at = rec.clock()
        # The view as it reads once this Revision is issued.
        snapshot = {**v, "revision": {"no": no, "version": v["version"], "signed_off": signed}}
        if signed:
            snapshot["status"] = "signed_off"
        body = _dump(snapshot)
        revision = {
            "deliverable_id": head["id"],
            "no": no,
            "version_n": v["version"],
            "issued_at": at,
            "issued_by": actor,
            "signed_off": signed,
            "sha256": hashlib.sha256(body).hexdigest(),
        }
        conn.execute(
            "INSERT INTO revisions (deliverable_id, no, version_n, issued_at, issued_by,"
            " signed_off, snapshot, sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                head["id"],
                no,
                v["version"],
                at,
                actor,
                int(signed),
                zlib.compress(body),
                revision["sha256"],
            ),
        )
        conn.execute("UPDATE deliverables SET updated_at = ? WHERE id = ?", (at, head["id"]))
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="create",
            table="revisions",
            row_id=f"{head['id']}/{no}",
            before=None,
            after=revision,
        )
        report = _report(conn, head, revision, v)
        conn.execute(
            "INSERT INTO review_reports (deliverable_id, revision_no, body, at)"
            " VALUES (?, ?, ?, ?)",
            (head["id"], no, zlib.compress(_dump(report)), at),
        )
        audit.record(
            conn,
            at=at,
            actor=actor,
            action="create",
            table="review_reports",
            row_id=f"{head['id']}/{no}",
            before=None,
            after={"deliverable_id": head["id"], "revision_no": no},
        )
    events.publish_deliverable(rec, rec.id, deliverable_id)
    return no


def sign_off(rec: Records, deliverable_id: str, *, actor: str) -> int:
    """Signs off the current version: issues the next Revision with `signed_off` and freezes its
    Review report, in one write; returns the Revision number. Refuses (409) with the first
    reason: ALREADY_SIGNED_OFF, SIGNOFF_PENDING_CHANGES, SIGNOFF_OPEN_CODE_C, SIGNOFF_NEEDS_CHECK,
    SIGNOFF_CODE_C. Only the engineer signs off (ValueError otherwise)."""
    return _issue(rec, deliverable_id, actor=actor, signed=True)


def issue_revision(rec: Records, deliverable_id: str, *, actor: str) -> int:
    """Issues the next Revision of the current version without signing it off (a Rev for
    comments): the same snapshot and Review report, with no Sign-off gate. Refuses a version
    already signed off. Only the engineer issues one (ValueError otherwise)."""
    return _issue(rec, deliverable_id, actor=actor, signed=False)


def review_report(rec: Records, deliverable_id: str, revision_no: int) -> dict:
    """The Review report frozen with Revision `revision_no`: the Deliverable, the Revision, the
    checks (code, checker model, same-provider), each thread with its replies and status, the
    counts of accepted and rejected changes, and who signed off and when (None for a Revision
    that was not signed off)."""
    with rec.read() as conn:
        ops.deliverable(conn, deliverable_id)
        found = conn.execute(
            "SELECT body FROM review_reports WHERE deliverable_id = ? AND revision_no = ?",
            (deliverable_id, revision_no),
        ).fetchone()
    if found is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="revision")
    return json.loads(zlib.decompress(found[0]))
