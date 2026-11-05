"""The Connector hub (Plan 5, decision 27): One as an MCP client (the `mcp` SDK's `ClientSession`,
over stdio or streamable HTTP) of every Connector the engineer adds.

- A Connector's settings, never its token, are in settings.json `connectors`; the token is in the
  system key store (user `connector:<name>`). A stdio server gets it in the environment variable
  the engineer named (`token_env`); an HTTP server as `Authorization: Bearer`.
- A stdio server starts with a small environment (no keys of One's), its own error output goes
  nowhere, and it stops with the core (`close`).
- Adding one (`propose`) connects, lists its tools and shows a `connector` card: what it runs or
  reaches, and each tool with its hints. The engineer may let its reading tools run without
  asking, and may pick one of them for web search. The tools as the engineer saw them are kept.
- The risk of a call (`risk`): `online` for a tool that was marked read-only, and neither
  destructive nor open-world, when the engineer allowed reading without asking; `outside` (asks
  every time) for anything else, including a tool added after the engineer saw the list. Hints
  come from the server, so they only ever make a call ask more. A hint counts only when the
  server sets it (the MCP defaults are not assumed).
- `call` runs one call for an agent: what to keep (`keep.apply`) decides what of the arguments is
  stored; every call, failed ones too, is a `connector_calls` row, so a result can be cited;
  embedded files are stored as files; lines that look like orders to an AI are flagged. The text
  is the server's: the tool layer fences it as data and marks the Brief.

No PydanticAI here. Arguments and results are never logged."""

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from typing import Literal
from urllib.parse import unquote, urlsplit

import httpx2
import mcp_types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from qsone import copy, keys, settings
from qsone.engine.types import Card, Risk, read_answer
from qsone.records import files, hidden, keep
from qsone.records.extract import Piece
from qsone.records.project import Records, RecordsError
from qsone.tools import cite
from qsone.tools.cite import SourceRef
from qsone.web.search import SearchFailed, SearchHit, as_hit

log = logging.getLogger(__name__)

SETTING = "connectors"  # settings.json
KEY_PREFIX = "connector:"  # the key store user of a Connector's token
START_TIMEOUT = 20.0  # seconds for a server to start and answer
CALL_TIMEOUT = 120.0  # seconds for one call
MAX_TOOLS = 500
PURPOSE_CHARS = 200
_NAME = re.compile(r"[a-z0-9-]{2,40}")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_ENV = ("PATH", "SYSTEMROOT", "HOME", "USERPROFILE", "LANG")  # all a stdio server is given
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_GONE = {types.CONNECTION_CLOSED, types.REQUEST_TIMEOUT}  # MCP errors that mean the server is gone
READ = "read_without_asking"  # the card's two questions
SEARCH = "search"
NO_SEARCH = "none"
_MIME_KINDS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/pdf": "pdf",
    "text/csv": "csv",
    "text/plain": "txt",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

Transport = Literal["stdio", "http"]


class ConnectorError(Exception):
    """A request the engineer or the model can fix: `text` says how; `status` for the screen."""

    def __init__(self, text: dict, status: int = 422) -> None:
        super().__init__(text["en"])
        self.text = text
        self.status = status


class ConnectorDown(Exception):
    """The server did not start, or did not answer in time, or broke off."""


class _Refused(Exception):
    """The server refused the request itself (an MCP error); its words are untrusted."""


def _good_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if not parts.hostname:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOOPBACK)


