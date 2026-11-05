"""Comments, checks, Revisions, Close-out and Sign-off (synthetic «عينة» data only)."""

import hashlib
import json
import zlib
from dataclasses import dataclass
from string import Formatter

import pytest

from qsone import copy
from qsone.deliverables import events
from qsone.deliverables.changes import accept_mine, propose, reject
from qsone.deliverables.comments import add, close, fix_text, list_comments, reopen, reply
from qsone.deliverables.review import (
    closeout,
    issue_revision,
    record_check,
    record_review,
    review_report,
    sign_off,
)
from qsone.deliverables.store import status, view
from qsone.records import db, ledger
from qsone.records.project import RecordsError
from tests.samples import sample_document, sample_sheet, sample_source

# Helpers ------------------------------------------------------------------------------------


def row_by_code(rec, d: str, code: str) -> dict:
    return next(r for r in view(rec, d)["rows"] if r.get("code") == code)


def set_rate(rec, d: str, code: str, value: str, **extra) -> dict:
    row = row_by_code(rec, d, code)
    return {"op": "set_number", "row": row["id"], "name": "rate", "value": value, **extra}


def edit(rec, d: str, op: dict) -> int:
    """The engineer's own edit, proposed and accepted: the new version."""
    propose(rec, d, [op], actor="engineer")
    return accept_mine(rec, d, actor="engineer")["version"]


def check(rec, d: str, code: str = "A", comments: list | None = None) -> str:
    return record_check(
        rec,
        d,
        version_n=view(rec, d)["version"],
        code=code,
        checker="model-sample",
        same_provider=False,
        summary="مراجعة - عينة",
        comments=comments or [],
    )


def letter_block(rec, d: str) -> dict:
    return next(b for b in view(rec, d)["blocks"] if "حالياً" in json.dumps(b, ensure_ascii=False))


def paragraph(text: str) -> dict:
    return {"type": "p", "children": [{"text": text}]}


def revision_row(rec, d: str, no: int) -> tuple:
    with rec.read() as c:
        return c.execute(
            "SELECT snapshot, sha256, signed_off, version_n FROM revisions"
            " WHERE deliverable_id = ? AND no = ?",
            (d, no),
        ).fetchone()


# Two kinds of comment -----------------------------------------------------------------------


