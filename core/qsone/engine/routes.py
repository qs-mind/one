"""The engine's HTTP routes. Settings part (Plan 4 Task 3): AI Connectors, the Model Data Sheet,
the model for each role, and entered prices. Spending Caps and what was spent (Task 6). The
engineer's own Claude Code (Task 5). Money goes out as exact decimal text. The Brief Runner's
chat stream, Brief controls, cards, and Plan 7's team and activity (Task 8)."""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx2
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.responses import Response, StreamingResponse

from qsone import copy, keys, keystore, settings
from qsone.engine import cards, connectors, costs, roles
from qsone.engine.connectors import claude_code, standard
from qsone.engine.types import EFFORTS, BadAnswer, ModelCard, ModelChoice, Role, Text, answer_value
from qsone.undo import Trash


class ChoiceIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    connector: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)


class StandardIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    key: str | None = Field(default=None, max_length=1000)


class PriceIn(BaseModel):
    connector: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    price_in: str = Field(alias="in", max_length=40)
    price_out: str = Field(alias="out", max_length=40)


class CapsIn(BaseModel):
    """Only the caps given change. Amounts are checked as exact decimal text in `costs`, so a
    JSON number is refused with the same words as any other inexact number."""

    model_config = ConfigDict(extra="forbid")

    brief: Any = None
    day: Any = None
    month: Any = None
    budget_above: Any = None
    subscription_stops: StrictBool | None = None