@dataclass(frozen=True)
class ConnectorConfig:
    """One Connector, as saved. Raises `ConnectorError` (CONNECTOR_BAD) when it cannot work: a
    name of 2–40 small letters, digits or dashes; a command for stdio; an https:// address (or
    http:// on this computer) for http."""

    name: str
    transport: Transport
    command: tuple[str, ...] | None = None
    url: str | None = None
    read_without_asking: bool = False
    enabled: bool = True
    search_tool: str | None = None
    token_env: str | None = None  # stdio: the environment variable that carries the token
    tools: tuple[dict, ...] = ()  # {name, purpose, read_only, destructive, open_world}, as the
    # engineer saw them when adding it

    def __post_init__(self) -> None:
        command = tuple(self.command) if self.command is not None else None
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "tools", tuple(dict(t) for t in self.tools))
        ok = isinstance(self.name, str) and _NAME.fullmatch(self.name) is not None
        if self.transport == "stdio":
            ok = ok and bool(command) and self.url is None
            ok = ok and all(isinstance(part, str) and part and "\0" not in part for part in command)
        elif self.transport == "http":
            ok = ok and command is None and _good_url(self.url)
        else:
            ok = False
        if self.token_env is not None and not _ENV_NAME.fullmatch(str(self.token_env)):
            ok = False
        if not ok:
            raise ConnectorError(copy.CONNECTOR_BAD)

    @property
    def runs(self) -> str:
        """What it runs or reaches, in the engineer's own words."""
        return " ".join(self.command) if self.command else str(self.url)

    def as_json(self) -> dict:
        found = asdict(self)
        found["command"] = list(self.command) if self.command else None
        found["tools"] = [dict(t) for t in self.tools]
        return found

    @classmethod
    def from_json(cls, found: object) -> "ConnectorConfig | None":
        """A saved entry, or None for one that does not fit (the engineer may edit the file)."""
        if not isinstance(found, dict):
            return None
        names = {f for f in cls.__dataclass_fields__}
        try:
            fields = {k: v for k, v in found.items() if k in names}
            tools = fields.get("tools") or ()
            fields["tools"] = tuple(t for t in tools if isinstance(t, dict) and "name" in t)
            return cls(**fields)
        except (ConnectorError, TypeError):
            return None


def _hints(tool: dict) -> tuple[bool, bool, bool]:
    return bool(tool.get("read_only")), bool(tool.get("destructive")), bool(tool.get("open_world"))


def _reads_only(tool: dict) -> bool:
    """Marked read-only, and not destructive or open-world: the only tools that may run without
    asking."""
    read_only, destructive, open_world = _hints(tool)
    return read_only and not destructive and not open_world


def _describe(tool: types.Tool) -> dict:
    hints = tool.annotations or types.ToolAnnotations()
    purpose = tool.description or hints.title or ""
    return {
        "name": tool.name,
        "purpose": " ".join(purpose.split())[:PURPOSE_CHARS],
        "read_only": hints.read_only_hint is True,
        "destructive": hints.destructive_hint is True,
        "open_world": hints.open_world_hint is True,
        "schema": tool.input_schema if isinstance(tool.input_schema, dict) else {},
    }


def _snapshot(tool: dict) -> dict:
    return {k: tool[k] for k in ("name", "purpose", "read_only", "destructive", "open_world")}


def compact_args(schema: dict) -> str:
    """A tool's arguments in one line: `to (string, required), body (string)`."""
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return "none"
    required = set(schema.get("required") or ())
    parts = []
    for key, spec in properties.items():
        kind = spec.get("type", "any") if isinstance(spec, dict) else "any"
        kind = "/".join(map(str, kind)) if isinstance(kind, list) else str(kind)
        parts.append(f"{key} ({kind}{', required' if key in required else ''})")
    return ", ".join(parts)


def _environment(config: ConnectorConfig, token: str | None) -> dict[str, str]:
    env = {k: os.environ[k] for k in _ENV if k in os.environ}
    if token and config.token_env:
        env[config.token_env] = token
    return env


@contextlib.asynccontextmanager
async def _transport(config: ConnectorConfig, token: str | None):
    if config.transport == "stdio":
        params = StdioServerParameters(
            command=config.command[0],
            args=list(config.command[1:]),
            env=_environment(config, token),
        )
        with open(os.devnull, "w", encoding="utf-8") as nowhere:  # its own words: not logged
            async with stdio_client(params, errlog=nowhere) as streams:
                yield streams
    else:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        timeout = httpx2.Timeout(30.0, read=300.0)
        async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http:
            async with streamable_http_client(config.url, http_client=http) as streams:
                yield streams


