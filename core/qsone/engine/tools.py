"""One tool registry. Each tool is defined once, as a `Tool`, and served two ways: to PydanticAI as
a toolset (`toolset`), and to Claude Code over MCP (`mcp_server`). Both go through `call`, so
every connector gets the same checks, the same approval gate and the same data-not-orders fence.

`call` does, in order:
1. validate the arguments; a wrong shape goes back as `ModelRetry` naming the field, what is
   allowed and a filled example;
2. for a write tool, return the earlier result when the same call was already made in this
   Brief (a replayed call never writes twice);
3. `gate.guard`: ask the engineer when the tool's risk needs it; "no" raises `Denied`;
4. run the tool; a `RecordsError` becomes `ModelRetry` with its English text, field and example;
5. cut the result into pages of at most 8 KB: a tool with a `page` argument gets the page asked
   for, unless it pages itself; any other is cut with a note;
6. fence a result that carries file, web or email text (`data_text.as_data`) and mark the Brief
   as having read untrusted text.

A deferred tool (the team tools of Task 7) does its real work in `run` too. In the PydanticAI
toolset it raises `CallDeferred` after its arguments validate, and the Brief Runner later runs it
through `call`; over MCP, `call` runs it at once and the MCP call waits for it.

Only this file's `toolset` uses PydanticAI's toolset classes. `ModelRetry` is PydanticAI's, so a
refusal reads the same to every connector. Arguments and results are never logged."""

import asyncio
import dataclasses
import hashlib
import inspect
import json
import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, get_type_hints

from pydantic import BaseModel, ValidationError, create_model
from pydantic_ai import ModelRetry

from qsone import copy
from qsone.engine import data_text
from qsone.engine.store import Store
from qsone.engine.types import AgentSpec, Progress, Risk, TeamHost, Text
from qsone.records.project import Records, RecordsError

if TYPE_CHECKING:
    from qsone.projects import Projects
    from qsone.tools.services import Services

log = logging.getLogger(__name__)

MAX_RESULT = 8 * 1024  # bytes of UTF-8 in one result, fence and note included
_PAGE = MAX_RESULT - 512  # room for the fence and the note
ROLES = frozenset({"lead", "specialist", "checker"})
DENIED = "The engineer said no to {tool}. Do not try it again in this Brief unless asked."


@dataclass(frozen=True)
class Tool:
    name: str
    description: str  # English, for the model: a recipe (Mizan rule 2)
    args: type[BaseModel]
    risk: Risk
    run: Callable[["ToolContext", BaseModel], Awaitable[str]]  # result text for the model
    activity: Callable[[BaseModel], Text]  # Progress Line words
    untrusted: bool = False  # the result carries file, web or email text
    deferred: bool = False  # run by the Brief Runner (team tools, Task 7)
    lead_only: bool = False
    writes: bool = False  # deduplicated per Brief (decision 11)
    example: dict | None = None  # a filled, valid call, shown with every refusal
    self_paged: bool = False  # its own `page` argument pages its result, not `call`
    invalid: Callable[[dict], str] | None = None  # the retry text for arguments that do not
    # validate, for a tool that words its own refusals (the Plan 3 calc tools)
    roles: frozenset[str] = ROLES  # who may be given it: "lead", "specialist", "checker"
    group: str = ""
    risk_for: Callable[[BaseModel], Risk] | None = None  # a risk that depends on the arguments
    # (a Connector's tool); the gate uses it in place of `risk` when set
    allow_for: Callable[[BaseModel], str] | None = None  # what "Allow for this Brief" covers,
    # when narrower than the whole tool (one Connector's one tool)


def allow_key(tool: Tool, args: BaseModel) -> str:
    """What the engineer's "Allow for this Brief" is saved as: the tool's name, or its name and
    `tool.allow_for(args)` (`connector_call:outlook/read_inbox`)."""
    return tool.name if tool.allow_for is None else f"{tool.name}:{tool.allow_for(args)}"


def risk_of(tool: Tool, args: BaseModel) -> Risk:
    """The risk of this call: `tool.risk_for(args)` when the tool has one, else `tool.risk`."""
    return tool.risk if tool.risk_for is None else tool.risk_for(args)


@dataclass
class ToolContext:
    """One agent run's view of its Brief. `rec` is the open project, or None in the General
    chat. `fence` is the run's own data fence (`data_text.new_fence`)."""

    brief_id: str
    run_id: str
    agent: AgentSpec
    rec: Records | None
    store: Store
    host: TeamHost
    fence: str
    embedder: object | None = None
    services: "Services | None" = None  # Plan 5: the only way a tool reaches the outside world
    projects: "Projects | None" = None  # Plan 7: the General chat's tools list the projects


class Denied(Exception):
    """The engineer said no."""


REGISTRY: dict[str, Tool] = {}


def register(tool: Tool) -> Tool:
    """Adds a tool. Raises `ValueError` when its name is taken."""
    if tool.name in REGISTRY:
        raise ValueError(f"a tool named {tool.name!r} is already registered")
    REGISTRY[tool.name] = tool
    return tool


