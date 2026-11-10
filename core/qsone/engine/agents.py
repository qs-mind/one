"""The fixed team's specs, their size tests, building a PydanticAI agent, and the history trim.

The fixed team is two: the Lead QS and the Checking QS. Their instructions are `.txt` files in
`instructions/`, written as principles (Mizan rule 1), with a size test: Lead QS at most 600
words, Checking QS 400, each specialist the Lead builds 300. Recipes go in tool descriptions.

One of the few engine files that import PydanticAI."""

import json
import re
from functools import cache
from pathlib import Path

from pydantic_ai.models.wrapper import WrapperModel

from qsone import copy
from qsone.engine.tools import REGISTRY
from qsone.engine.tools_records import RECORDS_TOOLS
from qsone.engine.types import AgentSpec

LEAD_WORDS, CHECKER_WORDS, SPECIALIST_WORDS = 600, 400, 300
_INSTRUCTIONS = Path(__file__).parent / "instructions"

# Plan 5's tools by default (its decision 7), each once it is registered. Web work, price
# proposals, the Sandbox and Connector calls go to specialists the Lead builds, which keeps the
# Lead's context small; the Checking QS reads only, and never goes online.
LEAD_TOOLS = (
    "project_map",
    "files_list",
    "files_read",
    "compare_files",
    "boq_preview",
    "boq_import",
    "boq_price_from_sheet",
    "ask_engineer",
    "prices_lookup",
    "note_lesson",
    "connector_tools",
    "understood",  # Plan 8: the "I understood this" card
    "show",  # decision 16.1: a view built from ONE's blocks (qsone/view.py)
    "record_finding",  # Phase 1 (C4): engine/findings.py
    "raise_finding",
)
CHECKER_TOOLS = ("files_list", "files_read", "sandbox_rerun")


def _registered(names: tuple[str, ...]) -> tuple[str, ...]:
    import qsone.tools  # noqa: F401 - registers every Plan 5 tool; it imports the engine
    from qsone.engine import finding_tools  # noqa: F401 - registers the Finding tools

    return tuple(name for name in names if name in REGISTRY)


def _checker_may(name: str) -> bool:
    tool = REGISTRY[name]
    return tool.risk == "read" and tool.risk_for is None and "checker" in tool.roles


def words(text: str) -> int:
    return len(text.split())


@cache
def _instructions(name: str) -> str:
    return (_INSTRUCTIONS / name).read_text(encoding="utf-8").strip()


def lead_spec() -> AgentSpec:
    """The Lead QS: the Project Records tools, every team tool, Plan 5's Lead tools and the
    outputs tools (Plan 6)."""
    from qsone.deliverables.tools import OUTPUTS_TOOLS
    from qsone.engine import team, tool_groups  # team registers the team tools

    return AgentSpec(
        id="lead-qs",
        name=copy.ROLE_LEAD,
        role="lead",
        instructions=_instructions("lead_qs.txt"),
        tools=(
            *RECORDS_TOOLS,
            *team.TEAM_TOOLS,
            *_registered(LEAD_TOOLS),
            *OUTPUTS_TOOLS,
            tool_groups.OPEN,  # most of these are sent when the Brief opens them
        ),
        tier="lead",
    )


def checker_spec() -> AgentSpec:
    """The Checking QS: read tools only, never online. The Lead never builds it."""
    found = (*RECORDS_TOOLS, *_registered(CHECKER_TOOLS))
    return AgentSpec(
        id="checking-qs",
        name=copy.ROLE_CHECKER,
        role="checker",
        instructions=_instructions("checking_qs.txt"),
        tools=tuple(name for name in found if _checker_may(name)),
        tier="checker",
    )


def build_agent(spec: AgentSpec, model, toolset, *, output_type=str):
    """A PydanticAI agent for one run of `spec` on `model`, with `toolset` (or no tools) and
    the history trim. The runner gives `output_type` (with deferred calls, for the Lead)."""
    from pydantic_ai import Agent

    return Agent(
        RequestHistory(model),
        name=spec.id,
        instructions=spec.instructions,
        toolsets=None if toolset is None else [toolset],
        output_type=output_type,
    )


class RequestHistory(WrapperModel):
    """Compact only the provider request; PydanticAI's durable run keeps full evidence.

    Wrap outside the cost/tool wrappers so their accounting sees what is actually sent.
    No per-run cache: rebuilding from a checkpoint applies the same deterministic trim.
    """

    async def request(self, messages, model_settings, model_request_parameters):
        return await self.wrapped.request(
            trim_history(messages), model_settings, model_request_parameters
        )

    def request_stream(self, messages, model_settings, model_request_parameters, run_context=None):
        return self.wrapped.request_stream(
            trim_history(messages), model_settings, model_request_parameters, run_context
        )


# History --------------------------------------------------------------------------------------

# Every request carries the whole history: past this many tokens of tool results (ONE's estimate,
# `request_size`), the oldest become short stubs. 3,500 holds a search's hits and a read page.
# The trim is deterministic, so unchanged older requests keep the same stubs for caching.
RESULTS_TOKENS = 3_500
_ID = re.compile(r'"(\w*id)"\s*:\s*"([^"]{1,80})"|\b(file)(?:_id)?:\s?([0-9a-f]{32})\b')
_VALUE = re.compile(r'"value"\s*:\s*"([^"]{1,40})"')
_STUB = "[earlier "