class _Live:
    """One running connection, owned by its own task (the SDK's task groups must be entered and
    left in one task). `close` stops it; a stdio server is stopped with it."""

    def __init__(self, config: ConnectorConfig, token: str | None) -> None:
        self.session: ClientSession | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self.task = asyncio.create_task(self._run(config, token), name=f"connector {config.name}")

    async def _run(self, config: ConnectorConfig, token: str | None) -> None:
        try:
            async with contextlib.AsyncExitStack() as stack:
                read, write = await stack.enter_async_context(_transport(config, token))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.session = session
                self._ready.set()
                await self._stop.wait()
        except Exception as error:  # the server's failure, never ours to raise
            log.warning("Connector %s stopped: %s", config.name, type(error).__name__)
        finally:
            self.session = None
            self._ready.set()

    @property
    def up(self) -> bool:
        return self.session is not None and not self.task.done()

    async def ready(self, timeout: float) -> ClientSession:
        try:
            async with asyncio.timeout(timeout):
                await self._ready.wait()
        except TimeoutError:
            raise ConnectorDown() from None
        if self.session is None:
            raise ConnectorDown()
        return self.session

    async def close(self) -> None:
        self._stop.set()
        done, _ = await asyncio.wait({self.task}, timeout=15)
        if not done:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task


async def _list(session: ClientSession) -> list[dict]:
    found: list[dict] = []
    cursor = None
    while len(found) < MAX_TOOLS:
        params = types.PaginatedRequestParams(cursor=cursor) if cursor else None
        page = await session.list_tools(params=params)
        found += [_describe(t) for t in page.tools]
        cursor = page.next_cursor
        if not cursor:
            break
    return found[:MAX_TOOLS]


_ACTIVE: "ConnectorHub | None" = None


def active() -> "ConnectorHub | None":
    """The core's hub, once started. `connector_call`'s argument check and its risk use it: the
    tool layer gives them no context."""
    return _ACTIVE


