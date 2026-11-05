"""The Project Canvas in the core API (Plan 7): where each frame sits, the project's status line,
and a file's pages as images and text for its file frame. All paths start `/projects/{p}`.

The canvas keeps only *where* things sit, in `canvas_frames` and `canvas_view` inside the
project's encrypted file. These rows are screen layout, not project facts: they are written
without an audit row, and floats are allowed. Every route needs the bearer secret (the app checks
it) and an open project. A refusal is `{"error": {en, ar}, "field": str | None}`. Page images are
rendered in memory (`records.render`), never to a file. Only ids are ever logged."""

import json
import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from starlette.concurrency import run_in_threadpool

from qsone import copy
from qsone.deliverables import store as deliverables
from qsone.projects import Projects
from qsone.records import files, render
from qsone.records.project import Records, RecordsError

MAX_FRAMES = 2000  # in one save, and as removed keys
MAX_PIECES = 1000  # text pieces in one answer
KEY = re.compile(r"^(files|file|deliverable|desk|team):[0-9a-z_-]{1,64}$")
_PLACE = 1_000_000  # world coordinates within ±1,000,000

Coordinate = Annotated[float, Field(ge=-_PLACE, le=_PLACE, allow_inf_nan=False)]


def today() -> date:
    """The machine's local date: days left count from it."""
    return date.today()


class FrameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=KEY.pattern, max_length=80)
    x: Coordinate
    y: Coordinate
    w: float = Field(ge=120, le=8000, allow_inf_nan=False)
    h: float = Field(ge=80, le=8000, allow_inf_nan=False)
    z: int = Field(ge=-1_000_000, le=1_000_000)
    collapsed: StrictBool


class FramesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: list[FrameIn] = Field(max_length=MAX_FRAMES)
    removed: list[Annotated[str, Field(pattern=KEY.pattern, max_length=80)]] = Field(
        max_length=MAX_FRAMES
    )


class ViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: Coordinate
    y: Coordinate
    zoom: float = Field(ge=0.1, le=2, allow_inf_nan=False)


def _refusal(e: RecordsError) -> JSONResponse:
    return JSONResponse({"error": e.text, "field": e.field}, status_code=e.status)


async def _layout_body(request: Request, model: type[BaseModel]) -> BaseModel:
    """The body as `model`, or CANVAS_BAD_LAYOUT naming the first field that is wrong."""
    try:
        return model.model_validate_json(await request.body())
    except ValidationError as e:
        where = ".".join(str(p) for p in e.errors()[0]["loc"]) or None
        raise RecordsError(copy.CANVAS_BAD_LAYOUT, status=422, field=where) from None


# The layout ------------------------------------------------------------------------------------


def read_layout(rec: Records) -> dict:
    with rec.read() as conn:
        frames = conn.execute(
            "SELECT key, x, y, w, h, z, collapsed FROM canvas_frames ORDER BY z, key"
        ).fetchall()
        view = conn.execute("SELECT x, y, zoom FROM canvas_view WHERE id = 1").fetchone()
    return {
        "frames": [
            {"key": k, "x": x, "y": y, "w": w, "h": h, "z": z, "collapsed": bool(c)}
            for k, x, y, w, h, z, c in frames
        ],
        "view": None if view is None else {"x": view[0], "y": view[1], "zoom": view[2]},
    }


def save_frames(rec: Records, frames: list[FrameIn], removed: list[str]) -> None:
    """One transaction: the frames given are put (one row per key), the removed ones go."""
    at = rec.clock()
    with rec.write("engineer") as conn:  # screen layout: no audit row (decision 3)
        conn.executemany("DELETE FROM canvas_frames WHERE key = ?", ((k,) for k in removed))
        conn.executemany(
            "INSERT INTO canvas_frames(key, x, y, w, h, z, collapsed, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET x = excluded.x,"
            " y = excluded.y, w = excluded.w, h = excluded.h, z = excluded.z,"
            " collapsed = excluded.collapsed, updated_at = excluded.updated_at",
            (
                (
                    f.key,
                    round(f.x, 1),
                    round(f.y, 1),
                    round(f.w, 1),
                    round(f.h, 1),
                    f.z,
                    int(f.collapsed),
                    at,
                )  # fmt: skip
                for f in frames
            ),
        )


def save_view(rec: Records, view: ViewIn) -> None:
    with rec.write("engineer") as conn:
        conn.execute(
            "INSERT INTO canvas_view(id, x, y, zoom, updated_at) VALUES (1, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET x = excluded.x, y = excluded.y,"
            " zoom = excluded.zoom, updated_at = excluded.updated_at",
            (round(view.x, 1), round(view.y, 1), round(view.zoom, 3), rec.clock()),
        )


# The status ------------------------------------------------------------------------------------


def _stage(raw: str | None) -> dict | None:
    try:
        found = json.loads(raw) if raw else None
    except ValueError:
        return None
    ok = isinstance(found, dict) and all(isinstance(found.get(k), str) for k in ("en", "ar"))
    return {"en": found["en"], "ar": found["ar"]} if ok else None


def _boq_value(rec: Records) -> dict | None:
    """The total of the most recently updated BOQ Sheet, with its Deliverable and Revision, and
    `sample` when any number behind it is sample data (the screen labels it)."""
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
    }


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

    @r.get("/projects/{project_id}/canvas")
    async def get_layout(project_id: str):
        return await run(lambda: read_layout(project(project_id)))

    @r.put("/projects/{project_id}/canvas/frames")
    async def put_frames(project_id: str, request: Request):
        def save(body: FramesIn) -> dict:
            save_frames(project(project_id), body.frames, body.removed)
            return {"ok": True}

        try:
            body = await _layout_body(request, FramesIn)
        except RecordsError as e:
            return _refusal(e)
        return await run(save, body)

    @r.put("/projects/{project_id}/canvas/view")
    async def put_view(project_id: str, request: Request):
        def save(body: ViewIn) -> dict:
            save_view(project(project_id), body)
            return {"ok": True}

        try:
            body = await _layout_body(request, ViewIn)
        except RecordsError as e:
            return _refusal(e)
        return await run(save, body)

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