# Plain functions as tools (Plan 6) --------------------------------------------------------------


def _jsonable(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, set | frozenset | tuple):
        return list(value)
    return str(value)


def _as_text(value) -> str:
    return (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=_jsonable)
    )


def _from_function(fn: Callable, group: str, roles: set[str], risk: Risk) -> Tool:
    hints = get_type_hints(fn, include_extras=True)  # keeps Annotated constraints
    params = list(inspect.signature(fn).parameters.values())
    takes_ctx = bool(params) and hints.get(params[0].name) is ToolContext
    fields = {
        p.name: (hints.get(p.name, Any), ... if p.default is p.empty else p.default)
        for p in params[1 if takes_ctx else 0 :]
    }
    args = create_model(f"{fn.__name__}_args", **fields)

    async def run(ctx: ToolContext, parsed: BaseModel) -> str:
        values = {name: getattr(parsed, name) for name in type(parsed).model_fields}
        first = (ctx,) if takes_ctx else ()
        if inspect.iscoroutinefunction(fn):
            out = await fn(*first, **values)
        else:
            out = await asyncio.to_thread(fn, *first, **values)
        return _as_text(out)

    name = fn.__name__
    return Tool(
        name=name,
        description=inspect.getdoc(fn) or "",
        args=args,
        risk=risk,
        run=run,
        activity=lambda _: copy.tool_step(name),
        lead_only=set(roles) == {"lead"},
        writes=risk in ("write", "outside"),
        roles=frozenset(roles),
        group=group,
    )


def register_functions(
    group: str, functions: list[Callable], *, roles: set[str], risk: Risk = "write"
) -> list[Tool]:
    """One `Tool` per plain function: its arguments from the type hints (a first parameter typed
    `ToolContext` gets the run's context), its description from the docstring. A function may be
    async; a plain one runs in a thread. A result that is not text goes back as JSON."""
    unknown = set(roles) - ROLES
    if unknown:
        raise ValueError(f"unknown roles {sorted(unknown)}; use {sorted(ROLES)}")
    return [register(_from_function(fn, group, roles, risk)) for fn in functions]


# call -------------------------------------------------------------------------------------------


def _example_text(tool: Tool) -> str:
    return json.dumps(tool.example or {}, ensure_ascii=False)


def _validate(tool: Tool, args: dict) -> BaseModel:
    try:
        return tool.args.model_validate(args)
    except ValidationError as e:
        if tool.invalid is not None:
            raise ModelRetry(tool.invalid(args)) from None
        first = e.errors()[0]
        where = ".".join(str(p) for p in first["loc"]) or "the arguments"
        raise ModelRetry(
            f"{tool.name}: «{where}»: {first['msg']}. Send it like this: {_example_text(tool)}"
        ) from None


