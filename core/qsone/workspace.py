"""The workspace in the core API (Workspace plan): the project's open document, its status line,
the client BOQs it holds, and a file's pages as images and text. All paths start `/projects/{p}`.

The project keeps only *which document is open* (and where in it), in `workspace` inside the
project's encrypted file. That row is screen state, not a project fact: it is written without an
audit row. Every route needs the bearer secret (the app checks it) and an open project. A refusal
is `{"error": {en, ar}, "field": str | None}`. Page images are rendered in memory
(`records.render`), never to a file. Only ids are ever logged."""

import json
import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from qsone import copy
from qsone.clientfile import imported
from qsone.deliverables import store as deliverables
from qsone.projects import Projects
from qsone.records import files, render
from qsone.records.project import Records, RecordsError

MAX_PIECES = 1000  # text pieces in one answer
MAX_ANCHOR = 2048  # bytes of an anchor's JSON
KEY = re.compile(r"^(files:all|(file|deliverable|clientboq):[0-9a-z_-]{1,64})$")


def today() -> date:
    """The machine's local date: days left count from it."""
    return date.today()


def _refusal(e: RecordsError) -> JSONResponse:
    return JSONResponse({"error": e.text, "field": e.field}, status_code=e.status)


def _bad(field: str) -> RecordsError:
    return RecordsError(copy.WORKSPACE_BAD, status=422, field=field)


async def _open_body(request: Request) -> tuple[str, dict | None]:
    """The body's `open` and `anchor`, or WORKSPACE_BAD naming the field that is wrong."""
    try:
        body = json.loads(await request.body())
    except ValueError:
        raise _bad("open") from None
    if not isinstance(body, dict):
        raise _bad("open")
    key, anchor = body.get("open"), body.get("anchor")
    if not isinstance(key, str) or not KEY.match(key):
        raise _bad("open")
    if anchor is not None:
        try:
            size = len(json.dumps(anchor, ensure_ascii=False, allow_nan=False).encode())
        except ValueError:
            raise _bad("anchor") from None
        if not isinstance(anchor, dict) or size > MAX_ANCHOR:
            raise _bad("anchor")
    return key, anchor


# The open document -----------------------------------------------------------------------------


def read_open(rec: Records) -> dict:
    """The open document's key and anchor (None, None when nothing was ever opened), and the
    Client BOQs the project holds."""
    with rec.read() as conn:
        found = conn.execute("SELECT doc, anchor FROM workspace WHERE id = 1").fetchone()
    key, anchor = (None, None) if found is None else (found[0], json.loads(found[1] or "null"))
    return {"open": key, "anchor": anchor, "client_boqs": imported.list_imported(rec)}


def save_open(rec: Records, key: str, anchor: dict | None) -> None:
    with rec.write("engineer", upkeep=True) as conn:  # screen state: no audit row (decision 3)
        conn.execute(
            "INSERT INTO workspace(id, doc, anchor, updated_at) VALUES (1, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET doc = excluded.doc, anchor = excluded.anchor,"
            " updated_at = excluded.updated_at",
            (key, None if anchor is None else json.dumps(anchor, ensure_ascii=False), rec.clock()),
        )


# The status ------------------------------------------------------------------------------------


def _stage(raw: str | None) -> dict | None:
    try:
        found = json.loads(raw) if raw else None
    except ValueError:
        return None
    ok = isinstance(found, dict) and all(isinstance(found.get(k), str) for k in ("en", "ar"))
    return {"en": found["en"], "ar": found["ar"]} if ok else None


