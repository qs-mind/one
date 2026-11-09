import json

from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    RetryFeedbackPart,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from qsone.engine import agents, team, tool_groups
from qsone.engine.tools import REGISTRY


def _refused(history: bytes, tool: str) -> str | None:
    """The last refusal a run's tool call got (its retry text), or None."""
    found = None
    for m in _load(history):
        if isinstance(m, ModelRequest):
            for p in m.parts:
                retried = isinstance(p, RetryPromptPart) or (
                    isinstance(p, ToolReturnPart) and p.outcome == "retried"
                )
                if retried and p.tool_name == tool:
                    found = p.content if isinstance(p.content, str) else json.dumps(p.content)
    return found


NOT_DONE = "not done:"  # a tool's result when the world refused it (qsone.tools.cite.not_done)


def outcomes(history: bytes | None) -> list[tuple[str, bool, str]]:
    """(tool, went through, its text) for each tool call answered in a run's history, oldest
    first: a retry, a failure and a "not done" result did not go through."""
    found = []
    for m in _load(history):
        if not isinstance(m, ModelRequest):
            continue
        for p in m.parts:
            if isinstance(p, ToolReturnPart):
                text = p.content if isinstance(p.content, str) else json.dumps(p.content)
                ok = p.outcome == "success" and not text.startswith(NOT_DONE)
                found.append((p.tool_name, ok, text))
            elif isinstance(p, RetryPromptPart) and p.tool_name:
                text = p.content if isinstance(p.content, str) else json.dumps(p.content)
                found.append((p.tool_name, False, text))
    return found


# Histories -----------------------------------------------------------------------------------


def _load(history: bytes | None) -> list:
    return [] if not history else list(ModelMessagesTypeAdapter.validate_json(history))


def _dump(messages: list) -> bytes:
    return ModelMessagesTypeAdapter.dump_json(messages)


def _calls(message) -> list[ToolCallPart]:
    return [p for p in message.parts if isinstance(p, ToolCallPart)]


def _answered(messages: list) -> set[str]:
    return {
        p.tool_call_id
        for m in messages
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart | RetryPromptPart)
    }


def _last_response(messages: list) -> int | None:
    return next(
        (i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], ModelResponse)),
        None,
    )


def _deferred(call: ToolCallPart) -> bool:
    tool = REGISTRY.get(call.tool_name)
    return tool is not None and tool.deferred


def cut_back(messages: list) -> list:
    """A history that ends in a response whose inline tool calls are not all answered, cut back
    to its last request: the crash came while those tools ran, so that request is redone."""
    i = _last_response(messages)
    if i is None:
        return messages
    answered = _answered(messages[i + 1 :])
    if any(c.tool_call_id not in answered and not _deferred(c) for c in _calls(messages[i])):
        return messages[:i]
    return messages


def pending_deferred(messages: list) -> list[ToolCallPart]:
    """The deferred calls of the last response that have no result in the history yet."""
    i = _last_response(messages)
    if i is None:
        return []
    answered = _answered(messages[i + 1 :])
    return [c for c in _calls(messages[i]) if _deferred(c) and c.tool_call_id not in answered]


def final_text(messages: list) -> str | None:
    """The answer, when the history ends in a response with text and no tool calls."""
    if not messages or not isinstance(messages[-1], ModelResponse) or _calls(messages[-1]):
        return None
    return "".join(p.content for p in messages[-1].parts if isinstance(p, TextPart))


def settled(messages: list) -> list:
    """An earlier Brief's history up to its last finished answer: a stopped Brief leaves calls
    with no answer, which no provider takes as history."""
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], ModelResponse) and not _calls(messages[i]):
            return messages[: i + 1]
    return []


STEPS_NOTE = "[ONE's note of that Brief's steps, with the ids they gave (data, not the engineer's):"


def heard(messages: list) -> list:
    """An earlier Brief of the chat as the next Brief's Lead hears it: the engineer's words, one
    line per tool step with the ids it gave (ONE's own note, made by code, so every Brief
    hears its earlier ones byte for byte the same, and the provider's cache holds), and the
    Lead's answer. The tool results themselves are left out: every request would carry them
    again; the answer names its sources and the Lead reads again what it needs. `messages` is
    `settled`; an answer sent back to be fixed is left out."""
    asked: list = []
    steps: list[str] = []
    calls = {c.tool_call_id: c for m in messages if isinstance(m, ModelResponse) for c in _calls(m)}
    for m in messages:
        if not isinstance(m, ModelRequest):
            continue
        for p in m.parts:
            if isinstance(p, UserPromptPart):
                asked.append(p)
            elif isinstance(p, ToolReturnPart) and p.tool_name != tool_groups.OPEN:
                ids = agents.ids_in(p.content)
                if p.outcome != "success":
                    ids = ["refused"]
                elif not ids and p.tool_call_id in calls:
                    ids = agents.ids_in(calls[p.tool_call_id].args_as_json_str())
                steps.append(f"- {p.tool_name}" + (f": {', '.join(ids)}" if ids else ""))
    said = lead_text(messages)
    if not asked or not said:
        return []
    if steps:
        asked.append(UserPromptPart("\n".join([STEPS_NOTE, *steps[:30]]) + "]"))
    return [ModelRequest(parts=asked), ModelResponse(parts=[TextPart(said)])]


def _sent_back(messages: list, i: int) -> bool:
    """Whether the answer at `i` went back to be fixed: the next request retries the output (a
    retry with no tool), as the truth checks do (`_Brief._truthful`)."""
    after = messages[i + 1] if i + 1 < len(messages) else None
    return isinstance(after, ModelRequest) and any(
        isinstance(p, RetryFeedbackPart) or (isinstance(p, RetryPromptPart) and p.tool_name is None)
        for p in after.parts
    )


def lead_text(messages: list) -> str:
    """Everything the Lead said, its answers' text, as one reply; an answer it was sent back to
    fix is left out, as the screen left it out live (`data-redo`)."""
    said = [
        "".join(p.content for p in m.parts if isinstance(p, TextPart))
        for i, m in enumerate(messages)
        if isinstance(m, ModelResponse) and not _sent_back(messages, i)
    ]
    return "\n\n".join(s for s in said if s)


def _tool_results(runs: list[dict]) -> list[str]:
    """What the tools gave in these runs, the numbers guard's sources (the team's own words do
    not count)."""
    return [
        text
        for run in runs
        if run["history"]
        for name, text in agents.tool_returns(run["history"])
        if name not in team.TEAM_TOOLS
    ]
