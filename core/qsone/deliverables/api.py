"""The Deliverables in the core API: the screen's Project Index, viewers, review, exports and the
client's file (Plan 6). All paths start `/projects/{p}`.

Every route needs the bearer secret (the app checks it) and an open project. The actor is always
the engineer at the screen: there is no route to record a check, to write One's note or to
propose as an agent. An id that is not 32 lower-case hex digits is 404 before anything is read.
A refusal is `{"error": {en, ar}, "field": str | None}` with its status (404, 409 or 422).
Heavy work (views, exports, the fill) runs in the thread pool. Only ids are ever logged.
"""

import json
import re
from dataclasses import asdict
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from qsone import copy, export
from qsone.clientfile import fill
from qsone.deliverables import changes, comments, compare, ops, revert, review, store
from qsone.projects import ACTOR, Projects
from qsone.records.project import Records, RecordsError
from qsone.undo import Trash

_ID = re.compile(r"[0-9a-f]{32}")
_AT = re.compile(
    r"([vr]):([1-9][0-9]{0,8})"
)  # compare's "v:3" (a Saved version), "r:2" (a Revision)
_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}
_EXPORTS = {
    ("sheet", "xlsx"): export.to_xlsx,
    ("sheet", "pdf"): export.to_pdf,
    ("document", "docx"): export.to_docx,
    ("document", "pdf"): export.to_pdf,
}


def _refusal(e: RecordsError) -> JSONResponse:
    return JSONResponse({"error": e.text, "field": e.field}, status_code=e.status)


def _known(value: str, text: dict, field: str) -> str:
    if not _ID.fullmatch(value):
        raise RecordsError(text, status=404, field=field)
    return value


def _file(data: bytes, name: str) -> Response:
    """The bytes, with the name as plain ASCII and as RFC 5987 UTF-8 (Arabic names)."""
    ascii_name = name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "_")
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
    media = _TYPES.get(name.rpartition(".")[2].lower(), "application/octet-stream")
    return Response(data, media_type=media, headers={"content-disposition": disposition})


# The answers, each run in the thread pool with the open project.


def change_json(change: changes.Change) -> dict:
    """A Suggested change as the screen reads it. A Document block change also carries
    `segments`, the core's word difference old → new, so the screen never diffs."""
    out = asdict(change)
    kind = change.op["op"]
    if kind in ops.DOC_OPS:
        was = compare.block_text(change.before["node"]) if change.before else ""
        new = compare.block_text(change.op["node"]) if "node" in change.op else was
        out["segments"] = compare.segments(was, "" if kind == "remove_block" else new)
    return out


def current_view(rec: Records, deliverable_id: str, version=None, revision=None) -> dict:
    """The view; the latest one with its Update from Project Records made current first, so its
    `pending` counts it."""
    v = store.view(rec, deliverable_id, version=version, revision=revision)
    if version is None and revision is None and v["records_moved"]:
        changes.refresh_records_change(rec, deliverable_id)
        v = store.view(rec, deliverable_id)
    return v


def _with_sources(rec: Records, found: list[changes.Change]) -> list[dict]:
    """Each change as the screen reads it, with `sources`: the source of every number it shows
    that is in Project Records (a number the engineer types gets its source only when accepted)."""
    out = [change_json(c) for c in found]
    wanted: set[str] = set()
    for change in out:
        cells = [change["before"], change["after"], *(f["after"] for f in change["follows"])]
        wanted |= {c["source"] for c in cells if isinstance(c, dict) and c.get("source")}
    sources = store.sources_of(rec, sorted(wanted))
    for change in out:
        cells = [change["before"], change["after"], *(f["after"] for f in change["follows"])]
        ids = {c["source"] for c in cells if isinstance(c, dict) and c.get("source")}
        change["sources"] = {s: sources[s] for s in sorted(ids) if s in sources}
    return out


def _changes(rec: Records, d: str, status: str | None) -> dict:
    found = (
        changes.pending(rec, d)
        if status == "pending"
        else changes.list_changes(rec, d, status=status)
    )
    return {"changes": _with_sources(rec, found)}


