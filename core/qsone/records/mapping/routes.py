"""Project Map read API; mounted under the app's existing bearer authentication."""

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from qsone import copy
from qsone.records.mapping import store
from qsone.records.project import RecordsError


class FactEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool | None = None
    value: StrictStr | None = None


def router(projects):
    r = APIRouter()

    @r.get("/projects/{project_id}/map")
    def project_map(
        project_id: str,
        parent: str | None = None,
        cursor: str | None = None,
        limit: int = Query(100, ge=1, le=200),
    ):
        """{status:{waiting,reading,done,failed,total,line:{en,ar}}, groups:[{path,
        label:{en,ar},count}], files:[{file_id,name,folder,kind,pages,read_how,ai_title,
        ai_group,key_pages:[{label:{en,ar},page|sheet+row,why}],local_state}],next_cursor}.
        Names/folders are verbatim engineer source labels; enums are machine codes.
        parent selects a full group path; cursor is opaque and scoped to that parent.
        """
        return store.list_map(projects.get(project_id), parent=parent, cursor=cursor, limit=limit)

    @r.get("/projects/{project_id}/map/files/{file_id}")
    def map_file(project_id: str, file_id: str):
        """The map_files fields with decoded JSON structure, scanned_pages,
        ocr_done_pages, key_pages and bilingual note, plus tables, sheets, links, facts.
        PDF locators: one-based page, box in points from CropBox top-left.
        Excel locators: sheet and one-based rows/cols. Source text is verbatim.
        """
        result = store.detail(projects.get(project_id), file_id)
        if result is None:
            raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=404)
        return result

    @r.get("/projects/{project_id}/map/facts")
    def facts(project_id: str, cursor: str | None = None, limit: int = Query(100, ge=1, le=200)):
        """{facts:[{id,name:{en,ar},value,unit,currency,file_id,locator,box,state,
        conflict_with,confirmed_by,confirmed_at,corrected_value}],next_cursor}.
        Current facts only; empty until the fact-mapping job fills them.
        """
        return store.entries(projects.get(project_id), "facts", cursor=cursor, limit=limit)

    @r.post("/projects/{project_id}/map/facts/{fact_id}")
    def edit_fact(project_id: str, fact_id: str, edit: FactEdit):
        from qsone.records.mapping.facts import update

        return update(projects.get(project_id), fact_id, confirm=edit.confirm, value=edit.value)

    @r.get("/projects/{project_id}/map/links")
    def links(project_id: str, cursor: str | None = None, limit: int = Query(100, ge=1, le=200)):
        """{links:[{id,from_file_id,from_locator,to_file_id,to_locator,kind,
        words:{en,ar},evidence,by,state}],next_cursor}. Current links only.
        Empty until the link-mapping job fills them.
        """
        return store.entries(projects.get(project_id), "links", cursor=cursor, limit=limit)

    return r
