"""The tender plan's routes, rows 8 to 12 of the Phase 1 contract: read the plan, ask the Lead
for one, approve it, sign off a stage, and answer a Suggested change.

Every refusal is a `Refusal` (`phase1_contract.refusal`). What only the engine knows is checked
here, before the store is asked: work running in the tender (WORK_RUNNING), and whether the
Lead can work at all (the Model Data Sheet; its refusal is the engine's own text). The figures
are worked out again from the sheet of this moment at approval, with the requests measured
when they were proposed: only a change of the models, prices or AI links moves them. Once the
plan or a stage is approved, or a change accepted, the plan driver starts what comes next
(`_driver`). The Lead is told the answer to its Suggested change in one line."""

import asyncio
import inspect
from importlib import import_module
from importlib.util import find_spec

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from qsone import copy
from qsone import phase1_contract as c
from qsone.engine.plan import build, model, store
from qsone.journey import setup_state
from qsone.records.project import RecordsError

DRIVER = "qsone.engine.plan.driver"
INSTRUCTION = (
    "The engineer asks for the tender plan. Read what the tender holds (project_map, "
    "files_list, files_read), then open the plan tools (open_tools: plan) and propose the plan "
    "with tender_plan_write: its stages and the team. If the submission date is missing or has "
    "passed, ask the engineer for it first."
)


def _refusals(*codes: int) -> dict:
    """The refusals a route declares, as the contract has them."""
    return {
        code: {"model": c.Refusal | c.BodyProblem if code == 422 else c.Refusal} for code in codes
    }


def _refused(e: RecordsError) -> JSONResponse:
    return c.refusal(e.text, e.status, field=e.field)


async def _driver(event: str, *args) -> None:
    """Tells the plan driver that the plan or a stage was approved, so it starts the next stage.
    Until the driver is built, nothing starts."""
    if find_spec(DRIVER) is None:
        return
    found = getattr(import_module(DRIVER), event, None)
    if found is not None:
        answer = found(*args)
        if inspect.isawaitable(answer):
            await answer


