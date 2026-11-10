"""The Lead's tools in groups, sent when a Brief needs them (as Claude Code sends its deferred
tools): every request carries every schema it is sent, and the Lead's 36 tools were 23,000 of
a request's 25,000 tokens (6 Nov real walk, Gemini 3.1 Flash Lite).

- Always sent: the tools that read files and the Source Ledger, add a source, record a number
  and ask the engineer, and `open_tools`, whose description names each group still closed.
- A group opens for the rest of the Brief when the Lead calls `open_tools` with it (or with one
  of its tools), or calls one of its tools: every tool stays callable, sent or not, so a call
  to one is checked and run as any other.
- The groups opened are read from the Brief's own messages, so Continue rebuilds them; the
  chat's earlier Briefs reach the Lead without their tool calls, so a new Brief starts closed.
- The tools sent keep one order, the always-sent ones first, then each group in the order it
  opened, so the start of every request stays the same for the provider's prompt cache.

`ToolGroups` is the model wrapper that sends only those; no other file filters tools."""

import json
from collections.abc import Sequence
from dataclasses import replace

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.wrapper import WrapperModel

from qsone import copy
from qsone.engine.tools import Tool, ToolContext, register

OPEN = "open_tools"

# A tool in no group is always sent.
GROUPS: dict[str, tuple[str, ...]] = {
    "numbers": (
        "calculate",
        "recalculate",
        "explain_number",
        "show",
        "correct_number",
        "define_unit",
        "add_item",
    ),
    "team": (
        "plan_brief",
        "build_specialist",
        "delegate",
        "send_message",
        "make_deliverable",
        "submit_for_check",
        "save_desk",
        "use_desk",
        "keep_member",
    ),
    "boq": ("boq_preview", "boq_import", "boq_price_from_sheet", "prices_lookup"),
    "documents": (
        "pack_propose",
        "compare_files",
        "deliverable_create",
        "deliverable_read",
        "deliverable_propose",
        "deliverable_comment",
        "client_file_read",
        "client_file_plan",
    ),
    "more": ("note_lesson", "connector_tools", "understood", "settings_set"),
}
_GROUP_OF = {tool: group for group, tools in GROUPS.items() for tool in tools}


def group_of(tool: str) -> str | None:
    return _GROUP_OF.get(tool)


def opened(messages: Sequence) -> list[str]:
    """The groups opened in `messages`, in the order they opened."""
    found: list[str] = []

    def add(group: str | None) -> None:
        if group is not None and group not in found:
            found.append(group)

    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not isinstance(part, ToolCallPart):
                continue
            if part.tool_name == OPEN:
                try:
                    names = part.args_as_dict().get("open", [])
                except ValueError:
                    names = []
                for name in names if isinstance(names, list) else []:
                    add(name if name in GROUPS else group_of(str(name)))
            else:
                add(group_of(part.tool_name))
    return found


def _description(closed: Sequence[str], present: set[str]) -> str:
    lines = [
        "Your other tools, in groups: a group you open comes with your next step. Open all the "
        "Brief needs at once, by group or tool name."
    ]
    for group in closed:
        names = [t for t in GROUPS[group] if t in present]
        if names:
            lines.append(f"- {group}: {', '.join(names)}")
    lines.append(f"Example: {json.dumps(_EXAMPLE)}")
    return "\n".join(lines)


def sent(tool_defs: Sequence, messages: Sequence) -> list:
    """The tool definitions to send with this request, in their one order (above)."""
    present = {t.name for t in tool_defs}
    if OPEN not in present:
        return list(tool_defs)
    open_now = opened(messages)
    closed = [g for g in GROUPS if g not in open_now]
    out = []
    for t in tool_defs:
        if group_of(t.name) is None:
            if t.name == OPEN:
                if not any(set(GROUPS[g]) & present for g in closed):
                    continue  # nothing left to open
                t = replace(t, description=_description(closed, present))
            out.append(t)
    for group in open_now:
        out += [t for name in GROUPS[group] for t in tool_defs if t.name == name]
    return out


class ToolGroups(WrapperModel):
    """Sends the Lead's always-sent tools and the groups its Brief opened (`sent`)."""

    def _params(self, messages, params):
        return replace(params, function_tools=sent(params.function_tools, messages))

    async def request(self, messages, model_settings, model_request_parameters):
        params = self._params(messages, model_request_parameters)
        return await self.wrapped.request(messages, model_settings, params)

    def request_stream(self, messages, model_settings, model_request_parameters, run_context=None):
        params = self._params(messages, model_request_parameters)
        return self.wrapped.request_stream(messages, model_settings, params, run_context)


# open_tools ----------------------------------------------------------------------------------


class OpenArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    open: list[str] = Field(min_length=1, max_length=len(GROUPS) + 20)


_EXAMPLE = {"open": ["numbers"]}


async def _open(ctx: ToolContext, args: OpenArgs) -> str:
    groups, unknown = [], []
    for name in args.open:
        group = name if name in GROUPS else group_of(name)
        if group is None:
            unknown.append(name)
        elif group not in groups:
            groups.append(group)
    said = [f"{g}: {', '.join(GROUPS[g])}" for g in groups]
    out = f"Open from your next step: {'; '.join(said)}." if said else "Nothing opened."
    if unknown:
        out += f" No group or tool named {', '.join(unknown)}; groups: {', '.join(GROUPS)}."
    return out


register(
    Tool(
        OPEN,
        _description(list(GROUPS), set(_GROUP_OF)),
        OpenArgs,
        "read",
        _open,
        lambda _: copy.tool_step(OPEN),
        lead_only=True,
        example=_EXAMPLE,
        roles=frozenset({"lead"}),
    )
)