class ConnectorHub:
    def __init__(
        self, *, start_timeout: float = START_TIMEOUT, call_timeout: float = CALL_TIMEOUT
    ) -> None:
        self.start_timeout = start_timeout
        self.call_timeout = call_timeout
        self._live: dict[str, _Live] = {}
        self._listed: dict[str, list[dict]] = {}  # the tools each server listed last
        self._locks: dict[str, asyncio.Lock] = {}
        self._background: set[asyncio.Task] = set()

    # The core's lifetime ---------------------------------------------------------------------

    def start(self) -> None:
        """Makes this the core's hub. Servers start only when first used."""
        global _ACTIVE
        _ACTIVE = self

    async def close(self) -> None:
        """Stops every server and every Connector card still waiting."""
        global _ACTIVE
        for task in list(self._background):
            task.cancel()
        for task in list(self._background):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        for name in list(self._live):
            await self._drop(name)
        if _ACTIVE is self:
            _ACTIVE = None

    def background(self, work: Awaitable) -> asyncio.Task:
        """`work` as a task that `close` cancels (a Connector card waiting in Settings)."""
        task = asyncio.ensure_future(work)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    # Saved Connectors ------------------------------------------------------------------------

    def configs(self) -> list[ConnectorConfig]:
        saved = settings.load().get(SETTING)
        found = map(ConnectorConfig.from_json, saved if isinstance(saved, list) else [])
        return [c for c in found if c is not None]

    def config(self, name: str) -> ConnectorConfig | None:
        return next((c for c in self.configs() if c.name == name), None)

    def _save(self, configs: list[ConnectorConfig]) -> None:
        settings.save(SETTING, [c.as_json() for c in configs])

    def _need(self, name: str) -> ConnectorConfig:
        found = self.config(name)
        if found is None:
            raise ConnectorError(copy.CONNECTOR_NOT_FOUND, 404)
        return found

    def listing(self) -> list[dict]:
        """The Connectors for the Settings screen: never a token, only whether one is kept."""
        return [self.entry(c) for c in self.configs()]

    def entry(self, config: ConnectorConfig) -> dict:
        return {
            "name": config.name,
            "transport": config.transport,
            "runs": config.runs,
            "enabled": config.enabled,
            "tools": len(config.tools),
            "read_without_asking": config.read_without_asking,
            "search_tool": config.search_tool,
            "token": keys.get_key(KEY_PREFIX + config.name) is not None,
        }

    async def remove(self, name: str) -> None:
        """Raises `ConnectorError` (404) for an unknown name and `KeyringError` when the key
        store is down (then nothing is removed)."""
        self._need(name)
        keys.delete_key(KEY_PREFIX + name)
        self._save([c for c in self.configs() if c.name != name])
        self._listed.pop(name, None)
        await self._drop(name)

    async def set_enabled(self, name: str, on: bool) -> ConnectorConfig:
        found = replace(self._need(name), enabled=on)
        self._save([found if c.name == name else c for c in self.configs()])
        if not on:
            await self._drop(name)
        return found

    # Connections -----------------------------------------------------------------------------

    async def _drop(self, name: str) -> None:
        live = self._live.pop(name, None)
        if live is not None:
            await live.close()

    async def _session(self, config: ConnectorConfig) -> ClientSession:
        async with self._locks.setdefault(config.name, asyncio.Lock()):
            live = self._live.get(config.name)
            if live is not None and live.up:
                return live.session
            await self._drop(config.name)
            live = self._live[config.name] = _Live(config, keys.get_key(KEY_PREFIX + config.name))
            try:
                return await live.ready(self.start_timeout)
            except ConnectorDown:
                await self._drop(config.name)
                raise

    async def _probe(self, config: ConnectorConfig, token: str | None) -> list[dict]:
        """The tools of a server not added yet; the connection is closed again."""
        live = _Live(config, token)
        try:
            session = await live.ready(self.start_timeout)
            async with asyncio.timeout(self.call_timeout):
                return await _list(session)
        except (ConnectorDown, TimeoutError):
            raise ConnectorDown() from None
        except Exception as error:
            log.warning(
                "Connector %s did not list its tools: %s", config.name, type(error).__name__
            )
            raise ConnectorDown() from None
        finally:
            await live.close()

    async def _call_tool(self, config: ConnectorConfig, tool: str, args: dict):
        """One tools/call. Raises `ConnectorDown` or `_Refused`."""
        try:
            session = await self._session(config)
            async with asyncio.timeout(self.call_timeout):
                return await session.call_tool(tool, args)
        except ConnectorDown:
            raise
        except MCPError as error:
            if error.code not in _GONE:
                raise _Refused(" ".join(error.message.split())[:500]) from None
            await self._drop(config.name)
            raise ConnectorDown() from None
        except Exception as error:
            log.warning("Connector %s call failed: %s", config.name, type(error).__name__)
            await self._drop(config.name)
            raise ConnectorDown() from None

    # Tools and risks -------------------------------------------------------------------------

    async def tools(self, name: str) -> list[dict]:
        """The tools the server lists now: name, purpose (≤ 200 characters), args (compact),
        hints and the risk of calling it. Raises `ConnectorError` (not found) or
        `ConnectorDown`."""
        config = self._need(name)
        try:
            session = await self._session(config)
            async with asyncio.timeout(self.call_timeout):
                listed = await _list(session)
        except ConnectorDown:
            raise
        except Exception as error:
            log.warning("Connector %s did not list its tools: %s", name, type(error).__name__)
            await self._drop(name)
            raise ConnectorDown() from None
        self._listed[name] = listed
        return [
            {
                "name": t["name"],
                "purpose": t["purpose"],
                "args": compact_args(t["schema"]),
                "hints": dict(
                    zip(("read_only", "destructive", "open_world"), _hints(t), strict=True)
                ),
                "risk": self.risk(name, t["name"]),
            }
            for t in listed
        ]

    def known_tools(self, name: str) -> set[str]:
        """The tools the engineer saw when adding it, and those the server listed since."""
        config = self.config(name)
        if config is None:
            return set()
        return {t["name"] for t in config.tools} | {t["name"] for t in self._listed.get(name, ())}

    def risk(self, name: str, tool: str) -> Risk:
        """`online` for a reading tool the engineer let run without asking; `outside` for any
        other. A switched-off or unknown Connector is `read`: its call runs nothing."""
        config = self.config(name)
        if config is None or not config.enabled:
            return "read"
        seen = next((t for t in config.tools if t["name"] == tool), None)
        now = next((t for t in self._listed.get(name, ()) if t["name"] == tool), None)
        if (
            config.read_without_asking
            and seen is not None
            and _reads_only(seen)
            and (now is None or _reads_only(now))
        ):
            return "online"
        return "outside"

    # Adding a Connector ----------------------------------------------------------------------

    async def propose(
        self,
        config: ConnectorConfig,
        token: str | None,
        *,
        ask: Callable[[Card], Awaitable[str]],
    ) -> bool:
        """Connects, lists its tools, shows the `connector` card and saves it on yes: the
        settings in settings.json, the token in the key store. Raises `ConnectorError` for a
        name already added, `ConnectorDown` when it does not start or list its tools, and
        `KeyringError` when the key store is down (then nothing is saved)."""
        if self.config(config.name) is not None:
            raise ConnectorError(copy.CONNECTOR_NAME_TAKEN, 409)
        listed = await self._probe(config, token)
        card = _install_card(config, listed)
        answer = read_answer(card, await ask(card))
        if answer["choice"] != "yes":
            return False
        readable = [t["name"] for t in listed if t["read_only"]]
        search = answer["answers"].get(SEARCH)
        saved = replace(
            config,
            read_without_asking=answer["answers"].get(READ) == "yes",
            search_tool=search if search in readable else None,
            enabled=True,
            tools=tuple(_snapshot(t) for t in listed),
        )
        if self.config(config.name) is not None:  # added meanwhile
            raise ConnectorError(copy.CONNECTOR_NAME_TAKEN, 409)
        if token:
            keys.set_key(KEY_PREFIX + config.name, token)
        self._save([*self.configs(), saved])
        self._listed[config.name] = listed
        return True

    # Calls ----------------------------------------------------------------------------------

    async def call(self, ctx, name: str, tool: str, args: dict) -> str:
        """One call for an agent, rendered with its `connector:<name>/<call id>` source. A
        world failure is a `not done:` result. Raises `RecordsError` (not found) for the model
        to fix."""
        config = self.config(name)
        if config is None:
            raise RecordsError(copy.CONNECTOR_NOT_FOUND, field="connector")
        if not config.enabled:
            return cite.not_done(copy.CONNECTOR_OFF)
        if config.transport == "http" and ctx.services.on_device(ctx.rec):
            return cite.not_done(copy.ON_DEVICE_NO_ONLINE)
        target: Records = ctx.rec if ctx.rec is not None else ctx.services.engineer()
        kept, dropped = await keep.apply(ctx, args)
        stored = kept | {f: f"(not kept: {copy.KEEP_KINDS[k]['en']})" for f, k in dropped.items()}
        call_id = uuid.uuid4().hex
        at = ctx.services.clock()
        row = {
            "id": call_id,
            "at": at.isoformat(timespec="seconds"),
            "actor": ctx.agent.name["en"],
            "brief_id": ctx.brief_id,
            "connector": name,
            "tool": tool,
            "args": json.dumps(stored, ensure_ascii=False),
        }
        try:
            result = await self._call_tool(config, tool, args)
        except ConnectorDown:
            await asyncio.to_thread(_log_call, target, row, ok=False)
            return cite.not_done(copy.CONNECTOR_DOWN, retry_online=config.transport == "http")
        except _Refused as refused:
            await asyncio.to_thread(_log_call, target, row, ok=False)
            return cite.render(f"{name}: the Connector refused this call: {refused}")
        stored_files, notes = await _keep_attachments(ctx, target, name, result)
        await asyncio.to_thread(
            _log_call,
            target,
            row,
            ok=not result.is_error,
            result_sha256=hashlib.sha256(
                result.model_dump_json(by_alias=True).encode()
            ).hexdigest(),
            file_ids=[f.id for f in stored_files],
        )
        return _render(name, tool, call_id, at.strftime("%Y-%m-%d %H:%M UTC"), result, notes)

    # Web search through a Connector ------------------------------------------------------------

    def search_provider(self) -> "ConnectorSearch | None":
        """The search Connector the engineer picked (the 4th search option), or None."""
        found = next((c for c in self.configs() if c.enabled and c.search_tool), None)
        return None if found is None else ConnectorSearch(self, found.name, found.search_tool)