def _propose(rec: Records, d: str, body: dict) -> dict:
    reason = body.get("reason")
    made = changes.propose(
        rec, d, body.get("ops"), actor=ACTOR, reason=reason if isinstance(reason, str) else None
    )
    return {"changes": _with_sources(rec, made)}


def _accept(rec: Records, d: str, body: dict) -> dict:
    if body.get("mine") is True:
        out = changes.accept_mine(rec, d, actor=ACTOR)
    else:
        out = changes.accept(rec, d, body.get("ids"), actor=ACTOR)
    # whether Undo can take it back (not an Update from Project Records); said to the route only
    return {
        **out,
        "_undoable": out["version"] is not None and revert.undoable(rec, d, out["version"]),
    }


def _versions(rec: Records, d: str) -> dict:
    with rec.read() as conn:
        ops.deliverable(conn, d)
        versions = conn.execute(
            "SELECT n, at, by, changes FROM versions WHERE deliverable_id = ? ORDER BY n", (d,)
        ).fetchall()
        revisions = conn.execute(
            "SELECT no, version_n, issued_at, signed_off FROM revisions WHERE deliverable_id = ?"
            " ORDER BY no",
            (d,),
        ).fetchall()
    return {
        "versions": [
            {"n": n, "at": at, "by": by, "changes": json.loads(ids)} for n, at, by, ids in versions
        ],
        "revisions": [
            {"no": no, "version_n": v, "issued_at": at, "signed_off": bool(signed)}
            for no, v, at, signed in revisions
        ],
    }


def _view_at(rec: Records, d: str, at: str | None, field: str) -> dict:
    found = _AT.fullmatch(at or "")
    if found is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field=field)
    n = int(found[2])
    if found[1] == "v":
        return store.view(rec, d, version=n)
    return store.view(rec, d, revision=n)


def _compare(rec: Records, d: str, start: str | None, end: str | None) -> dict:
    return compare.compare(_view_at(rec, d, start, "from"), _view_at(rec, d, end, "to"))


def _thread(rec: Records, comment_id: str) -> dict:
    """The thread the comment belongs to."""
    with rec.read() as conn:
        found = conn.execute(
            "SELECT coalesce(parent_id, id), deliverable_id FROM comments WHERE id = ?",
            (comment_id,),
        ).fetchone()
    if found is None:
        raise RecordsError(copy.COMMENT_NOT_FOUND, status=404, field="comment")
    root, d = found
    return next(t for t in comments.list_comments(rec, d) if t["id"] == root)


def _comment(rec: Records, d: str, body: dict) -> dict:
    code = body.get("code")
    made = comments.add(
        rec,
        d,
        kind="review",  # the screen never writes One's notes
        anchor=body.get("anchor"),
        body=body.get("body"),
        actor=ACTOR,
        code=code if code is None or isinstance(code, str) else str(code),
    )
    return _thread(rec, made)


def _reply(rec: Records, c: str, body: dict) -> dict:
    return _thread(rec, comments.reply(rec, c, body=body.get("body"), actor=ACTOR))


def _close(rec: Records, c: str, status: str) -> dict:
    (comments.close if status == "closed" else comments.reopen)(rec, c, actor=ACTOR)
    return _thread(rec, c)


def _export(rec: Records, d: str, format_: str, revision: int | None) -> Response:
    v = current_view(rec, d, revision=revision)
    make = _EXPORTS.get((v["kind"], format_))
    if make is None:
        raise RecordsError(copy.EXPORT_FORMAT_NOT_ALLOWED, status=422, field="format")
    return _file(make(v), export.file_name(v, format_))


def _review_report(rec: Records, d: str, revision: int | None) -> Response:
    if revision is None:
        raise RecordsError(copy.DELIVERABLE_NOT_FOUND, status=404, field="revision")
    report = review.review_report(rec, d, revision)
    v = store.view(rec, d, revision=revision)
    name = f"{export.say('report', v['language'])} - {export.file_name(v, 'pdf')}"
    return _file(export.review_pdf(report, v["language"]), name)