def test_two_kinds_of_comment(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")["id"]
    note = add(
        rec,
        d,
        kind="note",
        anchor={"type": "cell", "row": row, "column": "rate"},
        body="السعر من عرض المورّد - عينة",
        actor="estimator",
    )
    with pytest.raises(RecordsError) as e:
        add(rec, d, kind="note", anchor={"type": "deliverable"}, body="x", actor="engineer")
    assert e.value.text == copy.COMMENT_KIND_NOT_ALLOWED
    with pytest.raises(RecordsError):  # One's note never carries a code
        add(
            rec, d, kind="note", anchor={"type": "deliverable"}, body="x", actor="lead_qs", code="C"
        )
    with pytest.raises(RecordsError):  # a Review comment is the engineer's or the Checking QS's
        add(rec, d, kind="review", anchor={"type": "deliverable"}, body="x", actor="lead_qs")
    rid = add(
        rec,
        d,
        kind="review",
        anchor={
            "type": "range",
            "from": {"row": row, "column": "quantity"},
            "to": {"row": row, "column": "rate"},
        },
        body="راجع الكمية",
        actor="engineer",
        code="C",
    )
    threads = list_comments(rec, d)
    assert [c["kind"] for c in threads] == ["note", "review"]
    assert [c["id"] for c in threads] == [note, rid]
    assert threads[1]["code"] == "C" and threads[1]["status"] == "open"
    assert threads[1]["anchor_now"] == threads[1]["anchor"] and threads[1]["version_n"] == 1
    assert view(rec, d)["open_comments"] == 2


def test_a_comment_needs_text_and_a_real_place(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")["id"]

    def refused(anchor, body="راجع - عينة"):
        with pytest.raises(RecordsError) as e:
            add(rec, d, kind="review", anchor=anchor, body=body, actor="engineer")
        return e.value.text, e.value.field

    assert refused({"type": "deliverable"}, body="  ") == (copy.COMMENT_NEEDS_TEXT, "body")
    assert refused({"type": "cell", "row": "E12", "column": "rate"}) == (
        copy.ANCHOR_NOT_FOUND,
        "anchor.row",
    )  # never an A1 address
    assert refused({"type": "cell", "row": row, "column": "floor"}) == (
        copy.ANCHOR_NOT_FOUND,
        "anchor.column",
    )
    assert refused({"type": "text", "block": row, "start": 0, "end": 2, "quote": "x"})[1] == (
        "anchor.type"
    )  # a Sheet takes cell, range, row and deliverable anchors
    assert refused({"type": "row"})[1] == "anchor.row"
    with pytest.raises(RecordsError) as e:
        add(
            rec, "0" * 32, kind="review", anchor={"type": "deliverable"}, body="x", actor="engineer"
        )
    assert e.value.text == copy.DELIVERABLE_NOT_FOUND


def test_replies_close_and_reopen(rec):
    d = sample_sheet(rec)
    note = add(
        rec, d, kind="note", anchor={"type": "deliverable"}, body="ملحوظة - عينة", actor="lead_qs"
    )
    answer = reply(rec, note, body="تمام - عينة", actor="engineer")
    rid = add(
        rec,
        d,
        kind="review",
        anchor={"type": "deliverable"},
        body="ناقص بند - عينة",
        actor="engineer",
        code="C",
    )
    [thread, _] = list_comments(rec, d)
    assert [r["id"] for r in thread["replies"]] == [answer]
    assert thread["replies"][0]["kind"] == "note" and thread["replies"][0]["author"] == "engineer"
    with pytest.raises(RecordsError) as e:
        reply(rec, rid, body=" ", actor="engineer")
    assert e.value.text == copy.COMMENT_NEEDS_TEXT
    with pytest.raises(RecordsError) as e:
        reply(rec, "0" * 32, body="x", actor="engineer")
    assert e.value.text == copy.COMMENT_NOT_FOUND
    with pytest.raises(ValueError):  # the team cannot close a Review comment to unblock Sign-off
        close(rec, rid, actor="lead_qs")
    close(rec, rid, actor="engineer")
    assert [c["id"] for c in list_comments(rec, d, status="open")] == [note]
    [closed] = list_comments(rec, d, status="closed")
    assert closed["closed_by"] == "engineer" and closed["closed_at"]
    assert view(rec, d)["open_comments"] == 1
    reopen(rec, rid, actor="engineer")
    assert {c["id"] for c in list_comments(rec, d, status="open")} == {note, rid}
    assert list_comments(rec, d, status="open")[1]["closed_at"] is None


def test_comment_writes_are_audited_and_published(rec):
    d = sample_sheet(rec)
    seen = []
    stop = events.listen(lambda project, event: seen.append((project, event)))
    try:
        c = add(
            rec, d, kind="review", anchor={"type": "deliverable"}, body="x - عينة", actor="engineer"
        )
        close(rec, c, actor="engineer")
    finally:
        stop()
    assert [e["deliverable"]["id"] for _, e in seen] == [d, d]
    assert seen[0][1]["deliverable"]["open_comments"] == 1
    assert seen[1][1]["deliverable"]["open_comments"] == 0
    with rec.read() as conn:
        actions = conn.execute(
            "SELECT action FROM audit WHERE table_name = 'comments' AND row_id = ? ORDER BY id",
            (c,),
        ).fetchall()
    assert actions == [("create",), ("update",)]


# Checks --------------------------------------------------------------------------------------


def test_a_check_and_its_comments_are_one_write(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")["id"]
    with pytest.raises(RecordsError):  # one bad comment: nothing is kept
        record_check(
            rec,
            d,
            version_n=1,
            code="B",
            checker="model-x",
            same_provider=True,
            summary="",
            comments=[
                {"anchor": {"type": "deliverable"}, "body": "تمام - عينة"},
                {"anchor": {"type": "cell", "row": "nope", "column": "rate"}, "body": "x"},
            ],
        )
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM checks").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM comments").fetchone()[0] == 0
    check_id = record_check(
        rec,
        d,
        version_n=1,
        code="B",
        checker="model-x",
        same_provider=True,
        summary="مقبول",
        comments=[
            {
                "anchor": {"type": "cell", "row": row, "column": "rate"},
                "body": "راجع الفئة",
                "code": "B",
            },
            {"anchor": {"type": "deliverable"}, "body": "ملاحظة عامة - عينة"},
        ],
    )
    threads = list_comments(rec, d)
    assert [(c["kind"], c["author"], c["code"], c["check_id"]) for c in threads] == [
        ("review", "checking_qs", "B", check_id),
        ("review", "checking_qs", None, check_id),
    ]
    assert status(rec, d) == {
        "status": "checked",
        "code": "B",
        "same_provider": True,
        "off_desk": False,
    }
    with pytest.raises(ValueError):
        record_check(
            rec, d, version_n=1, code="D", checker="m", same_provider=False, summary="", comments=[]
        )
    with pytest.raises(RecordsError):  # a version that was never saved
        record_check(
            rec, d, version_n=9, code="A", checker="m", same_provider=False, summary="", comments=[]
        )


@dataclass(frozen=True)
class _Choice:  # Plan 4's ModelChoice, as the hook reads it
    connector: str
    model: str


@dataclass(frozen=True)
class _Review:  # Plan 4's Review, as the hook reads it
    code: str
    comments: tuple
    checker: _Choice
    same_provider: bool
    round: int


def test_plan_4_review_is_recorded_as_a_check(rec):
    d = sample_sheet(rec)
    got = _Review(
        code="C",
        comments=(
            {"about": "03/02", "text": "الفئة أعلى من السوق - عينة"},
            {"about": "", "text": "x"},
        ),
        checker=_Choice(connector="anthropic", model="model-sample"),
        same_provider=True,
        round=1,
    )
    check_id = record_review(rec, d, got, version_n=1)
    out = closeout(rec, d)
    assert out["check"] == {
        "id": check_id,
        "version_n": 1,
        "code": "C",
        "checker": "model-sample",
        "same_provider": True,
        "summary": None,
        "at": out["check"]["at"],
    }
    assert [c["body"] for c in out["blocking"]] == ["03/02: الفئة أعلى من السوق - عينة", "x"]
    assert all(c["code"] == "C" and c["anchor"] == {"type": "deliverable"} for c in out["blocking"])
    passed = _Review(
        code="A",
        comments=({"about": "", "text": "سليم"},),
        checker=got.checker,
        same_provider=False,
        round=2,
    )
    record_review(rec, d, passed, version_n=1)
    assert list_comments(rec, d)[-1]["code"] is None  # Code A comments never block


# Close-out and Sign-off ----------------------------------------------------------------------


def test_sign_off_is_blocked_until_the_rules_hold(rec):
    d = sample_sheet(rec)
    assert closeout(rec, d)["reasons"] == [copy.SIGNOFF_NEEDS_CHECK]
    record_check(
        rec,
        d,
        version_n=1,
        code="C",
        checker="model-x",
        same_provider=False,
        summary="",
        comments=[{"anchor": {"type": "deliverable"}, "body": "الفئة ناقصة", "code": "C"}],
    )
    with pytest.raises(RecordsError) as e:
        sign_off(rec, d, actor="engineer")
    assert e.value.text == copy.SIGNOFF_OPEN_CODE_C and e.value.status == 409
    out = closeout(rec, d)
    assert out["reasons"] == [copy.SIGNOFF_OPEN_CODE_C, copy.SIGNOFF_CODE_C]
    assert not out["can_sign_off"] and [c["body"] for c in out["blocking"]] == ["الفئة ناقصة"]
    [c] = out["blocking"]
    close(rec, c["id"], actor="engineer")
    with pytest.raises(RecordsError) as e:
        sign_off(rec, d, actor="engineer")
    assert e.value.text == copy.SIGNOFF_CODE_C
    v2 = edit(rec, d, set_rate(rec, d, "03/02", "40000"))  # the fix
    assert status(rec, d)["status"] == "draft" and closeout(rec, d)["reasons"] == [
        copy.SIGNOFF_NEEDS_CHECK
    ]
    record_check(
        rec,
        d,
        version_n=v2,
        code="B",
        checker="model-x",
        same_provider=False,
        summary="",
        comments=[],
    )
    out = closeout(rec, d)
    assert out["can_sign_off"] and out["reasons"] == [] and out["pending"] == 0
    assert sign_off(rec, d, actor="engineer") == 1
    assert status(rec, d)["status"] == "signed_off"
    v = view(rec, d)
    assert v["revision"] == {"no": 1, "version": v2, "signed_off": True}
    assert closeout(rec, d)["reasons"] == [copy.ALREADY_SIGNED_OFF]
    with pytest.raises(RecordsError) as e:
        sign_off(rec, d, actor="engineer")
    assert e.value.text == copy.ALREADY_SIGNED_OFF


def test_a_pending_change_blocks_sign_off(rec):
    d = sample_sheet(rec)
    check(rec, d)
    [ch] = propose(rec, d, [set_rate(rec, d, "1-1", "15")], actor="engineer")
    with pytest.raises(RecordsError) as e:
        sign_off(rec, d, actor="engineer")
    assert e.value.text == copy.SIGNOFF_PENDING_CHANGES
    reject(rec, d, [ch.id], actor="engineer")
    rate = row_by_code(rec, d, "03/02")["cells"]["rate"]
    ledger.correct_number(  # out of date numbers block too: the Update from Project Records waits
        rec,
        rate["number_id"],
        value="41000",
        reason="عرض جديد - عينة",
        source_id=sample_source(rec),
        dated="2026-11-04",
        actor="estimator",
    )
    out = closeout(rec, d)
    assert out["pending"] == 1 and out["reasons"] == [copy.SIGNOFF_PENDING_CHANGES]
    with pytest.raises(RecordsError) as e:
        sign_off(rec, d, actor="engineer")
    assert e.value.text == copy.SIGNOFF_PENDING_CHANGES


def test_a_note_never_blocks_but_an_open_code_c_does(rec):
    d = sample_sheet(rec)
    check(rec, d, "A")
    add(rec, d, kind="note", anchor={"type": "deliverable"}, body="ملحوظة - عينة", actor="lead_qs")
    add(
        rec,
        d,
        kind="review",
        anchor={"type": "deliverable"},
        body="ملحوظة B - عينة",
        actor="engineer",
        code="B",
    )
    assert closeout(rec, d)["can_sign_off"]
    c = add(
        rec,
        d,
        kind="review",
        anchor={"type": "deliverable"},
        body="لازم يتصلح - عينة",
        actor="engineer",
        code="C",
    )
    out = closeout(rec, d)
    assert out["reasons"] == [copy.SIGNOFF_OPEN_CODE_C] and len(out["open"]) == 3
    assert [x["id"] for x in out["blocking"]] == [c]
    close(rec, c, actor="engineer")
    assert sign_off(rec, d, actor="engineer") == 1


def test_a_document_without_numbers_needs_no_check(rec):
    from qsone.deliverables import store

    d = store.create(
        rec,
        kind="document",
        variant="letter",
        title="خطاب - عينة",
        language="ar",
        actor="lead_qs",
        blocks=[paragraph("نص بدون أرقام - عينة")],
    )
    assert closeout(rec, d)["reasons"] == []
    assert sign_off(rec, d, actor="engineer") == 1
    letter = sample_document(rec, sample_sheet(rec))  # its total is a number: it needs a check
    assert closeout(rec, letter)["reasons"] == [copy.SIGNOFF_NEEDS_CHECK]


def test_only_the_engineer_signs_off(rec):
    d = sample_sheet(rec)
    check(rec, d)
    for actor in ("lead_qs", "checking_qs"):
        with pytest.raises(ValueError):
            sign_off(rec, d, actor=actor)
        with pytest.raises(ValueError):
            issue_revision(rec, d, actor=actor)
    with rec.read() as conn:
        assert conn.execute("SELECT count(*) FROM revisions").fetchone()[0] == 0


def test_signed_off_revision_never_changes(rec):
    d = sample_sheet(rec)
    check(rec, d)
    seen = []
    stop = events.listen(lambda project, event: seen.append(event))
    try:
        no = sign_off(rec, d, actor="engineer")
    finally:
        stop()
    assert seen[-1]["deliverable"]["status"] == "signed_off"
    frozen = view(rec, d, revision=no)
    snapshot, sha, signed, version_n = revision_row(rec, d, no)
    assert signed == 1 and version_n == 1
    body = zlib.decompress(snapshot)
    assert hashlib.sha256(body).hexdigest() == sha
    assert body == json.dumps(frozen, sort_keys=True, ensure_ascii=False).encode()
    assert frozen["status"] == "signed_off" and frozen["revision"] == {
        "no": 1,
        "version": 1,
        "signed_off": True,
    }
    current = view(rec, d)
    for key in ("rows", "total", "sources", "version", "status", "revision"):
        assert frozen[key] == current[key], key
    edit(rec, d, set_rate(rec, d, "03/02", "40000"))
    assert view(rec, d)["total"] != frozen["total"] and status(rec, d)["status"] == "draft"
    assert view(rec, d, revision=no) == frozen and revision_row(rec, d, no)[:2] == (snapshot, sha)
    with rec.write("engineer") as conn, pytest.raises(db.IntegrityError):
        conn.execute("UPDATE revisions SET sha256 = 'x' WHERE deliverable_id = ?", (d,))


def test_issue_revision_does_not_sign_off(rec):
    d = sample_sheet(rec)
    assert issue_revision(rec, d, actor="engineer") == 1  # Rev issued for comments: no gate
    assert status(rec, d)["status"] == "draft"
    assert view(rec, d, revision=1)["revision"] == {"no": 1, "version": 1, "signed_off": False}
    assert revision_row(rec, d, 1)[2] == 0
    check(rec, d)
    assert sign_off(rec, d, actor="engineer") == 2
    with pytest.raises(RecordsError) as e:
        issue_revision(rec, d, actor="engineer")
    assert e.value.text == copy.ALREADY_SIGNED_OFF


def test_review_report_lists_threads_and_codes(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")["id"]
    record_check(
        rec,
        d,
        version_n=1,
        code="C",
        checker="model-x",
        same_provider=True,
        summary="ناقص",
        comments=[
            {
                "anchor": {"type": "cell", "row": row, "column": "rate"},
                "body": "الفئة ناقصة",
                "code": "C",
            }
        ],
    )
    [c] = list_comments(rec, d)
    reply(rec, c["id"], body="اتصلحت - عينة", actor="engineer")
    close(rec, c["id"], actor="engineer")
    [no] = propose(
        rec, d, [set_rate(rec, d, "1-1", "15", source_id=sample_source(rec))], actor="lead_qs"
    )
    reject(rec, d, [no.id], actor="engineer")
    v2 = edit(rec, d, set_rate(rec, d, "03/02", "40000"))
    record_check(
        rec,
        d,
        version_n=v2,
        code="B",
        checker="model-y",
        same_provider=False,
        summary="مقبول",
        comments=[],
    )
    rev = sign_off(rec, d, actor="engineer")
    report = review_report(rec, d, rev)
    assert (
        report["deliverable"]["id"] == d and report["deliverable"]["title"] == "جدول الكميات - عينة"
    )
    assert report["revision"]["no"] == rev and report["revision"]["version_n"] == v2
    assert report["revision"]["signed_off"] is True and report["revision"]["sha256"]
    assert [(k["code"], k["checker"], k["same_provider"]) for k in report["checks"]] == [
        ("C", "model-x", True),
        ("B", "model-y", False),
    ]
    [thread] = report["threads"]
    assert thread["status"] == "closed" and thread["code"] == "C"
    assert [r["body"] for r in thread["replies"]] == ["اتصلحت - عينة"]
    assert report["changes"] == {"accepted": 1, "rejected": 1}
    assert report["signed_off"]["by"] == "engineer" and report["signed_off"]["at"]
    # the report is frozen with the Revision: later comments never reach it
    add(
        rec, d, kind="review", anchor={"type": "deliverable"}, body="بعد الاعتماد", actor="engineer"
    )
    assert review_report(rec, d, rev) == report
    with pytest.raises(RecordsError):
        review_report(rec, d, 9)


# Anchors that follow the Deliverable ---------------------------------------------------------


def test_text_anchor_follows_its_quote(rec):
    d = sample_document(rec, sample_sheet(rec))
    block = letter_block(rec, d)
    text = "الأسعار سارية حالياً لمدة ٣٠ يوماً"
    start = text.index("حالياً")
    anchor = {
        "type": "text",
        "block": block["id"],
        "start": start,
        "end": start + 6,
        "quote": "حالياً",
    }
    c = add(rec, d, kind="review", anchor=anchor, body="وضّح المدة - عينة", actor="engineer")
    with pytest.raises(RecordsError) as e:  # a quote that is not in the block
        add(
            rec,
            d,
            kind="review",
            anchor={**anchor, "quote": "غير موجود"},
            body="x",
            actor="engineer",
        )
    assert e.value.text == copy.ANCHOR_NOT_FOUND
    prefix = "نؤكد أن "
    edit(rec, d, {"op": "set_block", "block": block["id"], "node": paragraph(prefix + text)})
    [thread] = list_comments(rec, d)
    assert thread["anchor"] == anchor
    shift = len(prefix)
    assert thread["anchor_now"] == {**anchor, "start": start + shift, "end": start + shift + 6}
    edit(
        rec,
        d,
        {"op": "set_block", "block": block["id"], "node": paragraph("الأسعار سارية لمدة ٣٠ يوماً")},
    )
    [thread] = list_comments(rec, d)
    assert thread["anchor_now"] == {"type": "row", "block": block["id"], "moved": True}
    edit(rec, d, {"op": "remove_block", "block": block["id"]})
    [thread] = list_comments(rec, d)
    assert thread["anchor_now"] == {"type": "deliverable", "moved": True} and thread["id"] == c


def test_removed_row_comment_is_moved_not_lost(rec):
    d = sample_sheet(rec)
    row = row_by_code(rec, d, "03/02")
    cell = {"type": "cell", "row": row["id"], "column": "rate"}
    c = add(rec, d, kind="review", anchor=cell, body="راجع - عينة", actor="engineer", code="C")
    other = row_by_code(rec, d, "1-1")["id"]
    span = {
        "type": "range",
        "from": {"row": other, "column": "rate"},
        "to": {"row": row["id"], "column": "rate"},
    }
    r = add(rec, d, kind="review", anchor=span, body="راجع المدى - عينة", actor="engineer")
    edit(rec, d, {"op": "remove_row", "row": row["id"]})
    threads = {t["id"]: t for t in list_comments(rec, d)}
    assert threads[c]["anchor_now"] == {"type": "deliverable", "moved": True}
    assert threads[c]["anchor"] == cell and threads[c]["status"] == "open"
    assert threads[r]["anchor_now"] == {"type": "row", "row": other, "moved": True}
    assert closeout(rec, d)["reasons"][0] == copy.SIGNOFF_OPEN_CODE_C  # still blocks


def test_fix_text_names_the_place_and_the_ids(rec):
    d = sample_sheet(rec)
    issue_revision(rec, d, actor="engineer")
    row = row_by_code(rec, d, "03/02")
    body = "الفئة أقل من عرض المورّد - عينة"
    c = add(
        rec,
        d,
        kind="review",
        anchor={"type": "cell", "row": row["id"], "column": "rate"},
        body=body,
        actor="engineer",
        code="C",
    )
    text = fix_text(rec, c, lang="ar")
    for part in (c, d, row["id"], "Rev 1", "«03/02»", "«الفئة»", body):
        assert part in text, part
    english = fix_text(rec, c, lang="en")
    assert c in english and "Rev 1" in english and "«Rate»" in english and body in english
    assert list_comments(rec, d)[0]["fix_asked_at"]
    with pytest.raises(RecordsError):
        fix_text(rec, "0" * 32, lang="ar")


def test_fix_text_for_a_passage_quotes_it(rec):
    d = sample_document(rec, sample_sheet(rec))
    block = letter_block(rec, d)
    anchor = {"type": "text", "block": block["id"], "start": 0, "end": 7, "quote": "الأسعار"}
    c = add(rec, d, kind="review", anchor=anchor, body="راجع - عينة", actor="engineer")
    text = fix_text(rec, c, lang="ar")
    assert "«الأسعار»" in text and "النسخة 1" in text and block["id"] in text


def test_review_texts_have_both_languages_and_the_same_placeholders():
    def fields(s: str) -> set[str]:
        return {f for _, f, _, _ in Formatter().parse(s) if f is not None}

    for name in [
        "COMMENT_KIND_NOT_ALLOWED",
        "FIX_REQUEST",
        "FIX_AT_REVISION",
        "FIX_AT_VERSION",
        "FIX_PLACE_CELL",
        "FIX_PLACE_RANGE",
        "FIX_PLACE_ROW",
        "FIX_PLACE_TEXT",
        "FIX_PLACE_DELIVERABLE",
    ]:
        text = getattr(copy, name)
        assert set(text) == {"en", "ar"} and text["en"].strip() and text["ar"].strip(), name
        assert fields(text["en"]) == fields(text["ar"]), name
