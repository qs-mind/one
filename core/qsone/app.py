import secrets
from typing import Literal

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import chat, copy, keys, models, settings

Provider = Literal["anthropic"]


class AiKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: Provider
    value: str = Field(min_length=1)


class ModelIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)


def create_app(
    secret: str,
    model_factory: chat.ModelFactory | None = None,
    models_lister: models.ModelLister | None = None,
) -> FastAPI:
    """Build the core app. Every route needs `Authorization: Bearer <secret>`.

    `model_factory` gives the Lead QS model (None when no key is saved); tests inject a
    PydanticAI `FunctionModel`. `models_lister` lists the models a key can use; tests inject
    a fake, so no test calls Anthropic.
    """
    expected = f"Bearer {secret}".encode()
    model_factory = model_factory or chat.default_model
    models_lister = models_lister or models.list_models

    def check_secret(request: Request) -> None:
        given = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(given, expected):
            raise HTTPException(status_code=401)

    app = FastAPI(
        dependencies=[Depends(check_secret)], docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default echoes the request body, which may hold a key: send only where and why.
        detail = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/chat")
    async def chat_stream(request: Request) -> Response:
        return await chat.respond(request, model_factory)

    @app.get("/settings/ai-key")
    def ai_key_status(provider: Provider = "anthropic") -> dict:
        return {"set": keys.get_key(provider) is not None}

    @app.put("/settings/ai-key")
    def save_ai_key(body: AiKeyIn) -> JSONResponse:
        try:
            keys.set_key(body.provider, body.value)
        except KeyringError:
            return JSONResponse({"error": copy.KEY_STORE_DOWN}, status_code=503)
        return JSONResponse({"set": True})

    @app.get("/settings/models")
    async def list_models() -> JSONResponse:
        key = keys.get_key("anthropic")
        if key is None:
            return JSONResponse({"error": copy.NO_KEY}, status_code=409)
        try:
            return JSONResponse(await models_lister(key))
        except anthropic.APIError as error:
            # The provider's own words go to core.log; the screen gets a plain {en, ar} pair.
            models.log.warning("Listing the models failed: %s", error)
            return JSONResponse({"error": models.plain_error(error)}, status_code=502)

    @app.get("/settings/model")
    def lead_model() -> dict:
        return {"id": chat.lead_model_id()}

    @app.put("/settings/model")
    def choose_lead_model(body: ModelIn) -> JSONResponse:
        try:
            settings.save("lead_model", body.id)
        except OSError:
            return JSONResponse({"error": copy.MODEL_NOT_SAVED}, status_code=503)
        return JSONResponse({"id": body.id})

    return app
