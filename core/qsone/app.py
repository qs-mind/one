import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal
from uuid import uuid4

import anthropic
import httpx2
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from keyring.errors import KeyringError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from qsone import (
    about,
    activity,
    chat,
    copy,
    keys,
    models,
    phase1_stubs,
    projects,
    settings,
    settings_routes,
    undo,
    usage,
    workspace,
)
from qsone.account import routes as account_routes
from qsone.account import vault as account_vault
from qsone.account.session import Account
from qsone.backup import routes as backup_routes
from qsone.backup.runner import Backups
from qsone.calc import routes as calc_routes
from qsone.connectors import routes as connector_routes
from qsone.connectors.hub import ConnectorHub
from qsone.deliverables import api as deliverables_api
from qsone.deliverables import events as deliverable_events
from qsone.engine import connectors as engine_connectors
from qsone.engine import mcp_server, roles, tools_records  # noqa: F401 - registers the records tools
from qsone.engine import routes as engine_routes
from qsone.engine.connectors import claude_code
from qsone.engine.runner import Engine
from qsone.engine.types import ModelChoice
from qsone.journey import profile
from qsone.journey import routes as journey_routes
from qsone.meaning import routes as meaning_routes
from qsone.meaning.service import Meaning
from qsone.records.project import RecordsError
from qsone.sandbox import runtime as sandbox_runtime
from qsone.setup import routes as setup_routes
from qsone.setup.runner import Setup
from qsone.tools import services as tool_services  # the package registers every Plan 5 tool
from qsone.web import search as web_search

Provider = Literal["anthropic"]


class AiKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: Provider
    value: str = Field(min_length=1)


class SearchKeyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=500)


class UsageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    on: bool


# The engineer's own zoom (Ctrl/Cmd with = or -) over the screen's fluid scale:
# 80 % to 150 %, in steps of 10 %.
ZOOM_SETTING = "zoom"
ZOOMS = tuple(round(0.8 + 0.1 * n, 1) for n in range(8))


class ZoomIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zoom: float = Field(ge=0.8, le=1.5)


def saved_zoom() -> float:
    """The saved zoom, or 1 when none is saved or it is not one of the steps."""
    value = settings.load().get(ZOOM_SETTING)
    return value if isinstance(value, float) and value in ZOOMS else 1.0