def router(projects, engine) -> APIRouter:
    from qsone.engine.runner import BriefBusy, NoAI

    r = APIRouter()

    def running(project_id: str) -> JSONResponse | None:
        busy = engine.active(project_id)
        return None if busy is None else c.refusal(copy.WORK_RUNNING, brief_id=busy)

    async def figures(stages: list[dict], requests: dict, measured: list | None) -> model.Estimate:
        """The estimate of `stages` on the sheet now. Raises `NoAI` when the Lead cannot work."""
        sheet, _ = await engine.sheet()
        kept = None if measured is None else tuple(measured)
        return model.estimate(build.work(stages, requests), sheet, kept)

    @r.get("/projects/{project_id}/plan", response_model=c.PlanView, responses=_refusals(404, 409))
    async def get_plan(project_id: str):
        try:
            return await asyncio.to_thread(lambda: store.plan_view(projects.get(project_id)))
        except RecordsError as e:
            return _refused(e)

    @r.post(
        "/projects/{project_id}/plan/request",
        status_code=202,
        response_model=c.BriefStarted,
        responses=_refusals(404, 409, 423),
    )
    async def ask_for_plan(project_id: str):
        try:
            rec = projects.get(project_id)
            if rec.archived_at is not None:
                raise RecordsError(copy.PROJECT_ARCHIVED, status=423)
            if (busy := running(project_id)) is not None:
                return busy
            if await asyncio.to_thread(store.current, rec) is not None:
                raise RecordsError(copy.PLAN_EXISTS)
            text = copy.PLAN_REQUEST_BRIEF[setup_state.language()]
            brief_id = await engine.start_brief(project_id, text, instruction=INSTRUCTION, by="one")
        except RecordsError as e:
            return _refused(e)
        except BriefBusy as busy:
            return c.refusal(copy.WORK_RUNNING, brief_id=busy.brief_id)
        except NoAI as none:
            return c.refusal(none.text)
        return JSONResponse({"brief_id": brief_id}, status_code=202)

    @r.post(
        "/projects/{project_id}/plan/approve",
        response_model=c.PlanView,
        responses=_refusals(404, 409, 422, 423),
    )
    async def approve_plan(project_id: str, body: c.PlanApproveIn):
        try:
            rec = projects.get(project_id)
            found = await asyncio.to_thread(store.body, rec)
            if found is None:
                raise RecordsError(copy.PLAN_NOT_FOUND, status=404)
            plan = found["plan"]
            if body.version != plan["version"]:
                raise RecordsError(copy.PLAN_CHANGED, field="version")
            if plan["status"] == "approved":  # a retry after a lost answer: nothing starts
                return c.PlanView(plan=await asyncio.to_thread(store.current, rec))
            if (busy := running(project_id)) is not None:
                return busy
            now = await figures(plan["stages"], found["requests"], found.get("measured"))
            done = await asyncio.to_thread(
                lambda: store.approve(rec, version=body.version, estimate=now)
            )
        except RecordsError as e:
            return _refused(e)
        except NoAI as none:
            return c.refusal(none.text)
        await _driver("on_plan_approved", project_id)
        return c.PlanView(plan=done)

    @r.post(
        "/projects/{project_id}/plan/stages/{stage_id}/approve",
        response_model=c.PlanView,
        responses=_refusals(404, 409, 422, 423),
    )
    async def sign_off_stage(project_id: str, stage_id: str, body: c.StageApproveIn):
        try:
            rec = projects.get(project_id)
            now = await asyncio.to_thread(store.current, rec)
            if now is None:
                raise RecordsError(copy.PLAN_NOT_FOUND, status=404)
            at = next((i for i, s in enumerate(now.stages) if s.id == stage_id), None)
            if at is None:
                raise RecordsError(copy.STAGE_NOT_FOUND, status=404)
            if body.version != now.version:
                raise RecordsError(copy.PLAN_CHANGED, field="version")
            if now.stages[at].status == "approved":  # a retry: nothing starts
                return c.PlanView(plan=now)
            if now.stages[at].status != "waiting_engineer":
                raise RecordsError(copy.STAGE_NOT_WAITING)
            if (busy := running(project_id)) is not None:
                return busy
            if any(s.status == "pending" for s in now.stages[at + 1 :]):
                await engine.sheet()  # another stage would start: the Lead must be able to work
            done = await asyncio.to_thread(
                lambda: store.approve_stage(rec, stage_id, version=body.version)
            )
        except RecordsError as e:
            return _refused(e)
        except NoAI as none:
            return c.refusal(none.text)
        await _driver("on_stage_approved", project_id, stage_id)
        return c.PlanView(plan=done)

    @r.post(
        "/projects/{project_id}/plan/change",
        response_model=c.PlanView,
        responses=_refusals(404, 409, 422, 423),
    )
    async def answer_change(project_id: str, body: c.PlanChangeIn):
        try:
            rec = projects.get(project_id)
            found = await asyncio.to_thread(store.body, rec)
            if found is None:
                raise RecordsError(copy.PLAN_NOT_FOUND, status=404)
            change = found["plan"]["change"]
            now = None
            if body.accept and change is not None and change["id"] == body.change_id:
                now = await figures(  # the figures of now, so the Lead must be able to work
                    change["stages"], found["change_requests"], found.get("change_measured")
                )
            done = await asyncio.to_thread(
                lambda: store.answer_change(rec, body.change_id, body.accept, estimate=now)
            )
        except RecordsError as e:
            return _refused(e)
        except NoAI as none:
            return c.refusal(none.text)
        await tell_running(project_id, rec)
        if body.accept:
            await _driver("on_plan_changed", project_id)  # a stage it adds or frees starts
        return c.PlanView(plan=done)

    async def tell_running(project_id: str, rec) -> None:
        """The answer, as a steer to the Lead's running work. With none running, the plan
        driver puts it in the next work's instruction."""
        said = await asyncio.to_thread(store.untold, rec)
        busy = engine.active(project_id, include_mapping=False)
        if said is None or busy is None:
            return
        try:
            await engine.steer(busy, said[1][setup_state.language()])
        except LookupError:
            return  # it ended meanwhile: the next work is told
        await asyncio.to_thread(store.told, rec, said[0])

    return r
