"""Settings in one home and the AI links (Phase 1, contract routes 21 to 24).

Each route is declared as the contract declares it (`qsone.phase1_contract`): the same path,
status, answer model and refusals, so the screens' OpenAPI file does not change. Refusals go out
through `phase1_contract.refusal`, with `field`, `example` and `brief_id` when they apply."""

import httpx2
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from qsone import ai_links, settings_registry
from qsone import phase1_contract as c
from qsone.records.project import RecordsError
from qsone.undo import Trash

_REFUSAL = {"model": c.Refusal}
_BAD = {"model": c.Refusal | c.BodyProblem}  # 422: the engineer's value, or a body built wrongly


def router(http: httpx2.AsyncClient | None, trash: Trash, engine: object) -> APIRouter:
    """`http` reaches the AI providers for the key's check (tests inject a fake); a removed
    link waits in `trash` for its Undo window; `engine` says which links running work uses."""
    r = APIRouter()
    ai_links.kinds(trash)

    @r.get("/settings", response_model=c.Settings)
    def all_settings():
        return settings_registry.all_settings()

    # Async on purpose: the `setting` event is published on the core's loop.
    @r.patch(
        "/settings/{key}",
        response_model=c.Setting,
        responses={404: _REFUSAL, 422: _BAD, 503: _REFUSAL},
    )
    async def change_setting(key: str, body: c.SettingIn):
        try:
            return settings_registry.change(key, body.value)
        except RecordsError as e:
            return settings_registry.answer(e)

    @r.post(
        "/settings/ai/connect",
        status_code=201,
        response_model=c.AiLink,
        responses={
            200: {"model": c.AiLink},
            409: _REFUSAL,
            422: _BAD,
            502: _REFUSAL,
            503: _REFUSAL,
        },
    )
    async def connect_ai(body: c.AiConnectIn):
        try:
            link, made = await ai_links.connect(body.key, http)
        except RecordsError as e:
            return settings_registry.answer(e)
        return JSONResponse(link.model_dump(mode="json"), status_code=201 if made else 200)

    @r.delete(
        "/settings/ai/links/{link_id}",
        response_model=c.Undoable,
        responses={404: _REFUSAL, 409: _REFUSAL},
    )
    async def disconnect_ai(link_id: str):  # the Undo window runs on the core's loop
        try:
            return ai_links.disconnect(link_id, trash, engine)
        except RecordsError as e:
            return settings_registry.answer(e)

    return r