def _install_card(config: ConnectorConfig, listed: list[dict]) -> Card:
    runs = (
        copy.fill(copy.CONNECTOR_RUNS, command=config.runs)
        if config.transport == "stdio"
        else copy.fill(copy.CONNECTOR_REACHES, url=config.runs)
    )
    readable = [t["name"] for t in listed if t["read_only"]]
    questions = []
    if any(_reads_only(t) for t in listed):
        questions.append(
            {"id": READ, "text": "Use its reading tools without asking?", "options": ["yes", "no"]}
        )
    if readable:
        questions.append(
            {
                "id": SEARCH,
                "text": "Use one of its reading tools for web search?",
                "options": [NO_SEARCH, *readable],
            }
        )
    return Card(
        id=uuid.uuid4().hex,
        kind="connector",
        title=copy.fill(copy.CONNECTOR_ASK_ADD, connector=config.name),
        detail=runs,
        options=("yes", "no"),
        payload={
            "connector": {"name": config.name, "transport": config.transport, "runs": config.runs},
            "tools": [_snapshot(t) for t in listed],
            "questions": questions,
        },
    )


def _log_call(
    rec: Records,
    row: dict,
    *,
    ok: bool,
    result_sha256: str | None = None,
    file_ids: list[str] | None = None,
) -> None:
    with rec.write(row["actor"]) as conn:
        conn.execute(
            "INSERT INTO connector_calls(id, at, actor, brief_id, connector, tool, args, ok,"
            " result_sha256, file_ids) VALUES (:id, :at, :actor, :brief_id, :connector, :tool,"
            " :args, :ok, :result_sha256, :file_ids)",
            row
            | {
                "ok": int(ok),
                "result_sha256": result_sha256,
                "file_ids": json.dumps(file_ids or []),
            },
        )


