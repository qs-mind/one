"""Projects on this computer, and their routes in the core API.

Each project is a folder under `<data folder>/projects/`, named by its random id; nothing else about
it is readable on disk. The list comes from opening each file, and the names are kept in memory
only. Log ids only: never a project name, a file name or file text."""

import re
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from qsone import copy, settings
from qsone.meaning.service import Meaning, ModelFailed
from qsone.records import files, search
from qsone.records.project import FILE_NAME, Records, RecordsError

ACTOR = "engineer"  # every HTTP call is the engineer at the screen
_ID = re.compile(r"[0-9a-f]{32}")


def default_data_dir() -> Path:
    """The app data folder, shared with settings.json; `QSONE_DATA_DIR` overrides it."""
    return settings.data_dir()


class Projects:
    """The projects in `data_dir/projects/<id>/`. Open and close are explicit."""

    def __init__(self, data_dir: Path):
        self.root = Path(data_dir) / "projects"
        self._open: dict[str, Records] = {}
        self._known: dict[str, dict] = {}  # id -> {"id", "name", "created_at"}, from the file
        self._lock = threading.RLock()

    def _folder(self, project_id: str) -> Path:
        """An id never becomes a path unless it is 32 lower-case hex digits."""
        if not _ID.fullmatch(project_id):
            raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
        return self.root / project_id

    def _remember(self, rec: Records) -> dict:
        meta = rec.meta()
        self._known[rec.id] = {"id": rec.id, "name": meta["name"], "created_at": meta["created_at"]}
        return self._known[rec.id]

    def create(self, name: str, actor: str) -> dict:
        project_id = uuid.uuid4().hex
        try:
            rec = Records.create(self.root / project_id, name=name, actor=actor)
        except KeyringError:
            raise RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503) from None
        with self._lock:
            self._open[project_id] = rec
            return {**self._remember(rec), "open": True}

    def opened(self) -> list[tuple[str, Records]]:
        """The open projects, a snapshot."""
        with self._lock:
            return [(pid, rec) for pid, rec in self._open.items() if rec.is_open]

    def list(self) -> list[dict]:
        """Newest first; a project that cannot be read is listed after them, with its `error`."""
        if not self.root.is_dir():
            return []
        listed, failed = [], []
        with self._lock:
            for folder in sorted(self.root.iterdir()):
                project_id = folder.name
                if not _ID.fullmatch(project_id):
                    continue
                if project_id not in self._known:
                    try:
                        rec = Records.open(folder)
                        try:
                            self._remember(rec)
                        finally:
                            rec.close()
                    except RecordsError as e:
                        failed.append({"id": project_id, "error": e.text})
                        continue
                rec = self._open.get(project_id)
                listed.append({**self._known[project_id], "open": rec is not None and rec.is_open})
        listed.sort(key=lambda p: p["created_at"], reverse=True)
        return listed + failed

    def open(self, project_id: str) -> dict:
        folder = self._folder(project_id)
        with self._lock:
            rec = self._open.get(project_id)
            if rec is None or not rec.is_open:
                rec = Records.open(folder)
                try:
                    search.ensure_index(rec)
                    self._remember(rec)
                except BaseException:
                    rec.close()
                    raise
                self._open[project_id] = rec
            return {**self._known[project_id], "open": True}

    def get(self, project_id: str) -> Records:
        """Raises `RecordsError`: PROJECT_NOT_FOUND (404) or PROJECT_NOT_OPEN (409)."""
        folder = self._folder(project_id)
        with self._lock:
            rec = self._open.get(project_id)
            if rec is not None and rec.is_open:
                return rec
        if not (folder / FILE_NAME).is_file():
            raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
        raise RecordsError(copy.PROJECT_NOT_OPEN)

    def close(self, project_id: str) -> None:
        self._folder(project_id)
        with self._lock:
            rec = self._open.pop(project_id, None)
        if rec is not None:
            rec.close()

    def close_all(self) -> None:
        with self._lock:
            opened, self._open = list(self._open.values()), {}
        for rec in opened:
            rec.close()


class ProjectIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)


class RerankIn(BaseModel):
    q: str = Field(min_length=1, max_length=1000)
    chunk_ids: list[int] = Field(min_length=1, max_length=search.RERANK_TOP)


