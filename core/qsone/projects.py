"""Projects on this computer, and their routes in the core API.

Each project is a folder under `<data folder>/projects/`, named by its random id; nothing else about
it is readable on disk. The list comes from opening each file, and the names are kept in memory
only. Log ids only: never a project name, a file name or file text.

Next to `records.db` sits `key.json`: the project key wrapped by the Backup key, or by the
project's recovery code for a Confidential Project (Plan 8). When the key store loses a project
key, One puts it back from there."""

import logging
import re
import threading
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from qsone import activity, copy, settings
from qsone.backup import keys as backup_keys
from qsone.meaning.service import Meaning, ModelFailed
from qsone.records import audit, files, search, unzip, vault
from qsone.records.project import FILE_NAME, Records, RecordsError

if TYPE_CHECKING:
    from qsone.backup.runner import Backups

log = logging.getLogger(__name__)
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
        self.backups: Backups | None = None  # set by the app: a copy on close, the escrow

    def _escrow(self) -> backup_keys.Escrow | None:
        return self.backups.escrow() if self.backups is not None else None

    def _key_doc(self, rec: Records, *, confidential: bool) -> None:
        """Writes key.json when it is missing or stale; a failure is logged, never raised (the
        next backup writes it)."""
        try:
            key = vault.get_key(rec.id)
            if key is not None:
                backup_keys.ensure_key_doc(
                    rec.folder, rec.id, key, confidential=confidential, escrow=self._escrow()
                )
        except (OSError, KeyringError, RecordsError) as e:
            log.warning("Key file of %s not written (%s)", rec.id, type(e).__name__)

    def _recover_key(self, folder: Path) -> None:
        """Puts a lost project key back in the key store from key.json. Raises `RecordsError`:
        PROJECT_KEY_MISSING (no Backup key wrap, as for a Confidential Project),
        BACKUP_NEEDS_SIGN_IN (this computer has not got the Backup key), BACKUP_KEY_WRONG."""
        doc = backup_keys.read_doc(folder / backup_keys.KEY_FILE)
        if doc is None or doc.get("kind") != backup_keys.KIND_KEY:
            raise RecordsError(copy.PROJECT_KEY_MISSING)
        wanted = str(doc.get("key_id"))
        found = backup_keys.known_key(wanted)
        escrow = self._escrow() if found is None else None
        if escrow is not None:
            try:
                kept = escrow.get()
            except Exception as e:  # noqa: BLE001 - offline: the engineer is told what is needed
                log.warning("The Backup key escrow failed (%s)", type(e).__name__)
                kept = None
            if kept is not None and backup_keys.key_id(kept) == wanted:
                found = kept
                if backup_keys.backup_key() is None:
                    backup_keys.set_backup_key(kept)
        if found is None:
            raise backup_keys.BackupError(copy.BACKUP_NEEDS_SIGN_IN)
        vault.put_key(folder.name, backup_keys.unwrap(doc, backup_key=found))
        log.warning("PROJECT_KEY_RESTORED %s", folder.name)

    def _open_file(self, folder: Path) -> tuple[Records, bool]:
        """`Records.open`, putting a lost key back first; True when it was put back."""
        try:
            return Records.open(folder), False
        except RecordsError as e:
            if e.text is not copy.PROJECT_KEY_MISSING:
                raise
        try:
            self._recover_key(folder)
        except KeyringError:
            raise RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503) from None
        return Records.open(folder), True

    def open_file(self, project_id: str) -> Records:
        """The project's file opened on its own, not counted as open (a backup copy). Close it."""
        return self._open_file(self._folder(project_id))[0]

    def _folder(self, project_id: str) -> Path:
        """An id never becomes a path unless it is 32 lower-case hex digits."""
        if not _ID.fullmatch(project_id):
            raise RecordsError(copy.PROJECT_NOT_FOUND, status=404)
        return self.root / project_id

    def _remember(self, rec: Records) -> dict:
        meta = rec.meta()
        self._known[rec.id] = {
            "id": rec.id,
            "name": meta["name"],
            "created_at": meta["created_at"],
            "confidential": meta.get("confidential") == "1",  # a Confidential Project
            "archived_at": meta.get("archived_at"),  # read-only while set (Plan 8)
        }
        return self._known[rec.id]

    def create(self, name: str, actor: str) -> dict:
        project_id = uuid.uuid4().hex
        try:
            rec = Records.create(self.root / project_id, name=name, actor=actor)
        except KeyringError:
            raise RecordsError(copy.PROJECT_KEY_STORE_DOWN, status=503) from None
        self._key_doc(rec, confidential=False)
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
                        rec, _ = self._open_file(folder)
                        try:
                            self._remember(rec)
                        finally:
                            rec.close()
                    except RecordsError as e:
                        failed.append({"id": project_id, "error": e.text})
                        continue
                rec = self._open.get(project_id)
                is_open = rec is not None and rec.is_open
                if is_open:  # its meta may have changed since (e.g. marked Confidential)
                    self._remember(rec)
                listed.append({**self._known[project_id], "open": is_open})
        listed.sort(key=lambda p: p["created_at"], reverse=True)
        return listed + failed

    def open(self, project_id: str) -> dict:
        folder = self._folder(project_id)
        with self._lock:
            rec = self._open.get(project_id)
            restored = False
            if rec is None or not rec.is_open:
                rec, restored = self._open_file(folder)
                try:
                    search.ensure_index(rec)
                    self._remember(rec)
                except BaseException:
                    rec.close()
                    raise
                self._open[project_id] = rec
                self._key_doc(rec, confidential=self._known[project_id]["confidential"])
            opened = {**self._known[project_id], "open": True}
            return opened | {"note": copy.PROJECT_KEY_RESTORED} if restored else opened

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

    def close(self, project_id: str, *, back_up: bool = True) -> None:
        """Backs the project up first (when the app runs backups), unless `back_up` is False."""
        self._folder(project_id)
        with self._lock:
            opened = self._open.get(project_id)
        # Outside this lock: a backup run takes its own lock first, then this one.
        if back_up and self.backups is not None and opened is not None and opened.is_open:
            self.backups.closing(opened)
        with self._lock:
            rec = self._open.pop(project_id, None)
            if rec is not None and rec.is_open:
                self._remember(rec)  # the list keeps its latest meta while it is closed
        if rec is not None:
            rec.close()

    def forget(self, project_id: str) -> None:
        """The file was replaced (a restore): its name and meta are read again."""
        with self._lock:
            self._known.pop(project_id, None)

    def set_confidential(self, project_id: str, on: bool) -> dict:
        """Marks an open project Confidential, or not, audited. On: a new recovery code wraps
        the key, and key.json holds that wrap only, so the Backup key and the account never
        meet this project's key; the code is in this answer only. Off: a Backup key wrap again.
        Raises `RecordsError`, `KeyringError`, `OSError`."""
        rec = self.get(project_id)
        key = vault.get_key(project_id)
        if key is None:
            raise RecordsError(copy.PROJECT_KEY_MISSING)
        code = backup_keys.new_recovery_code() if on else None
        if code is not None:
            doc = backup_keys.wrap_with_code(key, project_id=project_id, code=code)
        else:
            current = backup_keys.ensure_backup_key(self._escrow())
            doc = backup_keys.wrap(key, project_id=project_id, backup_key=current)
        backup_keys.write_doc(rec.folder / backup_keys.KEY_FILE, doc)
        before = rec.meta().get("confidential") == "1"
        with rec.write(ACTOR) as conn:
            rec.set_meta(conn, "confidential", "1" if on else "0")
            audit.record(
                conn,
                at=rec.clock(),
                actor=ACTOR,
                action="update",
                table="meta",
                row_id="confidential",
                before={"confidential": before},
                after={"confidential": on},
            )
        with self._lock:
            self._remember(rec)
        return {"confidential": on, "code": code} if code else {"confidential": on}

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