def _results(messages: list) -> int:
    from pydantic_ai.messages import ModelRequest, RetryPromptPart, ToolReturnPart

    from qsone.engine import request_size

    return sum(
        request_size.estimate(_text(p.content))
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart | RetryPromptPart)
    )


def _text(content) -> str:
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def ids_in(content, most: int = 8) -> list[str]:
    """The record ids a tool result (or a call's arguments) names, as "name=id", first `most`."""
    found: dict[str, str] = {}  # id -> its first name
    for a, b, c, d in _ID.findall(_text(content)):
        found.setdefault(b or d, a or c)
    return [f"{name}={value}" for value, name in found.items()][:most]


def _summary(tool_name: str, content, args: dict | None = None) -> str:
    """A stub for a tool result: its ids and values, and, for a tool that only reads, the call
    that reads it again."""
    text = _text(content)
    if text.startswith("not done:"):  # a refusal stays one (engine.truth reads it: done or not)
        return text.split("\n", 1)[0][:300]
    if tool_name in ("files_read", "read_chunk"):
        from qsone.records.key_lines import key_lines

        kept_lines = []
        locator = ""
        size = 0
        seen_locators = set()
        for line in text.splitlines():
            if tool_name == "read_chunk" and line.startswith("{"):
                try:
                    header = json.loads(line)
                    locator = (
                        "Key lines "
                        + json.dumps(
                            {"file_id": header.get("file_id"), **header.get("locator", {})},
                            ensure_ascii=False,
                        )
                        + ":"
                    )
                except ValueError:
                    pass
            elif line.startswith("Key lines "):
                locator = line
                size = 0
            elif locator and key_lines(line) and size + len(line) + 1 <= 600:
                if locator not in seen_locators:
                    kept_lines.append(locator)
                    seen_locators.add(locator)
                kept_lines.append(line)
                size += len(line) + 1
            elif tool_name == "files_read":
                locator = ""
        again = f"call {tool_name} {json.dumps(args or {}, ensure_ascii=False)}"
        return (
            f"{_STUB}{tool_name} result, trimmed to save room:\n"
            + "\n".join(kept_lines)
            + "\nyou read this; its full text was shortened to save room — "
            "the key lines above are from it; "
            + again
            + " to read it again before quoting other text]"
        )
    ids = ids_in(text, 20)
    values = list(dict.fromkeys(_VALUE.findall(text)))[:20]
    tool = REGISTRY.get(tool_name)
    again = None
    if args is not None and tool is not None and tool.risk == "read" and not tool.writes:
        again = f"call {tool_name} {json.dumps(args, ensure_ascii=False)} to read it again"
    kept = "; ".join(
        part
        for part in (
            f"ids {', '.join(ids)}" if ids else "",
            f"values {', '.join(values)}" if values else "",
            again or "",
        )
        if part
    )
    return f"{_STUB}{tool_name} result, trimmed to save room{': ' + kept if kept else ''}]"


def trim_history(messages: list, *, limit_tokens: int = RESULTS_TOKENS) -> list:
    """With at most `limit_tokens` of tool results, the history as it is. Over it, the oldest
    successful tool results become short stubs (`_summary`), oldest first, until the rest fit.
    Errors and results from the Brief’s last two model steps stay whole. The saved history
    is never changed in place. This is a request-only projection, never durable evidence."""
    from dataclasses import replace

    from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

    if _results(messages) <= limit_tokens:
        return messages
    calls = {
        p.tool_call_id: p
        for m in messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    }
    # A model step may return several parallel calls, each in its own request.
    # Protect all results of the last two responses in this Brief.
    from pydantic_ai.messages import UserPromptPart

    start = max(
        (
            i
            for i, m in enumerate(messages)
            if isinstance(m, ModelRequest) and any(isinstance(p, UserPromptPart) for p in m.parts)
        ),
        default=0,
    )
    steps = [i for i, m in enumerate(messages) if i >= start and isinstance(m, ModelResponse)]
    protected = steps[-2] if len(steps) >= 2 else start
    out = list(messages)
    for i, message in enumerate(out[:-1]):
        if not isinstance(message, ModelRequest) or i > protected:
            continue
        parts = list(message.parts)
        for j, part in enumerate(parts):
            if (
                isinstance(part, ToolReturnPart)
                and part.outcome == "success"
                and not (isinstance(part.content, str) and part.content.startswith(_STUB))
            ):
                call = calls.get(part.tool_call_id)
                try:
                    args = call.args_as_dict() if call is not None else None
                except ValueError:
                    args = None
                parts[j] = replace(part, content=_summary(part.tool_name, part.content, args))
                out[i] = replace(message, parts=parts)
                if _results(out) <= limit_tokens:
                    return out
    return out


def tool_returns(history: bytes) -> list[tuple[str, str]]:
    """(tool name, result text) of each successful tool result in a saved history (JSON from
    PydanticAI's `ModelMessagesTypeAdapter`), oldest first."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, ToolReturnPart

    found = []
    for message in ModelMessagesTypeAdapter.validate_json(history):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.outcome == "success":
                content = part.content
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False, default=str)
                found.append((part.tool_name, content))
    return found