class ClaudeCodeIn(BaseModel):
    """`keep_copy` is optional: whether Claude Code keeps its own copy of each conversation
    (founder question 3); left out, it stays as it was (on by default)."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(max_length=1000)
    on: StrictBool
    keep_copy: StrictBool | None = None


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")  # never "1E-7"


def _choice_json(choice: ModelChoice) -> dict:
    return {"connector": choice.connector, "model": choice.model}


def card_json(card: ModelCard) -> dict:
    return _choice_json(card.choice) | {
        "name": card.name,
        "provider": card.provider,
        "images": card.images,
        "tools": card.tools,
        "context": card.context,
        "price_in": _money(card.price_in),
        "price_out": _money(card.price_out),
        "price_source": card.price_source,
        "on_device": card.on_device,
        "subscription": card.subscription,
        "efforts": list(card.efforts),  # none: the message box shows no effort for it
        "effort_default": card.effort_default,
    }


def _connector_json(connector: connectors.Connector, error: Text | None) -> dict:
    return {
        "id": connector.id,
        "kind": connector.kind,
        "name": connector.name,
        "provider": connector.provider,
        "on_device": getattr(connector, "on_device", False),
        "key_set": keys.get_key(connector.id) is not None,
        "error": error,  # why its models could not be listed just now, or None
    }


def _effort() -> str | None:
    saved = settings.ai().get("effort")
    return saved if saved in EFFORTS else None


def _roles_json(chosen: dict[Role, ModelChoice]) -> dict:
    return {role: _choice_json(choice) for role, choice in chosen.items()}


def settings_router(
    http_client: httpx2.AsyncClient | None = None,
    *,
    claude_command: Sequence[str] = (),
    trash: Trash | None = None,
) -> APIRouter:
    """`http_client` reaches the AI providers; tests inject a fake one. `claude_command`
    replaces the Claude Code executable; tests run the fake `claude`. A removed Standard Link
    waits in `trash` for its Undo window; its key goes when the window ends."""
    router = APIRouter()
    trash = trash if trash is not None else Trash()
    trash.kind("standard", restore=standard.put_back, purge=standard.forget_key)

    def found() -> list[connectors.Connector]:
        return connectors.connectors(http_client=http_client, claude_command=claude_command)

    async def sheet() -> list[ModelCard]:
        return (await cards.listed(found()))[0]

    @router.get("/settings/ai")
    async def ai_settings() -> dict:
        present = found()
        listed, errors = await cards.listed(present)
        return {
            "connectors": [_connector_json(c, errors.get(c.id)) for c in present],
            "sheet": [card_json(c) for c in listed],
            "roles": _roles_json(roles.chosen(listed)),
            "defaults": _roles_json(roles.defaults(listed)),
            "effort": _effort(),  # the message box's last effort, or None (the provider's own)
            "key_store": keystore.kind(),  # "file" when this computer has no key store
        }

    @router.put("/settings/ai/roles")
    async def choose_roles(body: dict[Role, ChoiceIn]) -> JSONResponse:
        listed = await sheet()
        allowed = [c.choice for c in listed]
        picked = {role: ModelChoice(c.connector, c.model) for role, c in body.items()}
        for role, choice in picked.items():
            if choice not in allowed:
                answer = {"role": role, "allowed": [_choice_json(c) for c in allowed]}
                return JSONResponse(answer, status_code=422)
        try:
            for role, choice in picked.items():
                roles.choose(role, choice)
        except OSError:
            return JSONResponse({"error": copy.MODEL_NOT_SAVED}, status_code=503)
        return JSONResponse(_roles_json(roles.chosen(listed)))

    @router.post("/settings/ai/standard")
    def add_standard(body: StandardIn) -> JSONResponse:
        try:
            link = standard.add(body.name, body.base_url, body.key or None)
        except KeyringError:
            return JSONResponse({"error": copy.KEY_STORE_DOWN}, status_code=503)
        except ValueError as error:  # also KeyInTheClear
            detail = [{"loc": ["body", "base_url"], "msg": str(error), "type": "value_error"}]
            return JSONResponse({"detail": detail}, status_code=422)
        return JSONResponse(_connector_json(link, None), status_code=201)

    @router.delete("/settings/ai/standard/{connector_id}")
    async def remove_standard(connector_id: str) -> Response:
        """Out of use at once; `{undo, window_ms}` takes it back (`POST /undo/{token}`)."""
        taken = standard.take_out(connector_id)
        if taken is None:
            return Response(status_code=404)
        return JSONResponse(trash.put("standard", taken))

    @router.put("/settings/ai/prices")
    async def enter_price(body: PriceIn) -> JSONResponse:
        choice = ModelChoice(body.connector, body.model)
        card = next((c for c in await sheet() if c.choice == choice), None)
        if card is None:
            return JSONResponse({"detail": "not on the Model Data Sheet"}, status_code=404)
        try:
            cards.enter_price(choice, body.price_in, body.price_out)
        except cards.PriceNotExact as refused:
            answer = {"error": copy.NUMBER_NOT_EXACT, "field": refused.field}
            return JSONResponse(answer, status_code=422)
        return JSONResponse(card_json(cards.priced(card)))

    @router.get("/settings/ai/claude-code")
    async def claude_code_status() -> dict:
        """The engineer's Check: free, and only when asked."""
        found = await claude_code.status(claude_code.saved()["path"], command_prefix=claude_command)
        return asdict(found) | {"models": list(found.models)}

    @router.put("/settings/ai/claude-code")
    def save_claude_code(body: ClaudeCodeIn) -> JSONResponse:
        try:
            entry = claude_code.save(path=body.path, on=body.on, keep_copy=body.keep_copy)
        except OSError:
            return JSONResponse({}, status_code=503)  # the screen says it in its own words
        notice = copy.CLAUDE_CODE_COPY if entry["on"] and entry["keep_copy"] else None
        return JSONResponse(entry | {"notice": notice})

    def caps_answer(value: costs.Caps) -> dict:
        return {"caps": costs.caps_json(value), "recommended": costs.caps_json(costs.RECOMMENDED)}

    @router.get("/settings/ai/caps")
    def spending_caps() -> dict:
        return caps_answer(costs.caps())

    @router.put("/settings/ai/caps")
    def save_caps(body: CapsIn) -> JSONResponse:
        changes = {name: getattr(body, name) for name in body.model_fields_set}
        try:
            saved = costs.save_caps(changes)
        except costs.CapNotExact as refused:
            answer = {"error": copy.NUMBER_NOT_EXACT, "field": refused.field}
            return JSONResponse(answer, status_code=422)
        except OSError:
            return JSONResponse({"error": copy.CAPS_NOT_SAVED}, status_code=503)
        return JSONResponse(caps_answer(saved))

    return router


# The Brief Runner (Task 8) ----------------------------------------------------------------------

ACTIVITY_PING = 15  # seconds between keep-alive comments on the activity stream


class SteerIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=20_000)


class CardChoiceIn(BaseModel):
    """The engineer's answer. A card with a payload (Plan 5) also takes its answers, by
    question id, and the rows ticked, by index."""

    choice: str = Field(min_length=1, max_length=200)
    answers: dict[str, str] | None = Field(default=None, max_length=50)
    rows_ok: list[int] | None = Field(default=None, max_length=1000)