def _file_name(connector: str, uri: str | None, mime: str | None, n: int) -> str:
    name = unquote(urlsplit(uri or "").path.rsplit("/", 1)[-1]) if uri else ""
    name = " ".join(re.sub(r"[\x00-\x1f/\\]", " ", name).split())[:120]
    kind = _MIME_KINDS.get((mime or "").split(";")[0].strip().lower())
    if not name:
        name = f"{connector} attachment {n}"
    if kind and not name.lower().endswith(f".{kind}"):
        name = f"{name}.{kind}"
    return name


async def _keep_attachments(ctx, target: Records, connector: str, result) -> tuple[list, list]:
    """Embedded files and images stored as files in `target`; a note for each."""
    stored, notes = [], []
    for n, block in enumerate(result.content, 1):
        if isinstance(block, types.EmbeddedResource):
            res = block.resource
            if isinstance(res, types.BlobResourceContents):
                try:
                    data = base64.b64decode(res.blob, validate=True)
                except ValueError:
                    notes.append(f"attachment {n} was not kept: it is damaged")
                    continue
            else:
                data = res.text.encode()
            name = _file_name(connector, str(res.uri), res.mime_type, n)
        elif isinstance(block, types.ImageContent):
            try:
                data = base64.b64decode(block.data, validate=True)
            except ValueError:
                notes.append(f"image {n} was not kept: it is damaged")
                continue
            name = _file_name(connector, None, block.mime_type, n)
        else:
            continue
        try:
            info = await asyncio.to_thread(
                files.add_file,
                target,
                name,
                data,
                actor=ctx.agent.name["en"],
                embedder=ctx.embedder,
            )
        except RecordsError as error:
            notes.append(f"attachment {n} was not kept: {error.text['en']}")
            continue
        stored.append(info)
        notes.append(
            f"attachment kept: file:{info.id} «{info.name}» ({info.kind}); read it with files_read"
        )
    return stored, notes


