"""The Backup routes. A recovery code is in one answer only, never stored and never cached."""

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from qsone.backup.runner import BACKUP_KEY, Backups

PathText = Annotated[str, Field(min_length=1, max_length=4096)]


class FolderIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    path: PathText


class RunIn(BaseModel):
    project_id: str | None = Field(default=None, max_length=64)


class RestoreIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    path: PathText
    project_id: str = Field(min_length=1, max_length=64)
    code: str | None = Field(default=None, max_length=100)


class LastGroupIn(BaseModel):
    last_group: str = Field(min_length=1, max_length=20)


class ConfidentialIn(BaseModel):
    on: bool


def _once(body: dict) -> JSONResponse:
    """An answer that holds a code: the webview never keeps it."""
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


def router(backups: Backups) -> APIRouter:
    r = APIRouter()

    @r.get("/backup")
    def status() -> dict:
        return backups.status()

    @r.put("/backup/folder")
    def set_folder(body: FolderIn) -> dict:
        return backups.set_folder(body.path)

    @r.post("/backup/run")
    def run(body: RunIn | None = None) -> dict:
        project_id = body.project_id if body is not None else None
        return {"backed_up": backups.run(project_id, reason="manual")}

    @r.get("/backup/found")
    def found(path: Annotated[str, Query(min_length=1, max_length=4096)]) -> dict:
        return {"projects": backups.found(path)}

    @r.post("/backup/restore")
    def restore(body: RestoreIn) -> dict:
        return backups.restore(body.path, body.project_id, body.code or None)

    @r.post("/backup/recovery-code")
    def recovery_code() -> JSONResponse:
        return _once({"code": backups.new_code()})

    @r.post("/backup/recovery-code/confirm")
    def confirm_code(body: LastGroupIn) -> dict:
        backups.confirm(BACKUP_KEY, body.last_group)
        return {"saved": True}

    @r.put("/projects/{project_id}/confidential")
    def set_confidential(project_id: str, body: ConfidentialIn) -> JSONResponse:
        return _once(backups.set_confidential(project_id, body.on))

    @r.post("/projects/{project_id}/confidential/confirm")
    def confirm_confidential(project_id: str, body: LastGroupIn) -> dict:
        backups.confirm(project_id, body.last_group)
        return {"saved": True}

    return r