def _file(info: files.FileInfo) -> dict:
    """FileInfo as JSON, its note turned from a copy.py name into its {en, ar} pair."""
    return asdict(info) | {"note": getattr(copy, info.note) if info.note else None}


def _hit(h: search.Hit) -> dict:
    return {
        "chunk_id": h.chunk_id,
        "file_id": h.file_id,
        "file_name": h.file_name,
        "locator": h.locator,
        "text": h.text,
        "score": h.score,
    }


def router(projects: Projects, meaning: Meaning | None = None) -> APIRouter:
    """With `meaning`, search uses the search models once they are ready."""
    r = APIRouter()

    def wake() -> None:
        if meaning is not None:
            meaning.wake()

    @r.get("/projects")
    def list_projects() -> dict:
        return {"projects": projects.list()}

    @r.post("/projects")
    def create_project(body: ProjectIn) -> JSONResponse:
        return JSONResponse(projects.create(body.name, ACTOR), status_code=201)

    @r.post("/projects/{project_id}/open")
    def open_project(project_id: str) -> dict:
        opened = projects.open(project_id)
        wake()
        return opened

    @r.post("/projects/{project_id}/close")
    def close_project(project_id: str) -> dict:
        projects.close(project_id)
        return {"open": False}

    @r.get("/projects/{project_id}/files")
    def list_files(project_id: str, include_old: bool = False) -> dict:
        rec = projects.get(project_id)
        return {"files": [_file(f) for f in files.list_files(rec, include_old=include_old)]}

    @r.post("/projects/{project_id}/files")
    async def add_file(
        project_id: str,
        request: Request,
        name: Annotated[str, Query(min_length=1, max_length=1000)],
    ) -> JSONResponse:
        """The raw file is the body; its name comes URL-encoded in `?name=`."""
        rec = await run_in_threadpool(projects.get, project_id)
        limit = files.MAX_FILE_BYTES
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > limit:
            raise RecordsError(copy.FILE_TOO_BIG, status=413)
        parts, size = [], 0
        async for part in request.stream():  # also stops a body sent without Content-Length
            size += len(part)
            if size > limit:
                raise RecordsError(copy.FILE_TOO_BIG, status=413)
            parts.append(part)
        info = await run_in_threadpool(files.add_file, rec, name, b"".join(parts), actor=ACTOR)
        wake()  # embedding happens in the background; the upload never waits for it
        return JSONResponse(_file(info), status_code=200 if info.duplicate else 201)

    @r.get("/projects/{project_id}/search")
    def search_project(
        project_id: str,
        q: str = "",
        also: Annotated[list[str] | None, Query()] = None,
        mode: search.Mode = "auto",
        k: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> dict:
        rec = projects.get(project_id)
        embedder = meaning.embedder() if meaning is not None else None
        try:
            found = search.search(rec, q, also=also or (), mode=mode, k=k, embedder=embedder)
        except ModelFailed:  # the state now says why; words still work
            found = search.search(rec, q, also=also or (), mode=mode, k=k)
        rerank = found.mode == "hybrid" and meaning is not None and meaning.reranker() is not None
        return {
            "mode": found.mode,
            "note": copy.SEARCH_WORDS_ONLY if found.mode == "words" else None,
            "rerank": rerank,
            "results": [_hit(h) for h in found.hits],
        }

    @r.post("/projects/{project_id}/rerank")
    def rerank_project(project_id: str, body: RerankIn) -> dict:
        """The second step of a search: these chunks, reordered by the reranker."""
        rec = projects.get(project_id)
        reranker = meaning.reranker() if meaning is not None else None
        if reranker is None:
            raise RecordsError(copy.MEANING_NOT_READY)
        should_stop = meaning.rerank_turn(project_id)
        try:
            hits = search.rerank_hits(
                rec, body.q, body.chunk_ids, reranker, should_stop=should_stop
            )
        except search.Superseded:
            raise RecordsError(copy.SEARCH_SUPERSEDED) from None
        except ModelFailed:
            raise RecordsError(copy.MEANING_NOT_READY) from None
        return {"results": [_hit(h) for h in hits]}

    return r