def _texts(result) -> list[str]:
    found = []
    for block in result.content:
        if isinstance(block, types.TextContent):
            found.append(block.text)
        elif isinstance(block, types.ResourceLink):
            found.append(f"link: {block.uri}")
        elif isinstance(block, types.AudioContent):
            found.append("(audio, not kept)")
    if not found and result.structured_content is not None:
        found.append(json.dumps(result.structured_content, ensure_ascii=False))
    return found


def _render(name: str, tool: str, call_id: str, read: str, result, notes: list[str]) -> str:
    texts = _texts(result)
    flags = hidden.ai_instruction_flags(Piece({"part": n}, t) for n, t in enumerate(texts, 1))
    notes = [
        *(
            f"flag: part {f.locator['part']} looks like an order to an AI: «{f.excerpt}»"
            for f in flags
        ),
        *notes,
    ]
    if result.is_error:
        head = f"{name}: {tool} reported an error; nothing from it can be cited."
        return cite.render(head + "\n" + "\n\n".join(texts), notes=notes)
    source = SourceRef(f"connector:{name}/{call_id}", f"{name}: {tool}", read)
    body = "\n\n".join(texts) or "(no text)"
    return cite.render(f"{name}: {tool} answered.\n{body}", sources=[source], notes=notes)


# Web search through a Connector -------------------------------------------------------------

_QUERY_KEYS = ("query", "q", "search", "text", "keywords")
_COUNT_KEYS = ("count", "num_results", "max_results", "limit", "n")


def _hits(value) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, dict):
        for key in ("results", "items", "hits", "web"):
            if key in value:
                return _hits(value[key])
        return []
    if not isinstance(value, list):
        return []
    hits = []
    for item in value:
        if isinstance(item, dict) and "url" not in item and isinstance(item.get("link"), str):
            item = item | {"url": item["link"]}
        hit = as_hit(item)
        if hit is not None:
            hits.append(hit)
    return hits


class ConnectorSearch:
    """A search Connector's tool as One's web search: only the query (and how many hits) goes
    out. Its answer is a list of hits, as JSON text or structured content."""

    def __init__(self, hub: ConnectorHub, connector: str, tool: str) -> None:
        self.hub = hub
        self.connector = connector
        self.tool = tool
        self.name = f"connector:{connector}"

    async def _arguments(self, query: str, count: int) -> dict:
        listed = self.hub._listed.get(self.connector)
        if listed is None:
            await self.hub.tools(self.connector)
            listed = self.hub._listed.get(self.connector, [])
        schema = next((t["schema"] for t in listed if t["name"] == self.tool), {})
        properties = schema.get("properties") or {}
        key = next((k for k in _QUERY_KEYS if k in properties), None)
        if key is None:
            key = next((k for k in schema.get("required") or () if k in properties), "query")
        args = {key: query}
        number = next((k for k in _COUNT_KEYS if k in properties), None)
        if number is not None:
            args[number] = count
        return args

    async def search(
        self, query: str, *, country: str | None, lang: str | None, count: int
    ) -> list[SearchHit]:
        config = self.hub.config(self.connector)
        if config is None or not config.enabled:
            raise SearchFailed(copy.CONNECTOR_OFF)
        try:
            result = await self.hub._call_tool(
                config, self.tool, await self._arguments(query, count)
            )
        except (ConnectorDown, ConnectorError):
            raise SearchFailed(copy.CONNECTOR_DOWN, retry_online=True) from None
        except _Refused:
            raise SearchFailed(copy.WEB_SEARCH_BUSY) from None
        if result.is_error:
            raise SearchFailed(copy.WEB_SEARCH_BUSY)
        hits = []
        for text in _texts(result):
            hits += _hits(text)
        if not hits and result.structured_content is not None:
            hits = _hits(result.structured_content)
        return hits[:count]
