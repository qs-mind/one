"""The engine's HTTP routes. Settings part (Plan 4 Task 3): AI Connectors, the Model Data Sheet,
the model for each role, and entered prices. Money goes out as exact decimal text."""

from decimal import Decimal

import httpx2
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import copy, keys
from qsone.engine import cards, connectors, roles
from qsone.engine.connectors import standard
from qsone.engine.types import ModelCard, ModelChoice, Role, Text


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


def _roles_json(chosen: dict[Role, ModelChoice]) -> dict:
    return {role: _choice_json(choice) for role, choice in chosen.items()}


def settings_router(http_client: httpx2.AsyncClient | None = None) -> APIRouter:
    """`http_client` reaches the AI providers; tests inject a fake one."""
    router = APIRouter()

    def found() -> list[connectors.Connector]:
        return connectors.connectors(http_client=http_client)

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
    def remove_standard(connector_id: str) -> Response:
        try:
            removed = standard.remove(connector_id)
        except KeyringError:
            return JSONResponse({"error": copy.KEY_STORE_DOWN}, status_code=503)
        return Response(status_code=204 if removed else 404)

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

    return router
