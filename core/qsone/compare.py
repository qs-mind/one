"""Read-only revision routes; images never leave memory or enter an HTTP cache."""

from typing import Annotated

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.records.compare import compare_files, overlay_png
from qsone.records.project import RecordsError


class CompareArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_file_id: str = Field(min_length=1, max_length=80)
    new_file_id: str = Field(min_length=1, max_length=80)


def router(projects) -> APIRouter:
    r = APIRouter()

    @r.post("/projects/{project_id}/files/compare")
    def compare(project_id: str, body: CompareArgs):
        try:
            return compare_files(projects.get(project_id), body.old_file_id, body.new_file_id)
        except RecordsError as e:
            return JSONResponse(copy.error(e.text), status_code=e.status)

    @r.get("/projects/{project_id}/files/compare/overlay")
    def overlay(
        project_id: str,
        old_file_id: Annotated[str, Query(min_length=1, max_length=80)],
        new_file_id: Annotated[str, Query(min_length=1, max_length=80)],
        old_page: Annotated[int, Query(ge=1)],
        new_page: Annotated[int, Query(ge=1)],
        width: Annotated[int, Query(ge=600, le=1400)] = 600,
    ):
        try:
            png = overlay_png(
                projects.get(project_id), old_file_id, new_file_id, old_page, new_page, width
            )
            return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
        except RecordsError as e:
            return JSONResponse(copy.error(e.text), status_code=e.status)

    return r
