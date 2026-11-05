import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import anthropic
import httpx2
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import activity, chat, copy, keys, models, projects, settings
from qsone.calc import routes as calc_routes
from qsone.deliverables import api as deliverables_api
from qsone.deliverables import events as deliverable_events
from qsone.engine import connectors as engine_connectors
from qsone.engine import mcp_server, roles, tools_records  # noqa: F401 - registers the records tools
from qsone.engine import routes as engine_routes
from qsone.engine.connectors import claude_code
from qsone.engine.runner import Engine
from qsone.engine.types import ModelChoice
from qsone.meaning import routes as meaning_routes
from qsone.meaning.service import Meaning
from qsone.records.project import RecordsError
from qsone.web import search as web_search

Provider = Literal["anthropic"]


class AiKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: Provider
    value: str = Field(min_length=1)


class SearchKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=500)


class ModelIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)


def create_app(
    secret: str,
    connectors: Callable[[], list] | None = None,
    models_lister: models.ModelLister | None = None,
    data_dir: Path | None = None,
    meaning: Callable[[projects.Projects], Meaning] | None = None,
    ai_http: httpx2.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable] | None = None,
) -> FastAPI:
    """Build the core app. Every route needs `Authorization: Bearer <secret>`.

    `connectors` gives the AI Connectors the Brief Runner uses (default: the ones the engineer
    set up); tests inject fakes with scripted models. `models_lister` lists the models a key can
    use; tests inject a fake, so no test calls Anthropic. Projects live in `data_dir/projects/`
    (default: the app data folder); they are all closed when the app stops. `meaning` builds the
    search-by-meaning service for the app's projects (default: the real models in
    `<data folder>/models`); tests inject sample specs, a fake hub and test doubles. `ai_http`
    reaches the AI providers for the AI settings and the Brief Runner (default: each provider's
    own client); tests inject a fake transport. `sleep` is the Brief Runner's wait between
    retries (default: `asyncio.sleep`).
    """
    expected = f"Bearer {secret}".encode()
    models_lister = models_lister or models.list_models

    def check_secret(request: Request) -> None:
        given = request.headers.get("authorization", "").encode()
        if not secrets.compare_digest(given, expected):
            raise HTTPException(status_code=401)

    folder = data_dir if data_dir is not None else projects.default_data_dir()
    registry = projects.Projects(folder)
    service = meaning(registry) if meaning else Meaning(registry, Path(folder) / "models")
    mcp = mcp_server.McpGate()
    engine = Engine(
        projects=registry,
        data_dir=Path(folder),
        connectors=connectors or (lambda: engine_connectors.connectors(http_client=ai_http)),
        sleep=sleep or asyncio.sleep,
        mcp=mcp,
        meaning=service,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        # Deliverables are written in worker threads: their events reach the hub on its loop.
        stop_listening = deliverable_events.listen(
            lambda project_id, event: loop.call_soon_threadsafe(activity.publish, project_id, event)
        )
        service.start()
        await engine.start()  # never continues a Brief by itself
        try:
            async with mcp.running():
                yield
                await engine.shutdown()  # each Brief keeps its Checkpoint
        finally:
            stop_listening()
        service.stop()
        registry.close_all()

    app = FastAPI(
        dependencies=[Depends(check_secret)],
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.projects = registry
    app.state.meaning = service
    app.state.mcp = mcp
    app.state.engine = engine
    app.add_route("/mcp", mcp_server.mcp_app(mcp))  # its own run-token check, not the secret
    app.include_router(projects.router(registry, service))
    app.include_router(meaning_routes.router(service))
    app.include_router(calc_routes.router(registry))
    app.include_router(deliverables_api.router(registry))
    app.include_router(engine_routes.settings_router(ai_http))
    app.include_router(engine_routes.briefs_router(engine))

    @app.middleware("http")
    async def learn_base_url(request: Request, call_next):
        # Claude Code reaches the MCP server at the core's own address.
        if engine.base_url is None:
            engine.base_url = str(request.base_url)
        return await call_next(request)

    @app.exception_handler(RecordsError)
    async def records_error(request: Request, exc: RecordsError) -> JSONResponse:
        return JSONResponse({"error": exc.text}, status_code=exc.status)

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
        return await chat.respond(request, engine)

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

    @app.get("/settings/search")
    def search_status() -> dict:
        own_key = keys.get_key(web_search.KEY_USER) is not None
        native = keys.get_key("anthropic") is not None or bool(claude_code.saved()["on"])
        setting = settings.load().get("search_provider")
        provider = web_search.provider_name(setting=setting, own_key=own_key, native=native)
        return {"provider": provider, "own_key": own_key}

    @app.put("/settings/search-key")
    def save_search_key(body: SearchKeyIn) -> JSONResponse:
        try:
            keys.set_key(web_search.KEY_USER, body.value)
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
            roles.choose("lead", ModelChoice("anthropic", body.id))
        except OSError:
            return JSONResponse({"error": copy.MODEL_NOT_SAVED}, status_code=503)
        return JSONResponse({"id": body.id})

    return app
