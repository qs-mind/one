"""The QS Calc Engine in the core API, for the screen and for tests: the same calls as the tools.

Every route needs the bearer secret (the app checks it) and an open project. The actor is the
engineer. A refusal is 422 with the tool's error body; numbers are always strings.
"""

from typing import Annotated

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from qsone.calc import resolve, tool
from qsone.calc.units import BUILT_IN
from qsone.projects import ACTOR, Projects
from qsone.records.project import Records


def _units(rec: Records) -> dict:
    with rec.read() as conn:
        rows = conn.execute(
            "SELECT i.code, n.value, n.unit, n.id, s.id, s.title, n.dated FROM items i"
            " JOIN numbers n ON n.item_id = i.id JOIN sources s ON s.id = n.source_id"
            " WHERE i.kind = ? AND n.name = ? AND n.valid_until IS NULL ORDER BY i.code, n.id",
            (resolve.UNIT_KIND, resolve.EQUALS),
        ).fetchall()
    defined = [
        {
            "symbol": symbol,
            "equals": f"{value} {unit}",
            "number": number_id,
            "source": {"id": source_id, "title": title},
            "dated": dated,
        }
        for symbol, value, unit, number_id, source_id, title, dated in rows
    ]
    return {"built_in": list(BUILT_IN), "defined": defined}


def router(projects: Projects) -> APIRouter:
    r = APIRouter()

    async def call(project_id: str, name: str, payload) -> dict:
        rec = await run_in_threadpool(projects.get, project_id)
        return await run_in_threadpool(tool.call, rec, name, payload, actor=ACTOR)

    async def run(project_id: str, name: str, payload, status: int = 200) -> JSONResponse:
        reply = await call(project_id, name, payload)
        return JSONResponse(reply, status_code=422 if "error" in reply else status)

    @r.post("/projects/{project_id}/calc")
    async def calculate(project_id: str, body: Annotated[dict, Body()]) -> JSONResponse:
        """201 when something was saved, else 200."""
        reply = await call(project_id, "calculate", body)
        status = 422 if "error" in reply else 201 if reply["saved"] else 200
        return JSONResponse(reply, status_code=status)

    @r.get("/projects/{project_id}/units")
    async def list_units(project_id: str) -> dict:
        rec = await run_in_threadpool(projects.get, project_id)
        return await run_in_threadpool(_units, rec)

    @r.post("/projects/{project_id}/units")
    async def define_unit(project_id: str, body: Annotated[dict, Body()]) -> JSONResponse:
        return await run(project_id, "define_unit", body, status=201)

    @r.get("/projects/{project_id}/numbers/{number_id}/explain")
    async def explain_number(project_id: str, number_id: str, page: int = 1) -> JSONResponse:
        return await run(project_id, "explain_number", {"number": number_id, "page": page})

    @r.get("/projects/{project_id}/calc/stale")
    async def stale(project_id: str) -> JSONResponse:
        return await run(project_id, "recalculate", {"apply": False})

    @r.post("/projects/{project_id}/calc/recalculate")
    async def recalculate(
        project_id: str, body: Annotated[dict | None, Body()] = None
    ) -> JSONResponse:
        """The body may name `only`: these calculation ids, and what they need first."""
        return await run(project_id, "recalculate", {**(body or {}), "apply": True})

    return r
