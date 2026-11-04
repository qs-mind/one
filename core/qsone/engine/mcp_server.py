"""One's tools over MCP (Streamable HTTP) at `/mcp` on the core's own port.

An agent connector that runs its own loop (the Subscription Link, Task 5) reaches One's tools
here. Each agent run gets its own random token from `McpGate.issue`; the token decides which
tools that run sees and is revoked when the run ends. The core's bearer secret is not a run
token: this app sits outside FastAPI's app-wide check and does its own, before it reads anything.
Every call goes through `tools.call`, so the checks, the approval gate and the data fence are the
same as for PydanticAI. The MCP names are the tool names (Claude Code shows `mcp__one__<name>`).

Stateless, with JSON responses: each request is checked and served on its own, and a long call
(a `delegate` the Brief Runner works on) simply keeps its request open until it is done."""

import contextvars
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from qsone.engine import tools
from qsone.engine.tools import DENIED, REGISTRY, Denied, ToolContext

log = logging.getLogger(__name__)

NAME = "one"
_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)


@dataclass(frozen=True)
class RunScope:
    ctx: ToolContext
    tools: tuple[str, ...]


_scope: contextvars.ContextVar[RunScope | None] = contextvars.ContextVar("mcp_run", default=None)


def _result(text: str, *, error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=error)


async def _list_tools(ctx, params) -> types.ListToolsResult:
    scope = _scope.get()
    names = () if scope is None else scope.tools
    return types.ListToolsResult(
        tools=[
            types.Tool(
                name=name,
                description=REGISTRY[name].description,
                input_schema=REGISTRY[name].args.model_json_schema(),
            )
            for name in names
        ]
    )


async def _call_tool(ctx, params: types.CallToolRequestParams) -> types.CallToolResult:
    scope = _scope.get()
    name = params.name
    if scope is None or name not in scope.tools:
        return _result(
            f"There is no tool «{name}». Use one of the tools you were given.", error=True
        )
    try:
        return _result(await tools.call(name, dict(params.arguments or {}), scope.ctx))
    except tools.ModelRetry as e:
        return _result(e.message, error=True)
    except Denied:
        return _result(DENIED.format(tool=name), error=True)
    except Exception:
        log.exception("MCP tool %s failed in run %s", name, scope.ctx.run_id)
        return _result(f"{name} failed inside One. Tell the engineer; do not retry it.", error=True)


class McpGate:
    """Issues and revokes run tokens, and runs the MCP server while the core runs."""

    def __init__(self) -> None:
        self._scopes: dict[str, RunScope] = {}
        self._server = Server(NAME, on_list_tools=_list_tools, on_call_tool=_call_tool)
        self._manager: StreamableHTTPSessionManager | None = None

    def issue(self, scope: RunScope) -> str:
        unknown = [n for n in scope.tools if n not in REGISTRY]
        if unknown:
            raise KeyError(f"no such tools: {unknown}")
        token = secrets.token_urlsafe(32)
        self._scopes[token] = scope
        return token

    def revoke(self, token: str) -> None:
        self._scopes.pop(token, None)

    def scope(self, token: str) -> RunScope | None:
        return self._scopes.get(token)

    @asynccontextmanager
    async def running(self) -> AsyncIterator[None]:
        """In the core's lifespan: a mounted app gets no lifespan of its own."""
        manager = StreamableHTTPSessionManager(
            self._server, json_response=True, stateless=True, security_settings=_SECURITY
        )
        async with manager.run():
            self._manager = manager
            try:
                yield
            finally:
                self._manager = None
                self._scopes.clear()

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self._manager is None:
            await _plain(send, 503, "One's MCP server is not running.")
            return
        await self._manager.handle_request(scope, receive, send)


def _bearer(scope: Scope) -> str | None:
    for key, value in scope.get("headers", ()):
        if key == b"authorization":
            kind, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if kind.lower() == "bearer" else None
    return None


async def _plain(send: Send, status: int, message: str) -> None:
    body = json.dumps({"error": message}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class _McpApp:
    """An ASGI app (a class, so Starlette routes to it as an app, not as an endpoint)."""

    def __init__(self, gate: McpGate) -> None:
        self.gate = gate

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        token = _bearer(scope)
        run = None if token is None else self.gate.scope(token)
        if run is None:
            await _plain(send, 401, "This needs a run token.")
            return
        reset = _scope.set(run)
        try:
            await self.gate.handle(scope, receive, send)
        finally:
            _scope.reset(reset)


def mcp_app(gate: McpGate) -> _McpApp:
    """Streamable HTTP; the tools come from the scope of the request's run token."""
    return _McpApp(gate)