class CrashIn(BaseModel):
    """A crash of the screen or the shell: class and where in our code, never a message."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    origin: Literal["screen", "shell"] = Field(alias="from")
    kind: str = Field(max_length=80)
    where: str = Field(max_length=80)
    version: str = Field(max_length=80)


class PrepareUpdateIn(BaseModel):
    """The version the shell is about to install, so the next start can tell whether it did."""

    model_config = ConfigDict(extra="forbid")

    to: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,80}$")


class ModelIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1, max_length=200)
    connector: str = "anthropic"


def create_app(
    secret: str,
    connectors: Callable[[], list] | None = None,
    models_lister: models.ModelLister | None = None,
    data_dir: Path | None = None,
    meaning: Callable[[projects.Projects], Meaning] | None = None,
    ai_http: httpx2.AsyncClient | None = None,
    sleep: Callable[[float], Awaitable] | None = None,
    setup: Setup | None = None,
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
    retries (default: `asyncio.sleep`). `setup` fetches what ONE needs beyond the installer
    (default: the manifest's parts); tests inject one with a fake hub.
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
    setup = setup or Setup(Path(folder) / "models", sandbox_runtime.root())
    mcp = mcp_server.McpGate()
    connector_hub = ConnectorHub()  # the engineer's MCP Connectors (Plan 5)
    trash = undo.Trash()  # Undo instead of "are you sure?": removals wait out their window here
    engine = Engine(
        projects=registry,
        data_dir=Path(folder),
        connectors=connectors or (lambda: engine_connectors.connectors(http_client=ai_http)),
        sleep=sleep or asyncio.sleep,
        mcp=mcp,
        meaning=service,
    )
    from qsone.records.mapping.facts import mapping_passes
    from qsone.records.mapping.service import Mapping

    mapping = Mapping(
        registry,
        passes=lambda rec: {"approved": mapping_passes},
    )
    sender = usage.Sender()
    account = Account()  # the QS Mind account; its vault keeps the Backup key
    backups = Backups(
        Path(folder), registry, escrow_factory=account.escrow, engineer=engine.engineer_records
    )
    registry.backups = backups

    def settle_backup_key() -> None:
        # Under the Backups lock, so no backup copy writes a key.json while it is wrapped again.
        with backups._lock:
            account_vault.settle_backup_key(account.escrow(), Path(folder))

    account.on_signed_in = settle_backup_key

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        loop = asyncio.get_running_loop()
        # Deliverables are written in worker threads: their events reach the hub on its loop.
        stop_listening = deliverable_events.listen(
            lambda project_id, event: loop.call_soon_threadsafe(activity.publish, project_id, event)
        )
        service.start()
        setup.on_change = lambda state: loop.call_soon_threadsafe(
            activity.publish, "general", {"type": "setup", "setup": state}
        )
        setup.start()  # in its own thread: the core answers meanwhile
        mapping.completed = lambda pid, ids, **options: asyncio.run_coroutine_threadsafe(
            engine.map_project(pid, ids, **options), loop
        )
        mapping.start()
        trash.purge_all()  # what a core that stopped inside an Undo window left
        connector_hub.start()  # a Connector's server starts only when first used
        # The tools' one way out (Plan 5), unless a test gave the engine its own fakes.
        own_services = engine.services is None
        if own_services:
            engine.services = tool_services.services_for(app.state)
        await engine.start()  # never continues a Brief by itself
        backups.start()  # every 30 minutes; closing a project also backs it up
        usage.app_start()  # queued only when the engineer said yes to Usage Stats
        sender.start()  # every 5 minutes
        try:
            async with mcp.running():
                yield
                await engine.shutdown()  # each Brief keeps its Checkpoint
        finally:
            if own_services:
                await engine.services.close()  # after the engine: no Brief uses it now
                engine.services = None
            await connector_hub.close()  # stdio servers stop with the core
            trash.purge_all()  # an Undo window ends with the core
            stop_listening()
            backups.stop()  # waits for a running copy
            sender.stop()
            account.close()  # a sign-in under way stops
        mapping.stop()
        setup.stop()
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
    app.state.setup = setup
    app.state.mcp = mcp
    app.state.engine = engine
    app.state.connectors = connector_hub
    app.state.trash = trash
    app.state.backups = backups
    app.state.account = account
    app.add_route("/mcp", mcp_server.mcp_app(mcp))  # its own run-token check, not the secret
    app.include_router(projects.router(registry, service, engine, mapping))
    app.include_router(meaning_routes.router(service))
    app.include_router(setup_routes.router(setup))
    app.include_router(calc_routes.router(registry))
    app.include_router(deliverables_api.router(registry, trash))
    app.include_router(engine_routes.settings_router(ai_http, trash=trash))
    app.include_router(engine_routes.briefs_router(engine))
    app.include_router(workspace.router(registry, engine.waiting))
    app.add_middleware(workspace.no_store)
    app.include_router(connector_routes.router(connector_hub, trash))
    app.include_router(undo.router(trash))
    app.include_router(backup_routes.router(backups))
    app.include_router(account_routes.router(account))
    app.include_router(journey_routes.router(engine))  # the first launch (Plan 8)
    app.include_router(profile.router(engine, account))  # the engineer's profile (Phase 1)
    registry.country = lambda: profile.country(engine.engineer_records)  # contract Q14
    app.include_router(settings_routes.router(ai_http, trash, engine))  # Phase 1: C10

    @app.middleware("http")
    async def learn_base_url(request: Request, call_next):
        # Claude Code reaches the MCP server at the core's own address.
        if engine.base_url is None:
            engine.base_url = str(request.base_url)
        return await call_next(request)

    @app.exception_handler(RecordsError)
    async def records_error(request: Request, exc: RecordsError) -> JSONResponse:
        return JSONResponse(copy.error(exc.text), status_code=exc.status)

    @app.exception_handler(Exception)
    async def crashed(request: Request, exc: Exception) -> Response:
        usage.crash(exc)  # class and module:line only; the error itself still goes to core.log
        return Response("Internal Server Error", status_code=500)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default echoes the request body, which may hold a key: send only where and why.
        detail = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/about")
    def about_core() -> dict:
        return about.about()

    @app.get("/about/native")
    def about_native() -> dict:
        return about.native()  # the packaging smoke test: every native library loads

    @app.post("/app/prepare-update")
    async def prepare_update(body: PrepareUpdateIn | None = None) -> dict:
        """Before the shell installs an update: every running Brief stops at its Checkpoint,
        the projects are backed up, then every open project is closed. The shell stops the core
        next, installs, and starts One again (or, if the install fails, the core)."""
        paused = await engine.pause_all()
        backed_up = await asyncio.to_thread(backups.run, reason="update")

        def close_open() -> None:
            for project_id, _ in registry.opened():
                registry.close(project_id, back_up=False)  # backed up just now

        await asyncio.to_thread(close_open)
        if body is not None and body.to is not None:
            with suppress(OSError):  # only the Usage Stats event after the restart needs it
                settings.save(usage.UPDATE_SETTING, body.to)
        return {"paused_briefs": paused, "backed_up": backed_up}

    @app.post("/chat")
    async def chat_stream(request: Request) -> Response:
        return await chat.respond(request, engine)

    @app.get("/settings/usage-stats")
    def usage_stats() -> dict:
        return {"on": usage.is_on()}  # None: not asked yet

    @app.put("/settings/usage-stats")
    def choose_usage_stats(body: UsageIn) -> JSONResponse:
        try:
            usage.set_on(body.on)
        except OSError:
            return JSONResponse({}, status_code=503)  # the screen says it in its own words
        return JSONResponse({"on": body.on})

    @app.get("/settings/zoom")
    def zoom() -> dict:
        return {"zoom": saved_zoom()}

    @app.put("/settings/zoom")
    def choose_zoom(body: ZoomIn) -> JSONResponse:
        step = round(body.zoom, 1)  # a step of 10 %: 1.1 stays 1.1, never 1.1000000000000001
        try:
            settings.save(ZOOM_SETTING, step)
        except OSError:
            return JSONResponse({}, status_code=503)  # the screen keeps the zoom for this session
        return JSONResponse({"zoom": step})

    @app.post("/usage/crash", status_code=204)
    def screen_crash(body: CrashIn) -> Response:
        data = body.model_dump(by_alias=True)  # {"from", "kind", "where", "version"}
        if not usage.valid("crash", data):
            detail = [{"loc": ["body"], "msg": "not a crash report", "type": "value_error"}]
            return JSONResponse({"detail": detail}, status_code=422)
        usage.track("crash", **data)
        return Response(status_code=204)

    @app.get("/settings/ai-key")
    def ai_key_status(provider: Provider = "anthropic") -> dict:
        return {"set": keys.get_key(provider) is not None}

    @app.put("/settings/ai-key")
    def save_ai_key(body: AiKeyIn) -> JSONResponse:
        try:
            keys.set_key(body.provider, body.value)
        except KeyringError:
            return JSONResponse(copy.error(copy.KEY_STORE_DOWN), status_code=503)
        return JSONResponse({"set": True})

    @app.get("/settings/search")
    def search_status() -> dict:
        own_key = keys.get_key(web_search.KEY_USER) is not None
        native = keys.get_key("anthropic") is not None or bool(claude_code.saved()["on"])
        setting = settings.load().get("search_provider")
        connector = connector_hub.search_provider() is not None
        provider = web_search.provider_name(
            setting=setting, own_key=own_key, native=native, connector=connector
        )
        return {"provider": provider, "own_key": own_key}

    @app.put("/settings/search-key")
    def save_search_key(body: SearchKeyIn) -> JSONResponse:
        try:
            keys.set_key(web_search.KEY_USER, body.value)
        except KeyringError:
            return JSONResponse(copy.error(copy.KEY_STORE_DOWN), status_code=503)
        return JSONResponse({"set": True})

    @app.get("/settings/models")
    async def list_models() -> JSONResponse:
        key = keys.get_key("anthropic")
        if key is None:
            return JSONResponse(copy.error(copy.NO_KEY), status_code=409)
        try:
            return JSONResponse(await models_lister(key))
        except anthropic.APIError as error:
            # The provider's own words go to core.log; the screen gets a plain {en, ar} pair.
            models.log.warning("Listing the models failed: %s", error)
            return JSONResponse(copy.error(models.plain_error(error)), status_code=502)

    @app.get("/settings/model")
    def lead_model() -> dict:
        lead = roles.saved().get("lead")
        return {"id": lead.model if lead else chat.lead_model_id()}

    @app.put("/settings/model")
    async def choose_lead_model(body: ModelIn) -> JSONResponse:
        try:
            if body.connector == "anthropic":
                roles.choose("lead", ModelChoice(body.connector, body.id))
            else:
                sheet, found = await engine.sheet()

                def count_probe(card, used):
                    if engine.cost_book() is not None:
                        engine.spending.after_response(
                            brief_id=f"check-{uuid4().hex}",
                            project_id=None,
                            run_id=uuid4().hex,
                            role="quick",
                            card=card,
                            input_tokens=used.input_tokens or 0,
                            output_tokens=used.output_tokens or 0,
                        )

                await roles.select_lead(
                    ModelChoice(body.connector, body.id), sheet, found, count_probe
                )
        except OSError:
            return JSONResponse({"error": copy.MODEL_NOT_SAVED}, status_code=503)
        return JSONResponse({"id": body.id})

    # The Phase 1 routes that are declared and not built yet (501). Keep this the last route
    # added: it then never takes a request an older route answers.
    app.include_router(phase1_stubs.router())
    return app