def _client_items(rec: Records) -> int | None:
    """How many items the client's BOQ has: those of the newest import; None with none."""
    with rec.read() as conn:
        newest = conn.execute(
            "SELECT json_extract(fields, '$.import_id') AS i FROM items"
            " WHERE kind = 'boq_item' AND i IS NOT NULL"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
        if newest is None:
            return None
        (n,) = conn.execute(
            "SELECT count(*) FROM items WHERE kind = 'boq_item'"
            " AND json_extract(fields, '$.import_id') = ?",
            (newest[0],),
        ).fetchone()
    return n


def _boq_value(rec: Records) -> dict | None:
    """The total of the most recently updated BOQ Sheet, with its Deliverable and Revision, and
    `sample` when any number behind it is sample data (the screen labels it). `items` is how many
    items the Sheet has, and `of` how many the client's BOQ has (when one was imported): the total
    says what it covers, «٤ من ٣٢٥ بند»."""
    with rec.read() as conn:
        found = conn.execute(
            "SELECT id FROM deliverables WHERE kind = 'sheet' AND variant = 'boq'"
            " ORDER BY updated_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    if found is None:
        return None
    entry = deliverables.entry(rec, found[0])
    total = entry["total"]
    if not total or "currency" not in total:
        return None
    return {
        "value": total["value"],
        "currency": total["currency"],
        "deliverable_id": entry["id"],
        "revision": entry["revision"],
        "status": entry["status"],
        "sample": entry["sample"],
        "items": (entry["progress"] or {}).get("total", 0),
    } | ({"of": of} if (of := _client_items(rec)) else {})


def project_status(rec: Records, waiting: int) -> dict:
    """Plan 7's `ProjectStatus`: only the fields known. Counts appear when above zero."""
    meta = rec.meta()
    out: dict = {}
    stage = _stage(meta.get("stage"))
    if stage is not None:
        out["stage"] = stage
    try:
        due = date.fromisoformat(meta.get("submission_date", ""))
    except ValueError:
        due = None
    if due is not None:
        out["submission_date"] = due.isoformat()
        out["days_left"] = (due - today()).days
    boq = _boq_value(rec)
    if boq is not None:
        out["boq_value"] = boq
    with rec.read() as conn:
        (open_comments,) = conn.execute(
            "SELECT count(*) FROM comments WHERE status = 'open' AND parent_id IS NULL"
        ).fetchone()
    if open_comments:
        out["open_comments"] = open_comments
    if waiting:
        out["waiting"] = waiting
    return out


# File pages and text ---------------------------------------------------------------------------


def _file_row(rec: Records, file_id: str) -> tuple[str, int | None]:
    with rec.read() as conn:
        found = conn.execute("SELECT kind, pages FROM files WHERE id = ?", (file_id,)).fetchone()
    if found is None:
        raise RecordsError(copy.FILE_NOT_FOUND, status=404, field="file")
    return found


def page_count(rec: Records, file_id: str) -> int:
    """0 for a file that is not a PDF, or a PDF pdfium cannot open."""
    kind, pages = _file_row(rec, file_id)
    if kind != "pdf":
        return 0
    if pages is not None:
        return pages
    try:
        return render.page_count(files.read_original(rec, file_id))
    except Exception:  # noqa: BLE001 - pdfium's own errors: the file shows its text instead
        return 0


def page_image(rec: Records, file_id: str, page: int, width: int) -> bytes:
    kind, _ = _file_row(rec, file_id)
    if kind != "pdf":
        raise RecordsError(copy.FILE_HAS_NO_PAGES, status=409, field="file")
    try:
        return render.page_png(files.read_original(rec, file_id), page, width)
    except IndexError:
        raise RecordsError(copy.PAGE_NOT_FOUND, status=404, field="page") from None
    except Exception:  # noqa: BLE001 - pdfium's own errors
        raise RecordsError(copy.FILE_UNREADABLE, status=409, field="file") from None


def file_text(rec: Records, file_id: str, page: int | None) -> dict:
    """The text pieces One read from the file, in order, with where each is."""
    _file_row(rec, file_id)
    where = "" if page is None else " AND json_extract(locator, '$.page') = :page"
    with rec.read() as conn:
        rows = conn.execute(
            f"SELECT locator, text FROM chunks WHERE file_id = :id{where} ORDER BY seq LIMIT :n",
            {"id": file_id, "page": page, "n": MAX_PIECES + 1},
        ).fetchall()
    pieces = [{"locator": json.loads(loc), "text": text} for loc, text in rows[:MAX_PIECES]]
    return {"pieces": pieces, "more": len(rows) > MAX_PIECES}


# The routes ------------------------------------------------------------------------------------


def router(projects: Projects, waiting=lambda project_id: 0) -> APIRouter:
    """`waiting(project_id)` counts the cards waiting for the engineer (the Brief Runner's)."""
    r = APIRouter()

    async def run(fn, *args):
        try:
            return await run_in_threadpool(fn, *args)
        except RecordsError as e:
            return _refusal(e)

    def project(project_id: str) -> Records:
        return projects.get(project_id)

    @r.get("/projects/{project_id}/workspace")
    async def get_workspace(project_id: str):
        return await run(lambda: read_open(project(project_id)))

    @r.put("/projects/{project_id}/workspace")
    async def put_workspace(project_id: str, request: Request):
        def save(key: str, anchor: dict | None) -> dict:
            save_open(project(project_id), key, anchor)
            return {"ok": True}

        try:
            key, anchor = await _open_body(request)
        except RecordsError as e:
            return _refusal(e)
        return await run(save, key, anchor)

    @r.get("/projects/{project_id}/client-boq/{file_id}")
    async def get_client_boq(project_id: str, file_id: str):
        return await run(lambda: imported.sheet(project(project_id), file_id))

    @r.get("/projects/{project_id}/status")
    async def get_status(project_id: str):
        return await run(lambda: project_status(project(project_id), waiting(project_id)))

    @r.get("/projects/{project_id}/files/{file_id}/pages")
    async def get_pages(project_id: str, file_id: str):
        return await run(lambda: {"pages": page_count(project(project_id), file_id)})

    @r.get("/projects/{project_id}/files/{file_id}/pages/{page}")
    async def get_page(
        project_id: str,
        file_id: str,
        page: int,
        width: Annotated[int, Query(ge=200, le=1600)] = 600,
    ):
        found = await run(lambda: page_image(project(project_id), file_id, page, width))
        return found if isinstance(found, Response) else Response(found, media_type="image/png")

    @r.get("/projects/{project_id}/files/{file_id}/text")
    async def get_text(
        project_id: str, file_id: str, page: Annotated[int | None, Query(ge=1)] = None
    ):
        return await run(lambda: file_text(project(project_id), file_id, page))

    return r


def no_store(app):
    """ASGI middleware: every answer under `/projects` and `/chat` (project content, page
    images, chats) carries `Cache-Control: no-store`, so the webview never keeps it on disk."""

    async def middleware(scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if not (path.startswith("/projects") or path.startswith("/chat")):
            return await app(scope, receive, send)

        async def sending(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"cache-control"]
                message = message | {"headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        return await app(scope, receive, send=sending)

    return middleware