def briefs_router(engine: Any) -> APIRouter:
    """The chat's stream and messages, the Brief controls, the cards, and Plan 7's team and
    activity. `engine` is the app's `runner.Engine`."""
    from qsone.chat import stream
    from qsone.engine.runner import BriefBusy, reply_id

    router = APIRouter()

    def refused(text: Text, status: int) -> JSONResponse:
        return JSONResponse({"error": text}, status_code=status)

    @router.get("/chat/{chat_id}/stream")
    def chat_stream(chat_id: str) -> Response:
        """204 when no Brief runs in the chat; else its stream, replayed from its start."""
        brief_id = engine.active(chat_id)
        if brief_id is None:
            return Response(status_code=204)
        return stream(engine.events(brief_id), reply_id(brief_id))

    @router.get("/chat/{chat_id}/messages")
    def chat_messages(chat_id: str) -> dict:
        return {"messages": engine.chat_messages(chat_id)}

    @router.post("/briefs/{brief_id}/stop")
    async def stop(brief_id: str) -> JSONResponse:
        try:
            await engine.stop(brief_id)
        except LookupError:
            return refused(copy.BRIEF_NOT_RUNNING, 409)
        return JSONResponse({"state": "stopped"})

    @router.post("/briefs/{brief_id}/steer")
    async def steer(brief_id: str, body: SteerIn) -> Response:
        try:
            await engine.steer(brief_id, body.text)
        except LookupError:
            return refused(copy.BRIEF_NOT_RUNNING, 409)
        return Response(status_code=202)

    @router.get("/briefs/activity")
    def chats_activity() -> dict:
        """What every chat's Briefs do now, for the screen outside each chat (it polls)."""
        return {"chats": engine.chats()}

    @router.post("/chat/{chat_id}/seen")
    def chat_seen(chat_id: str) -> Response:
        engine.seen(chat_id)
        return Response(status_code=204)

    @router.get("/briefs/unfinished")
    def unfinished() -> dict:
        return {"briefs": engine.unfinished()}

    @router.post("/briefs/{brief_id}/continue")
    async def continue_brief(brief_id: str) -> JSONResponse:
        try:
            await engine.continue_brief(brief_id)
        except BriefBusy as busy:
            return JSONResponse({"brief_id": busy.brief_id}, status_code=409)
        except LookupError:
            return refused(copy.BRIEF_NOT_FOUND, 404)
        return JSONResponse({"state": "running"})

    @router.post("/cards/{card_id}")
    async def answer(card_id: str, body: CardChoiceIn) -> Response:
        card = engine.card(card_id)
        if card is None:
            return refused(copy.CARD_GONE, 404)
        options = list(card.options)
        try:
            value = answer_value(card, body.choice, answers=body.answers, rows_ok=body.rows_ok)
            await engine.answer(card_id, value)
        except BadAnswer as bad:
            return JSONResponse({"error": copy.CARD_BAD_ANSWER, "field": bad.field}, 422)
        except ValueError:
            return JSONResponse({"error": copy.CARD_CHOICE, "options": options}, status_code=422)
        except LookupError:
            return refused(copy.CARD_GONE, 404)
        return Response(status_code=204)

    @router.get("/costs")
    def spent(brief_id: str | None = None) -> dict:
        """From the engine's own open cost book; nothing is spent before it is open."""
        return costs.summary(engine.cost_book(), brief_id=brief_id, now=datetime.now(UTC))

    @router.get("/projects/{project_id}/team")
    def team(project_id: str) -> dict:
        return engine.team(project_id)

    @router.get("/projects/{project_id}/activity")
    def activity(project_id: str) -> StreamingResponse:
        async def lines():
            events = engine.activity(project_id)
            pending = None
            try:
                while True:
                    pending = pending or asyncio.ensure_future(anext(events))
                    done, _ = await asyncio.wait({pending}, timeout=ACTIVITY_PING)
                    if not done:
                        yield ": ping\n\n"
                        continue
                    event, pending = pending.result(), None
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            finally:
                if pending is not None:  # ends the subscription inside the generator, too
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                await events.aclose()

        return StreamingResponse(
            lines(), media_type="text/event-stream", headers={"cache-control": "no-cache"}
        )

    return router
