import secrets
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import chat, copy, keys

Provider = Literal["anthropic"]


class AiKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: Provider
    value: str = Field(min_length=1)


def create_app(secret: str, model_factory: chat.ModelFactory | None = None) -> FastAPI:
    """Build the core app. Every route needs `Authorization: Bearer <secret>`.

    `model_factory` gives the Lead QS model (None when no key is saved); tests inject a
    PydanticAI `FunctionModel`.
    """
    expected = f"Bearer {secret}".encode()
    model_factory = model_factory or chat.default_model

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

    return app