def _zip_note(text: dict) -> str:
    """The copy.py name of a zip refusal, kept as the zip's note."""
    return "ZIP_TOO_BIG" if text is copy.ZIP_TOO_BIG else "ZIP_UNSAFE"


def add_upload(rec: Records, name: str, data: bytes, *, folder: str | None) -> tuple[dict, int]:
    """One uploaded file, or a zip opened in memory (Plan 8): (answer, status). A zip answers
    {"zip": true, "files": [FileInfo], "skipped": [{"name", "folder", "error"}]}, its members
    under `<folder>/<zip name>/<their folder>`; a member over 256 MB or empty is skipped and
    named. A zip that is refused (too big, unsafe) is kept as one file, not opened, with that
    note. Each added file reaches the canvas live. Raises what `files.add_file` raises."""
    if not unzip.is_zip(name, data):
        info = files.add_file(rec, name, data, actor=ACTOR, folder=folder)
        found = _file(info)
        activity.publish(rec.id, {"type": "file", "file": found})  # the canvas, live
        return found, 200 if info.duplicate else 201
    added: list[dict] = []
    skipped: list[dict] = []
    kept = None
    try:
        for inner, member, body in unzip.members(name, data):
            where = files.clean_folder(f"{folder or ''}/{inner}")
            if body is None:
                skipped.append({"name": member, "folder": where, "error": copy.FILE_TOO_BIG})
                continue
            try:
                info = files.add_file(rec, member, body, actor=ACTOR, folder=where)
            except RecordsError as e:
                if e.text is not copy.FILE_EMPTY:
                    raise
                skipped.append({"name": member, "folder": where, "error": e.text})
                continue
            added.append(_file(info))
            activity.publish(rec.id, {"type": "file", "file": added[-1]})
    except RecordsError as refused:  # kept as it came, not opened
        if refused.text not in (copy.ZIP_TOO_BIG, copy.ZIP_UNSAFE):
            raise  # e.g. an archived project
        note = _zip_note(refused.text)
        kept = files.add_file(rec, name, data, actor=ACTOR, folder=folder, note=note)
        activity.publish(rec.id, {"type": "file", "file": _file(kept)})
        if not added:
            return _file(kept), 200 if kept.duplicate else 201
        added.append(_file(kept))
    with rec.write(ACTOR) as conn:  # counts only, for Usage Stats' `zips`
        audit.record(
            conn,
            at=rec.clock(),
            actor=ACTOR,
            action="unzip",
            table="zips",
            row_id=uuid.uuid4().hex,
            before=None,
            after={"files": len(added), "skipped": len(skipped), "opened": kept is None},
        )
    return {"zip": True, "files": added, "skipped": skipped}, 201


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

    @r.get("/projects/{project_id}/files/{file_id}/flags")
    def list_flags(project_id: str, file_id: str) -> dict:
        """The file's hidden-text flags, for the warning on screen."""
        flags = files.list_flags(projects.get(project_id), file_id)
        if flags is None:
            raise RecordsError(copy.FILE_NOT_FOUND, status=404)
        return {"flags": flags}

    @r.post("/projects/{project_id}/files")
    async def add_file(
        project_id: str,
        request: Request,
        name: Annotated[str, Query(min_length=1, max_length=1000)],
        folder: Annotated[str | None, Query(max_length=files.MAX_FOLDER)] = None,
    ) -> JSONResponse:
        """The raw file is the body; its name comes URL-encoded in `?name=`, and the path inside
        a dropped folder in `?folder=` (display text only). A zip is opened (`add_upload`)."""
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
        found, status = await run_in_threadpool(
            add_upload, rec, name, b"".join(parts), folder=folder
        )
        wake()  # embedding happens in the background; the upload never waits for it
        return JSONResponse(found, status_code=status)

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
