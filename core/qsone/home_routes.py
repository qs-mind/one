"""The routes of Lessons Learned, Home and a tender's header (Phase 1, C7; contract rows 3–7).

Each is declared as its stub was, so the contract's OpenAPI document does not change, and every
refusal goes through `phase1_contract.refusal`, which keeps `field`."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from qsone import activity, home, lessons
from qsone import phase1_contract as c
from qsone.records.project import RecordsError

UNDO_KIND = "lesson"


def _refusals(*codes: int) -> dict:
    bad = c.Refusal | c.BodyProblem  # 422: the engineer's value, or a body built wrongly
    return {code: {"model": bad if code == 422 else c.Refusal} for code in codes}


def _refused(e: RecordsError) -> JSONResponse:
    return c.refusal(e.text, e.status, field=e.field)


def _changed() -> None:
    activity.publish("general", {"type": "lessons"})


def router(projects, engine, trash) -> APIRouter:
    r = APIRouter()

    def names() -> dict[str, str]:
        return {p["id"]: p["name"] for p in projects.list() if "error" not in p}

    def put_back(entry: dict) -> bool:
        try:
            done = lessons.put_back(engine.engineer_records(), entry["lesson_id"])
        except RecordsError:
            return False
        _changed()
        return done

    trash.kind(UNDO_KIND, restore=put_back, purge=lambda entry: None)  # nothing kept aside

    @r.get("/engineer/lessons", response_model=c.Lessons, responses=_refusals(409, 503))
    def list_lessons():
        try:
            return {"lessons": lessons.listed(engine.engineer_records(), names())}
        except RecordsError as e:
            return _refused(e)

    @r.patch(
        "/engineer/lessons/{lesson_id}",
        response_model=c.Lesson,
        responses=_refusals(404, 409, 422, 503),
    )
    def edit_lesson(lesson_id: str, body: c.LessonIn):
        try:
            found = lessons.edit(engine.engineer_records(), lesson_id, body.text, names())
        except RecordsError as e:
            return _refused(e)
        _changed()
        return found

    @r.delete(
        "/engineer/lessons/{lesson_id}",
        response_model=c.Undoable,
        responses=_refusals(404, 409, 503),
    )
    async def remove_lesson(lesson_id: str):
        try:
            await run_in_threadpool(lambda: lessons.remove(engine.engineer_records(), lesson_id))
        except RecordsError as e:
            return _refused(e)
        _changed()
        return trash.put(UNDO_KIND, {"lesson_id": lesson_id})  # on the loop: its window runs here

    @r.get("/home", response_model=c.Home)
    def show_home():
        return home.home(projects, engine)

    @r.get(
        "/projects/{project_id}/tender",
        response_model=c.TenderView,
        responses=_refusals(404, 409, 503),
    )
    def show_tender(project_id: str):
        try:
            return home.tender(projects, engine, project_id)
        except RecordsError as e:
            return _refused(e)

    return r