def _write_key(tool: Tool, parsed: BaseModel) -> str:
    canonical = json.dumps(
        parsed.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(f"{tool.name}\n{canonical}".encode()).hexdigest()


def _pages(text: str, limit: int = _PAGE) -> list[str]:
    """`text` in pieces of at most `limit` bytes of UTF-8, cut between characters."""
    data = text.encode()
    pages, start = [], 0
    while start < len(data):
        end = min(start + limit, len(data))
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        pages.append(data[start:end].decode())
        start = end
    return pages or [""]


def _paged(tool: Tool, parsed: BaseModel, text: str) -> tuple[str, str]:
    """The page asked for and the note that follows it."""
    pages = _pages(text)
    if tool.self_paged or "page" not in type(parsed).model_fields:
        return pages[0], ("" if len(pages) == 1 else "\n[cut at 8 KB: ask for less]")
    page = parsed.page
    if not 1 <= page <= len(pages):
        raise ModelRetry(f"{tool.name}: page {page} does not exist; there are {len(pages)}.")
    more = f"\n[more: call again with page={page + 1}; {len(pages)} pages]"
    return pages[page - 1], ("" if page == len(pages) else more)


async def call(name: str, args: dict, ctx: ToolContext) -> str:
    """Runs one tool call for an agent. Raises `ModelRetry` for the model to fix its call and
    `Denied` when the engineer said no; the text returned is at most 8 KB."""
    from qsone.engine.gate import guard

    tool = REGISTRY.get(name)
    if tool is None:
        raise ModelRetry(f"There is no tool «{name}». Use one of the tools you were given.")
    try:
        parsed = _validate(tool, args)
    except ModelRetry as e:
        _refused(ctx, name, copy.words_for(e.message))
        raise
    key = _write_key(tool, parsed) if tool.writes else None
    if key is not None:
        earlier = ctx.store.known_write(ctx.brief_id, key)
        if earlier is not None:
            log.info("tool %s replayed in run %s", name, ctx.run_id)
            return earlier
    await guard(tool, parsed, ctx)
    log.info("tool %s in run %s", name, ctx.run_id)
    try:
        out = await tool.run(ctx, parsed)
    except RecordsError as e:
        say_refused(ctx, e.text)
        _refused(ctx, name, e.text)
        raise ModelRetry(
            f"{tool.name}: {e.text['en']} Field: {e.field or 'none'}. "
            f"Example: {_example_text(tool)}"
        ) from None
    except ModelRetry as e:
        _refused(ctx, name, copy.words_for(e.message))
        raise
    if out.startswith("not done:"):
        _refused(ctx, name, copy.words_for(out.split("\n", 1)[0]))
    page, note = _paged(tool, parsed, out)
    if tool.untrusted:
        page = data_text.as_data(page, source=tool.name, fence=ctx.fence)
        ctx.store.mark_untrusted(ctx.brief_id)
    result = page + note
    if key is not None:
        ctx.store.remember_write(ctx.brief_id, key, result)
    return result


def _refused(ctx: ToolContext, tool: str, text: Text | None) -> None:
    """Tells the Brief that a call of `tool` was refused, with the reason in both languages when
    ONE has it: a reply that says it was done is then flagged with this reason."""
    note = getattr(ctx.host, "note_refusal", None)
    if note is not None:
        note(tool, text)


_HEX_ID = re.compile(r"\s*\b[0-9a-f]{32}\b,?")
_SENTENCE = re.compile(r"(.+?[.؟?!])(\s|$)", re.S)


def _first_sentence(text: str) -> str:
    """A refusal's first sentence, without ids: the rest tells the model how to call again."""
    text = _HEX_ID.sub("", text).strip()
    found = _SENTENCE.match(text)
    return (found[1] if found else text).rstrip(" :،,") or text


def say_refused(ctx: ToolContext, text: dict) -> None:
    """The refusal in the work log, so the engineer sees why a step did not happen."""
    why = {lang: _first_sentence(words) for lang, words in text.items()}
    words = copy.fill(copy.TOOL_REFUSED, why=why)
    ctx.host.emit(Progress(ctx.brief_id, ctx.run_id, ctx.agent.name, words))


# The PydanticAI toolset -------------------------------------------------------------------------

# What only `call`'s check needs: it validates against the whole model, and a refusal names the
# field and shows the example. Every request carries every schema, so they cost on each step.
_CHECK_ONLY = frozenset({"title", "minLength", "maxLength", "minItems", "maxItems", "pattern"})
_NAMED = frozenset({"properties", "patternProperties", "$defs", "definitions"})  # name -> schema
_NULL = {"type": "null"}


def _optional(schema: dict) -> dict:
    """A field that may be left out is sent without its "or null" and its null default."""
    either = schema.get("anyOf")
    if not (isinstance(either, list) and _NULL in either):
        return schema
    rest = [s for s in either if s != _NULL]
    out = {k: v for k, v in schema.items() if k != "anyOf"}
    if out.get("default", 0) is None:
        del out["default"]
    return (rest[0] | out) if len(rest) == 1 else (out | {"anyOf": rest})


def _shape(schema):
    if isinstance(schema, list):
        return [_shape(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k in _NAMED and isinstance(v, dict):  # its keys are names, not keywords
            out[k] = {name: _shape(s) for name, s in v.items()}
        elif k not in _CHECK_ONLY and not (k == "additionalProperties" and v is False):
            out[k] = _shape(v)
    fields = out.get("properties")
    if isinstance(fields, dict):
        needed = set(out.get("required", ()))
        out["properties"] = {
            name: s if name in needed or not isinstance(s, dict) else _optional(s)
            for name, s in fields.items()
        }
    return out


def sent_schema(tool: Tool) -> dict:
    """The tool's argument schema as a model is sent it: its shape, without titles, length and
    count limits, patterns, "no other fields" or "or null" for an optional field."""
    return _shape(tool.args.model_json_schema())


def toolset(names: Sequence[str], ctx: ToolContext):
    """A PydanticAI `FunctionToolset` of the named tools, all run through `call` with `ctx`.
    Raises `KeyError` for a name that is not registered."""
    from pydantic_ai import CallDeferred, ToolFailed
    from pydantic_ai.tools import Tool as AiTool
    from pydantic_ai.toolsets import FunctionToolset

    missing = [n for n in names if n not in REGISTRY]
    if missing:
        raise KeyError(f"no such tools: {missing}")

    def function(tool: Tool):
        async def run(**kwargs) -> str:
            if tool.deferred:
                _validate(tool, kwargs)
                raise CallDeferred()
            try:
                return await call(tool.name, kwargs, ctx)
            except Denied:
                raise ToolFailed(DENIED.format(tool=tool.name)) from None

        return run

    return FunctionToolset(
        [
            AiTool.from_schema(
                function(REGISTRY[name]),
                name=name,
                description=REGISTRY[name].description,
                json_schema=sent_schema(REGISTRY[name]),
            )
            for name in names
        ]
    )
