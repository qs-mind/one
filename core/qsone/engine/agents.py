"""The fixed team's specs, their size tests, building a PydanticAI agent, and the history trim.

The fixed team is two: the Lead QS and the Checking QS. Their instructions are `.txt` files in
`instructions/`, written as principles (Mizan rule 1), with a size test: Lead QS at most 600
words, Checking QS 400, each specialist the Lead builds 300. Recipes go in tool descriptions.

One of the few engine files that import PydanticAI."""

import json
import re
from functools import cache
from pathlib import Path

from qsone import copy
from qsone.engine.tools import REGISTRY
from qsone.engine.tools_records import RECORDS_TOOLS
from qsone.engine.types import AgentSpec

LEAD_WORDS, CHECKER_WORDS, SPECIALIST_WORDS = 600, 400, 300
TRIM_TOKENS = 60_000
_INSTRUCTIONS = Path(__file__).parent / "instructions"

# Plan 5's tools by default (its decision 7), each once it is registered. Web work, price
# proposals, the Sandbox and Connector calls go to specialists the Lead builds, which keeps the
# Lead's context small; the Checking QS reads only, and never goes online.
LEAD_TOOLS = (
    "files_list",
    "files_read",
    "boq_preview",
    "boq_import",
    "ask_engineer",
    "prices_lookup",
    "note_lesson",
    "connector_tools",
    "understood",  # Plan 8: the "I understood this" card
    "show",  # decision 16.1: a view built from ONE's blocks (qsone/view.py)
)
CHECKER_TOOLS = ("files_list", "files_read", "sandbox_rerun")


def _registered(names: tuple[str, ...]) -> tuple[str, ...]:
    import qsone.tools  # noqa: F401 - registers every Plan 5 tool; it imports the engine

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
    from qsone.engine import team  # registers the team tools; team imports this module

    return AgentSpec(
        id="lead-qs",
        name=copy.ROLE_LEAD,
        role="lead",
        instructions=_instructions("lead_qs.txt"),
        tools=(*RECORDS_TOOLS, *team.TEAM_TOOLS, *_registered(LEAD_TOOLS), *OUTPUTS_TOOLS),
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
    from pydantic_ai.capabilities import ProcessHistory

    return Agent(
        model,
        name=spec.id,
        instructions=spec.instructions,
        toolsets=None if toolset is None else [toolset],
        output_type=output_type,
        capabilities=[ProcessHistory(trim_history)],
    )


# History --------------------------------------------------------------------------------------

_ID = re.compile(r'"(\w*id)"\s*:\s*"([^"]{1,80})"')
_VALUE = re.compile(r'"value"\s*:\s*"([^"]{1,40})"')


def _tokens(messages: list) -> int:
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    return len(ModelMessagesTypeAdapter.dump_json(messages)) // 4  # about 4 bytes a token


def _summary(tool_name: str, content) -> str:
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    ids = list(dict.fromkeys(f"{k}={v}" for k, v in _ID.findall(text)))[:20]
    values = list(dict.fromkeys(_VALUE.findall(text)))[:20]
    kept = "; ".join(
        part
        for part in (
            f"ids {', '.join(ids)}" if ids else "",
            f"values {', '.join(values)}" if values else "",
        )
        if part
    )
    return f"[earlier {tool_name} result, trimmed to save room{': ' + kept if kept else ''}]"


def trim_history(messages: list, *, limit_tokens: int = TRIM_TOKENS) -> list:
    """Under `limit_tokens`, the history as it is. Over it, the oldest successful tool results
    become short summaries that keep their ids and values, oldest first, until it fits. Errors
    and the latest message stay whole; nothing else changes."""
    from dataclasses import replace

    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    if _tokens(messages) <= limit_tokens:
        return messages
    out = list(messages)
    for i, message in enumerate(out[:-1]):
        if not isinstance(message, ModelRequest):
            continue
        parts = list(message.parts)
        for j, part in enumerate(parts):
            if (
                isinstance(part, ToolReturnPart)
                and part.outcome == "success"
                and not (isinstance(part.content, str) and part.content.startswith("[earlier "))
            ):
                parts[j] = replace(part, content=_summary(part.tool_name, part.content))
        out[i] = replace(message, parts=parts)
        if _tokens(out) <= limit_tokens:
            break
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
