"""The Settings screen's Connector routes (Plan 5, Task 12).

- `GET /connectors` → `{"connectors": [{name, transport, runs, enabled, tools, read_without_asking,
  search_tool, token}]}`; `token` only says whether one is kept.
- `POST /connectors` `{name, transport, command? (argv list or one line), url?, token?,
  token_env?}` connects, lists the tools and answers `{"card": …}`: the `connector` card the
  screen shows (ConnectorCard). The token stays in memory until the engineer says yes.
- `POST /connectors/cards/{card_id}` `{choice, answers?}` answers that card: `{"connector": …}`
  once saved, `{"connector": null}` after a no.
- `DELETE /connectors/{name}` → `{undo, window_ms}`: out of use at once, back with
  `POST /undo/{token}` inside the window; the token leaves the key store when it ends.
- `PUT /connectors/{name}/enabled` `{enabled}` → `{"connector": …}`.

Refusals are `{"error": {en, ar}}`: CONNECTOR_BAD (422), CONNECTOR_NAME_TAKEN (409),
CONNECTOR_DOWN (502), CONNECTOR_NOT_FOUND (404), CONNECTOR_CARD_GONE (404), CARD_BAD_ANSWER and
CARD_CHOICE (422), KEY_STORE_DOWN (503). The token is never logged or sent back."""

import asyncio
import os
import shlex
from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import copy
from qsone.connectors.hub import ConnectorConfig, ConnectorDown, ConnectorError, ConnectorHub
from qsone.engine.types import BadAnswer, Card, answer_value
from qsone.undo import Trash


class ConnectorIn(BaseModel):
    """Loose on purpose: `ConnectorConfig` says what is wrong, in the engineer's words."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(max_length=200)
    transport: str = Field(max_length=20)
    command: list[str] | str | None = Field(None, max_length=200)
    url: str | None = Field(None, max_length=2048)
    token: str | None = Field(None, max_length=20_000)
    token_env: str | None = Field(None, max_length=100)


class AnswerIn(BaseModel):
    choice: str = Field(min_length=1, max_length=200)
    answers: dict[str, str] | None = Field(default=None, max_length=10)


class EnabledIn(BaseModel):
    enabled: bool


def _argv(command: list[str] | str | None) -> tuple[str, ...] | None:
    """A command line as its parts: a list as given, one line split as the system's shell would
    (quotes kept together)."""
    if command is None or isinstance(command, list):
        return None if command is None else tuple(part for part in command if part)
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return ()
    return tuple(p[1:-1] if len(p) > 1 and p[0] == p[-1] == '"' else p for p in parts)


def _card_json(card: Card) -> dict:
    found = asdict(card)
    found["options"] = list(card.options)
    return found


def router(hub: ConnectorHub, trash: Trash | None = None) -> APIRouter:
    """A removed Connector waits in `trash` for its Undo window."""
    router = APIRouter()
    trash = trash if trash is not None else Trash()
    trash.kind("connector", restore=hub.put_back, purge=hub.forget_key)
    waiting: dict[str, tuple[Card, asyncio.Future, asyncio.Task, str]] = {}

    def refused(text: dict, status: int) -> JSONResponse:
        return JSONResponse({"error": text}, status_code=status)

    def failure(error: BaseException) -> JSONResponse:
        if isinstance(error, ConnectorError):
            return refused(error.text, error.status)
        if isinstance(error, KeyringError):
            return refused(copy.KEY_STORE_DOWN, 503)
        return refused(copy.CONNECTOR_DOWN, 502)

    @router.get("/connectors")
    def listed() -> dict:
        return {"connectors": hub.listing()}

    @router.post("/connectors")
    async def add(body: ConnectorIn) -> JSONResponse:
        try:
            config = ConnectorConfig(
                name=body.name,
                transport=body.transport,  # type: ignore[arg-type]  # checked by the config
                command=_argv(body.command) if body.transport == "stdio" else None,
                url=body.url or None,
                token_env=body.token_env or None,
            )
        except ConnectorError as error:
            return failure(error)
        loop = asyncio.get_running_loop()
        shown: asyncio.Future = loop.create_future()
        task: asyncio.Task

        async def ask(card: Card) -> str:
            answer = loop.create_future()
            waiting[card.id] = (card, answer, task, config.name)
            shown.set_result(card)
            return await answer

        task = hub.background(hub.propose(config, body.token or None, ask=ask))
        await asyncio.wait({shown, task}, return_when=asyncio.FIRST_COMPLETED)
        if shown.done():
            return JSONResponse({"card": _card_json(shown.result())})
        error = task.exception()
        return failure(error if error is not None else ConnectorDown())

    @router.post("/connectors/cards/{card_id}")
    async def answer(card_id: str, body: AnswerIn) -> JSONResponse:
        found = waiting.get(card_id)
        if found is None or found[2].done():
            waiting.pop(card_id, None)
            return refused(copy.CONNECTOR_CARD_GONE, 404)
        card, future, task, name = found
        try:
            value = answer_value(card, body.choice, answers=body.answers)
        except BadAnswer as bad:
            return JSONResponse({"error": copy.CARD_BAD_ANSWER, "field": bad.field}, 422)
        except ValueError:
            return JSONResponse(
                {"error": copy.CARD_CHOICE, "options": list(card.options)}, status_code=422
            )
        del waiting[card_id]
        future.set_result(value)
        try:
            saved = await task
        except (ConnectorError, ConnectorDown, KeyringError, OSError) as error:
            return failure(error)
        config = hub.config(name) if saved else None
        return JSONResponse({"connector": None if config is None else hub.entry(config)})

    @router.delete("/connectors/{name}")
    async def remove(name: str) -> Response:
        try:
            taken = await hub.take_out(name)
        except ConnectorError as error:
            return failure(error)
        return JSONResponse(trash.put("connector", taken))

    @router.put("/connectors/{name}/enabled")
    async def enable(name: str, body: EnabledIn) -> JSONResponse:
        try:
            config = await hub.set_enabled(name, body.enabled)
        except ConnectorError as error:
            return failure(error)
        return JSONResponse({"connector": hub.entry(config)})

    return router