def _fill_file(rec: Records, plan: str) -> Response:
    data, name, _ = fill.fill(rec, plan, actor=ACTOR)
    return _file(data, name)


# The routes.


def router(projects: Projects, trash: Trash | None = None) -> APIRouter:
    """An accept waits in `trash` for its Undo window: Undo takes it back to the version before."""
    r = APIRouter()
    trash = trash if trash is not None else Trash()

    def take_back(entry: dict) -> bool | dict:
        try:
            rec = projects.get(entry["project"])
            revert.undo_accept(rec, entry["deliverable"], entry["version"], actor=ACTOR)
        except RecordsError as e:
            return e.text
        return True

    trash.kind("accepted", restore=take_back, purge=lambda entry: None)  # nothing kept aside

    def wait_again(entry: dict) -> bool | dict:
        try:
            rec = projects.get(entry["project"])
            changes.unreject(rec, entry["deliverable"], entry["ids"], actor=ACTOR)
        except RecordsError as e:
            return e.text
        return True

    trash.kind("rejected", restore=wait_again, purge=lambda entry: None)  # a reject keeps nothing aside

    async def answer(project_id: str, fn, *args, status: int = 200, ids=()) -> Response:
        """Runs `fn(rec, *args)` in the thread pool: JSON (or the file) on success, else the
        refusal. `ids` are (value, not-found text, field) checked first."""
        try:
            for value, text, field in ids:
                _known(value, text, field)
            rec = await run_in_threadpool(projects.get, project_id)
            out = await run_in_threadpool(fn, rec, *args)
        except RecordsError as e:
            return _refusal(e)
        return out if isinstance(out, Response) else JSONResponse(out, status_code=status)

    def deliverable(d: str) -> tuple:
        return ((d, copy.DELIVERABLE_NOT_FOUND, "deliverable"),)

    def comment(c: str) -> tuple:
        return ((c, copy.COMMENT_NOT_FOUND, "comment"),)

    def plan(f: str) -> tuple:
        return ((f, copy.FILL_PLAN_NOT_FOUND, "plan"),)

    Json = Annotated[dict, Body()]

    base = "/projects/{p}/deliverables"

    @r.get(base)
    async def list_all(p: str) -> Response:
        return await answer(p, lambda rec: {"deliverables": store.list_deliverables(rec)})

    @r.get(base + "/{d}")
    async def get_view(p: str, d: str, version: int | None = None, revision: int | None = None):
        return await answer(p, current_view, d, version, revision, ids=deliverable(d))

    @r.get(base + "/{d}/changes")
    async def list_changes(p: str, d: str, status: str | None = None) -> Response:
        return await answer(p, _changes, d, status, ids=deliverable(d))

    @r.post(base + "/{d}/changes")
    async def propose(p: str, d: str, body: Json) -> Response:
        return await answer(p, _propose, d, body, status=201, ids=deliverable(d))

    @r.post(base + "/{d}/changes/accept")
    async def accept(p: str, d: str, body: Json) -> Response:
        try:
            _known(d, copy.DELIVERABLE_NOT_FOUND, "deliverable")
            rec = await run_in_threadpool(projects.get, p)
            out = await run_in_threadpool(_accept, rec, d, body)
        except RecordsError as e:
            return _refusal(e)
        if out.pop("_undoable"):  # its Undo token and window, as a removal answers
            out |= trash.put(
                "accepted", {"project": p, "deliverable": d, "version": out["version"]}
            )
        return JSONResponse(out)

    @r.post(base + "/{d}/changes/reject")
    async def reject(p: str, d: str, body: Json) -> Response:
        try:
            _known(d, copy.DELIVERABLE_NOT_FOUND, "deliverable")
            rec = await run_in_threadpool(projects.get, p)
            done = await run_in_threadpool(changes.reject, rec, d, body.get("ids"), actor=ACTOR)
        except RecordsError as e:
            return _refusal(e)
        # its Undo token and window, as an accept answers: Undo makes the changes wait again
        undo = trash.put("rejected", {"project": p, "deliverable": d, "ids": done})
        return JSONResponse({"rejected": done} | undo)

    @r.get(base + "/{d}/versions")
    async def versions(p: str, d: str) -> Response:
        return await answer(p, _versions, d, ids=deliverable(d))

    @r.get(base + "/{d}/compare")
    async def compare_views(
        p: str,
        d: str,
        start: Annotated[str | None, Query(alias="from")] = None,
        to: str | None = None,
    ) -> Response:
        return await answer(p, _compare, d, start, to, ids=deliverable(d))

    @r.get(base + "/{d}/comments")
    async def list_comments(p: str, d: str, status: str | None = None) -> Response:
        def run(rec, d):
            return {"comments": comments.list_comments(rec, d, status=status)}

        return await answer(p, run, d, ids=deliverable(d))

    @r.post(base + "/{d}/comments")
    async def add_comment(p: str, d: str, body: Json) -> Response:
        return await answer(p, _comment, d, body, status=201, ids=deliverable(d))

    @r.post("/projects/{p}/comments/{c}/replies")
    async def reply(p: str, c: str, body: Json) -> Response:
        return await answer(p, _reply, c, body, ids=comment(c))

    @r.post("/projects/{p}/comments/{c}/close")
    async def close(p: str, c: str) -> Response:
        return await answer(p, _close, c, "closed", ids=comment(c))

    @r.post("/projects/{p}/comments/{c}/reopen")
    async def reopen(p: str, c: str) -> Response:
        return await answer(p, _close, c, "open", ids=comment(c))

    @r.post("/projects/{p}/comments/{c}/fix")
    async def fix(p: str, c: str, lang: Literal["ar", "en"] = "ar") -> Response:
        def run(rec, c):
            return {"text": comments.fix_text(rec, c, lang=lang)}

        return await answer(p, run, c, ids=comment(c))

    @r.get(base + "/{d}/closeout")
    async def closeout(p: str, d: str) -> Response:
        return await answer(p, review.closeout, d, ids=deliverable(d))

    @r.post(base + "/{d}/revisions")
    async def issue_revision(p: str, d: str) -> Response:
        def run(rec, d):
            return {"no": review.issue_revision(rec, d, actor=ACTOR)}

        return await answer(p, run, d, status=201, ids=deliverable(d))

    @r.post(base + "/{d}/signoff")
    async def sign_off(p: str, d: str) -> Response:
        def run(rec, d):
            return {"revision": review.sign_off(rec, d, actor=ACTOR)}

        return await answer(p, run, d, ids=deliverable(d))

    @r.get(base + "/{d}/export")
    async def export_file(p: str, d: str, format: str = "pdf", revision: int | None = None):
        return await answer(p, _export, d, format, revision, ids=deliverable(d))

    @r.get(base + "/{d}/review-report")
    async def review_report(p: str, d: str, revision: int | None = None,
                            format: Literal["pdf"] = "pdf") -> Response:  # fmt: skip
        return await answer(p, _review_report, d, revision, ids=deliverable(d))

    @r.get(base + "/{d}/fill-plans")
    async def fill_plans(p: str, d: str) -> Response:
        def run(rec, d):
            return {"plans": fill.list_plans(rec, d)}

        return await answer(p, run, d, ids=deliverable(d))

    fills = "/projects/{p}/fill-plans/{f}"

    @r.get(fills + "/preview")
    async def fill_preview(p: str, f: str) -> Response:
        return await answer(p, fill.preview, f, ids=plan(f))

    @r.post(fills + "/accept-mismatches")
    async def accept_mismatches(p: str, f: str, body: Json) -> Response:
        def run(rec, f):
            return fill.accept_mismatches(rec, f, body.get("rows"), actor=ACTOR)

        return await answer(p, run, f, ids=plan(f))

    @r.get(fills + "/file")
    async def fill_file(p: str, f: str) -> Response:
        return await answer(p, _fill_file, f, ids=plan(f))

    return r
