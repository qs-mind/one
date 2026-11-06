"""The Brief Runner: each engineer message is a Brief, run as a background task that no HTTP
request owns.

- **Durable steps.** Each agent run's Checkpoint is its own message history, saved in the
  project's encrypted file after every model response and every tool round. `delegate` and
  `submit_for_check` are PydanticAI deferred calls: the runner runs them (specialists in
  parallel, at most `max_agents` agents at once across all Briefs), stores each result as it
  finishes, and resumes the Lead with `deferred_tool_results`. Continue rebuilds every run from
  its Checkpoint: a history that ends in a response with inline tool calls not yet answered is
  cut back to its last request, so at most one model request is redone; a replayed write tool
  call never writes twice (`tools.call`). A fresh launch never continues anything by itself.
- **The Subscription Link.** A run on the engineer's Claude Code is a job with its own MCP token;
  its deferred tools run inside the MCP call. It keeps no history in One, so the runner keeps a
  mirror of it (its task, each tool call and result, its answer) as an ordinary history, for the
  numbers guard and for the Lead of the next Brief.
- **Stop, steer, failures.** Stop cancels the Brief's task, which reaches every agent of it
  (Claude Code is interrupted, then terminated, then killed). A message sent while it runs is
  enqueued into the running Lead. A provider that is down is tried once more after 5 s, then
  the role moves to a model of the same price or cheaper (a costlier one asks); no internet
  waits 5, 15, 30, 60 s, then every 60 s; a refused key fails plainly; a Spending Cap stops it.
- **The end.** The numbers guard marks typed numbers with no source in the Lead's reply, and
  every unchecked Deliverable with numbers goes to the Checking QS before the Brief is done.

Its events reach the screen through `events` (replayed from the start, then live) and
`stream.ui_stream`; the team and its state reach Plan 7's canvas through `activity`.
Never logs Brief text, messages, cards or tool arguments: only ids and states."""

import asyncio
import json
import logging
import re
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP
from pathlib import Path
from typing import Any
from uuid import uuid4

import anthropic
import openai
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, ModelRetry, ToolFailed
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelHTTPError,
    ModelRateLimitError,
    ModelRequestTimeout,
    ModelServerError,
    ModelUnavailableError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    RetryFeedbackPart,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from qsone import activity, copy, usage, view
from qsone.deliverables import tools as outputs
from qsone.engine import (
    agents,
    cards,
    checker,
    desks,
    focus,
    general,
    numbers_guard,
    oneshot,
    roles,
    selection,
    team,
    tool_groups,
    tools,
    truth,
)
from qsone.engine import connectors as connectors_mod
from qsone.engine.costs import CallRefused, CapReached, CostedModel, Spending
from qsone.engine.data_text import new_fence
from qsone.engine.mcp_server import McpGate, RunScope
from qsone.engine.store import UNFINISHED, CostBook, Store
from qsone.engine.team import TeamSetup
from qsone.engine.tools import DENIED, REGISTRY, Denied, ToolContext
from qsone.engine.types import (
    AgentSpec,
    Asked,
    BriefState,
    Card,
    CheckPacket,
    Data,
    Effort,
    Event,
    ModelCard,
    ModelChoice,
    Progress,
    Review,
    Reviewed,
    Role,
    Settled,
    Status,
    TeamMessage,
    Text,
    TextDelta,
    Unsourced,
    brief_language,
    choice_of,
    reply_line,
)
from qsone.engine.worklog import WorkLog
from qsone.journey import engineer, understand
from qsone.projects import Projects
from qsone.records.project import Records, RecordsError

log = logging.getLogger("qsone.engine.runner")

GENERAL = "general"  # the General chat's id; it lives in the Engineer Records file
WORK = "claude-work"  # <data>/claude-work/<run id>/: one Claude Code run's folder
TOOL_RETRIES = 3  # how often a model may fix one tool call, or its final answer
STEP_LIMIT = 50  # model requests in one pass of the Lead; then it reports what it has
REPORT_LIMIT = 3  # model requests of that report, or of a report at a Spending Cap
# ONE's own refusals, given up on by the model: never a provider's error (6 Nov 2026)
_TOOL_GAVE_UP = re.compile(r"^Tool '([A-Za-z0-9_]+)' exceeded max retries count of (\d+)")
_REPLY_GAVE_UP = re.compile(r"^Exceeded maximum (?:output )?retries")
BUSY_WAIT = 5  # seconds before the one more try at a busy provider
OFFLINE_WAITS = (5, 15, 30, 60)  # then every 60 s while the app runs
REVIEW_AS_JSON = (  # the model reads it: a check on Claude Code answers in text
    'Answer with one JSON object only: {"code": "A" | "B" | "C", "comments": '
    '[{"about": "...", "text": "..."}], "checked": ["..."]}.'
)
_ROLE_NAMES: dict[str, Text] = {
    "lead": copy.ROLE_LEAD,
    "checker": copy.ROLE_CHECKER,
    "specialist": copy.ROLE_SPECIALIST,
    "quick": copy.ROLE_QUICK,
}
_DEFERRED = object()  # the Lead's pass ended with deferred calls to run
# Every specialist's principles from ONE, beside the Lead's instructions for it: the tender day's
# weak model priced walls at a block's supply price «شامل العمالة» and cited worked-out numbers
# as read from a quote. The record tools refuse both; these say why before they do.
SPECIALIST_RULES = (
    "ONE's principles for every specialist:\n"
    "- A number read from a file is recorded at the place that has it, as written there. A "
    "number you work out (a total, an average, a price with waste or a margin) goes through "
    "calculate with its inputs and formula, never as read from a file.\n"
    "- A rate says what it includes: supply, or supply and installation. A supply-only quote "
    "never covers labour; an installed item's rate adds labour from its own source, with "
    "calculate. A rate is per the item's own unit.\n"
    "- A value you do not have is missing: say so; never leave a blank for it."
)
_RECORD_ID = re.compile(r"\b[0-9a-f]{32}\b")  # an item, file or number id in a tool's words
# The reply says ONE could not search the web: the screen adds the way to set it up.
_NO_SEARCH_SAID = re.compile(
    r"الإنترنت|الانترنت|\bالنت\b|الويب|أونلاين|اونلاين|\b(?:web|internet|online)\b", re.I
)


def _descriptions(rec: Records) -> list[str]:
    """The project's item descriptions, as its records have them."""
    with rec.read() as c:
        rows = c.execute(
            "SELECT json_extract(fields, '$.description') FROM items"
            " WHERE json_extract(fields, '$.description') IS NOT NULL"
        ).fetchall()
    return [str(d) for (d,) in rows]


def _no_search_notice(brief_id: str) -> Data:
    """The notice the web tools give when no search is set up, with its fix (audit B8)."""
    data = {"text": copy.WEB_NO_SEARCH, "fix": "search"}
    return Data(brief_id, "notice", f"{brief_id}-no-search", data)


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


def utc_now() -> datetime:
    return datetime.now(UTC)


def reply_id(brief_id: str) -> str:
    """The stored id of a Brief's reply: the stream's `start.messageId`."""
    return f"{brief_id}-reply"


def question_id(brief_id: str) -> str:
    return f"{brief_id}-question"


class NoAI(Exception):
    """No model to run on; `text` says why in plain words."""

    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


class BriefBusy(Exception):
    def __init__(self, brief_id: str) -> None:
        super().__init__(brief_id)
        self.brief_id = brief_id


class _Fail(Exception):
    """Ends the Brief as failed, with these plain words."""

    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


class _Busy(Exception):
    """The Subscription Link reached its limit: like a busy provider."""


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


def _error_kind(error: BaseException) -> str | None:
    """auth, offline, busy or other for a provider's error; None when it is not one."""
    if isinstance(error, _Busy):
        return "busy"
    status = getattr(error, "status_code", None)
    if isinstance(
        error,
        ModelAuthenticationError | anthropic.AuthenticationError | openai.AuthenticationError,
    ) or (isinstance(error, ModelHTTPError) and status in (401, 403)):
        return "auth"
    if isinstance(
        error,
        ModelConnectionError
        | ModelRequestTimeout
        | ConnectionError
        | anthropic.APIConnectionError
        | openai.APIConnectionError,
    ):
        return "offline"
    if isinstance(
        error,
        ModelRateLimitError
        | ModelUnavailableError
        | ModelServerError
        | anthropic.RateLimitError
        | anthropic.InternalServerError
        | openai.RateLimitError
        | openai.InternalServerError,
    ) or (isinstance(status, int) and (status == 429 or status >= 500)):
        return "busy"
    # an empty or malformed reply, or retries used up, is the model's doing, not ONE's
    if isinstance(
        error, ModelAPIError | UnexpectedModelBehavior | anthropic.APIError | openai.APIError
    ):
        return "other"
    return None


def _result_value(stored: str):
    found = json.loads(stored)
    if "ok" in found:
        return found["ok"]
    if "retry" in found:
        return ModelRetry(found["retry"])
    return ToolFailed(found["failed"])


def _with_reports(messages: list[dict], rec) -> list[dict]:
    """`messages` with each files report (records/report.py) as one message from ONE, after the
    Briefs that began before it."""
    from qsone.records import report

    kept = report.kept(rec)
    if not kept:
        return messages
    with rec.read() as c:
        began = dict(c.execute("SELECT id, created_at FROM briefs").fetchall())
    out, reports = [], iter(kept)
    nxt = next(reports, None)
    for m in messages:
        if m["role"] == "user":
            at = began.get(m["id"].removesuffix("-question"), "")
            while nxt is not None and nxt["at"] < at:
                out.append(_report_message(nxt))
                nxt = next(reports, None)
        out.append(m)
    while nxt is not None:
        out.append(_report_message(nxt))
        nxt = next(reports, None)
    return out


def _report_message(found: dict) -> dict:
    part = {"type": "data-files_read", "id": found["id"], "data": {"lines": found["lines"]}}
    return {"id": f"files-{found['id']}", "role": "assistant", "parts": [part]}


# The Brief task ------------------------------------------------------------------------------


@dataclass
class _Place:
    store: Store
    rec: Records | None  # the open project; None for the General chat
    project_id: str | None
    project_name: str | None

    @property
    def channel(self) -> str:
        return self.project_id or GENERAL


@dataclass
class _AgentState:
    run_id: str
    spec: AgentSpec
    model: str
    state: str = "thinking"
    line: Text | None = None
    focus: dict | None = None  # Plan 7's Focus: the frame it works on, from its tool calls
    at: str = field(default_factory=lambda: utc_now().isoformat())


class _Brief:
    """One Brief while this core runs it: its task, its event log, and the `TeamHost` its
    tools use."""

    def __init__(
        self,
        engine: "Engine",
        place: _Place,
        brief: dict,
        *,
        instruction: str | None = None,
        output_type: type | None = None,
        sheet: tuple[list[ModelCard], list] | None = None,
        lead: ModelChoice | None = None,
    ) -> None:
        self.engine = engine
        self.place = place
        self.store = place.store
        self.brief_id: str = brief["id"]
        self.chat_id: str = brief["chat_id"]
        self.text: str = brief["text"]
        self.lang = brief_language(self.text)  # the engineer's, for the Brief's Progress words
        self.selection: list[dict] | None = brief["selection"]  # on the canvas (Plan 7)
        # The Lead QS's model and effort, as picked in the message box; the effort is kept with
        # the Brief, so a continued Brief thinks as hard as it began.
        self.lead_choice = lead
        self.effort: Effort | None = brief["effort"]
        self.state: BriefState = brief["status"]
        self.step: Text | None = brief["step"]
        self.instruction = instruction
        self.output_type = output_type
        self.output: Any = None
        self.log: list[Event] = []
        self.finished = False
        self.task: asyncio.Task | None = None
        self.cancel_mode = "stop"  # "stop", "pause" (keep the Checkpoint as unfinished), "crash"
        self.waiting: dict[str, tuple[Card, asyncio.Future]] = {}
        self.steering: list[str] = []
        self.lead_run = None  # the Lead's PydanticAI `AgentRun` while one runs
        self.claude_lead: tuple[Any, str] | None = None  # (connector, run id) of a Claude Code Lead
        self.agents: dict[str, _AgentState] = {}
        self.tokens: set[str] = set()
        self.setup: TeamSetup | None = None
        self.saved_roles: set[Role] = set()  # the roles the engineer chose in Settings
        self.sheet: list[ModelCard] = []
        self.found: dict[str, Any] = {}
        self._given_sheet = sheet
        self.lead_run_id: str | None = None
        self.lead_ctx: ToolContext | None = None
        self.truth_retried = False  # the reply went back once to be fixed (engine.truth)
        self.step_limited = False  # the Lead reached STEP_LIMIT and reported what it had
        self.budget_approved = False  # the engineer said yes to the Brief Budget of its plan
        self.said = 0  # the reply's length so far, in the screen's units (UTF-16)
        self.answer_from = 0  # where the Lead's latest response began in it
        self.redo_cleared = False  # a reply sent back left the screen with no words
        self.refusals: dict[str, Text] = {}  # each tool's last refusal, in the engineer's words
        self._news = asyncio.Event()
        saved = brief.get("worklog")
        self.worklog = (
            WorkLog.load(saved, stopped_at=brief["updated_at"])
            if saved
            else WorkLog(started=self._now())
        )

    # Events --------------------------------------------------------------------------------

    def _notify(self) -> None:
        self._news.set()
        self._news = asyncio.Event()

    def _now(self) -> str:
        return self.engine.clock().isoformat(timespec="milliseconds")

    def emit(self, event: Event) -> None:
        if isinstance(event, Progress) and event.lang is None:
            event = replace(event, lang=self.lang)
        if isinstance(event, Progress | Settled) and event.at is None:
            event = replace(event, at=self._now())
        if isinstance(event, TextDelta):
            self.said += len(event.text.encode("utf-16-le")) // 2
        self.log.append(event)
        if isinstance(event, Progress):
            self._agent(event.run_id, state="working", line=event.text, focus=event.focus)
            self.step = event.text
            if self.state == "running" and self.cancel_mode != "crash":
                self.store.set_status(self.brief_id, "running", event.text)
            self.worklog.add(event, event.at)
            self._worklog_changed()
        self._notify()

    def _worklog_changed(self) -> None:
        """Saves the work log and sends it whole (`data-worklog`, id: the Brief)."""
        if self.cancel_mode != "crash":
            self.store.set_worklog(self.brief_id, self.worklog.saved())
        self.log.append(Data(self.brief_id, "worklog", self.brief_id, self.worklog.as_json()))
        self._notify()

    def _tools_done(self, run_id: str) -> None:
        """The run's tools have returned: its tool steps end now."""
        if self.worklog.tools_done(run_id, self._now()):
            self._worklog_changed()

    async def events(self) -> AsyncIterator[Event]:
        i = 0
        while True:
            news = self._news
            while i < len(self.log):
                yield self.log[i]
                i += 1
            if self.finished:
                return
            await news.wait()

    def set_state(self, state: BriefState, step: Text | None = None) -> None:
        self.state = state
        if step is not None:
            self.step = step
        if self.cancel_mode != "crash":
            self.store.set_status(self.brief_id, state, self.step)
        log.info("brief %s %s", self.brief_id, state)
        if state in ("done", "failed", "stopped"):
            self.worklog.end(self._now())
            self._worklog_changed()
        self.emit(Status(self.brief_id, state, self.step))

    # Plan 7's view of the team ---------------------------------------------------------------

    def _agent(
        self,
        run_id: str,
        *,
        spec: AgentSpec | None = None,
        model: str | None = None,
        state: str | None = None,
        line: Text | None = None,
        focus: dict | None = None,
    ) -> None:
        """`focus` None keeps the frame the agent was on."""
        found = self.agents.get(run_id)
        if found is None:
            if spec is None:
                return
            found = self.agents[run_id] = _AgentState(run_id, spec, model or "")
            if spec.role == "specialist" and spec.desk is None:
                self.engine._publish(self.place.channel, {"type": "desk", "desk": self.desk()})
        if model is not None:
            found.model = model
        if state is not None:
            found.state = state
        if line is not None:
            found.line = line
        if focus is not None:
            found.focus = focus
        found.at = utc_now().isoformat()
        self.engine._publish(self.place.channel, {"type": "agent", "agent": self.agent_info(found)})

    def agent_info(self, a: _AgentState) -> dict:
        desk = None
        if a.spec.role == "specialist":
            desk = a.spec.desk or self.brief_id
        return {
            "id": a.run_id,
            "kind": a.spec.role,  # lead, checker, specialist or quick: where the canvas puts it
            "role": a.spec.name,
            "desk_id": desk,
            "model": a.model,
            # the model's provider on this Brief's sheet, for its company's logo (None: not on it)
            "provider": next((c.provider for c in self.sheet if c.choice.model == a.model), None),
            # its name as the sheet gives it («Gemini 3.1 Flash Lite»): never the raw id
            "model_name": next((c.name for c in self.sheet if c.choice.model == a.model), None),
            "state": a.state,
            "line": a.line,
            "lang": self.lang,  # the line's language: the Brief's
            "brief_id": self.brief_id,
            "focus": a.focus,
            "at": a.at,
        }

    def desk(self) -> dict:
        return {"id": self.brief_id, "name": copy.DESK_TEMPORARY, "stage": "temporary"}

    def _waiting_count(self) -> None:
        count = sum(len(b.waiting) for b in self.engine._in(self.place.channel))
        self.engine._publish(self.place.channel, {"type": "waiting", "count": count})

    # TeamHost --------------------------------------------------------------------------------

    async def ask(self, card: Card) -> str:
        if card.id not in {c.id for c in self.store.pending(self.brief_id)}:
            self.store.add_approval(self.brief_id, card)  # stored before it is shown
        future = asyncio.get_running_loop().create_future()
        self.waiting[card.id] = (card, future)
        before = self.step
        state: BriefState = "paused_cap" if card.kind == "cap" else "waiting_engineer"
        self.set_state(state, copy.fill(copy.STEP_WAITING, title=card.title))
        self.emit(Asked(self.brief_id, card))
        if self.lead_run_id is not None:
            self._agent(self.lead_run_id, state="waiting")
        self._waiting_count()
        try:
            return await future
        finally:
            self.waiting.pop(card.id, None)
            self._waiting_count()
            if not self.waiting and self.state in ("waiting_engineer", "paused_cap"):
                self.set_state("running", before)
                if self.lead_run_id is not None:
                    self._agent(self.lead_run_id, state="working")

    def answer(self, card_id: str, choice: str) -> None:
        """`choice` is the settled value: an option, or a payload card's `answer_value`."""
        card, future = self.waiting[card_id]
        if choice_of(card, choice) not in card.options:
            raise ValueError(choice)
        try:
            self.store.settle(card_id, choice)
        except LookupError:
            pass  # stored by the tool that asked
        self.emit(Settled(self.brief_id, card_id, choice))
        if not future.done():
            future.set_result(choice)

    def post(self, message: TeamMessage) -> None:
        self.emit(message)  # send_message stored it already

    def note_refusal(self, tool: str, text: Text | None) -> None:
        """A tool call refused, with its words when ONE has them in both languages: the flag
        beside a reply that says it was done gives the engineer this reason (`_did`)."""
        if text is not None:
            self.refusals[tool] = text
        else:
            self.refusals.pop(tool, None)

    async def run_specialist(self, spec: AgentSpec, task: str, kit: dict) -> str:
        run_id = team.specialist_run(self.store, self.brief_id, spec.id)
        prompt = task
        if any(kit.get(k) for k in ("file_ids", "item_ids", "notes")):
            prompt = f"{task}\n\nKit: {json.dumps(kit, ensure_ascii=False)}"
        async with self.engine._agent_slots:
            self.store.set_run(run_id, status="running")
            choice = self.store.run(run_id)["choice"]
            self._agent(run_id, spec=spec, model=choice.model, state="thinking")
            try:
                out = await self._attempts(
                    run_id, spec, lambda c: self._specialist_pass(run_id, spec, prompt, c)
                )
            except _Fail as failed:  # the Lead hears it and decides; the Brief goes on
                self.store.set_run(run_id, status="failed")
                self._agent(run_id, state="failed", line=failed.text)
                return f"The specialist could not finish: {failed.text['en']}"
            self.store.set_run(run_id, status="done")
            self._agent(run_id, state="done")
            return out

    async def run_checker(self, packet: CheckPacket, maker: ModelChoice) -> Review:
        assert self.setup is not None
        spec = agents.checker_spec()
        choice = self.setup.roles.get("checker") or maker
        if choice == maker and "checker" not in self.saved_roles:
            # Only a default Checking QS moves off the maker's model, and never to a costlier
            # one: the engineer's own choice always wins (a Same-provider check, still blind).
            others = [
                c for c in roles.same_or_cheaper(self.sheet, maker, {maker}) if self._model(c)
            ]
            choice = others[0] if others else maker
        run_id = self.store.new_run(self.brief_id, spec, choice, self.lead_run_id)
        async with self.engine._agent_slots:
            self._agent(run_id, spec=spec, model=choice.model, state="working")
            self.emit(Progress(self.brief_id, run_id, spec.name, copy.STEP_CHECKING))
            try:
                review = await self._attempts(
                    run_id,
                    spec,
                    lambda c: self._check_pass(run_id, spec, packet, maker, c),
                    avoid=frozenset({maker}),
                )
            finally:
                self.store.set_run(run_id, status="done")
                self._agent(run_id, state="done")
        return review

    # Models ----------------------------------------------------------------------------------

    def _model(self, choice: ModelChoice) -> bool:
        connector = self.found.get(choice.connector)
        return connector is not None and connector.kind == "model"

    def card(self, choice: ModelChoice) -> ModelCard:
        for c in self.sheet:
            if c.choice == choice:
                return c
        connector = self.found.get(choice.connector)
        return ModelCard(
            choice=choice,
            name=choice.model,
            provider=getattr(connector, "provider", choice.connector),
            images=False,
            tools=True,
            context=None,
            price_in=None,
            price_out=None,
            price_source=None,
            subscription=getattr(connector, "kind", "") == "agent",
        )

    def _provider(self, choice: ModelChoice) -> str:
        connector = self.found.get(choice.connector)
        return getattr(connector, "name", choice.connector)

    def lead_effort(self, choice: ModelChoice) -> Effort | None:
        """The Brief's effort, when the Lead's model `choice` accepts it (a model moved to after
        a failure may not); None sends none, and the provider uses its own."""
        return self.effort if self.effort in self.card(choice).efforts else None

    def _costed(self, run_id: str, role: Role, choice: ModelChoice, effort: Effort | None = None):
        connector = self.found.get(choice.connector)
        if connector is None:
            raise _Fail(copy.NO_AI)
        try:
            model = connector.model(choice.model)
        except connectors_mod.NoKey:
            raise _Fail(copy.NO_AI) from None
        return CostedModel(
            model,
            spending=self.engine.spending,
            host=self,
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            role=role,
            card=self.card(choice),
            effort=effort,
        )

    def models(self, run_id: str) -> oneshot.Models:
        """This Brief's models, for the one-shot calls of a tool in run `run_id`."""
        return oneshot.Models(
            sheet=tuple(self.sheet),
            roles=dict(self.setup.roles) if self.setup is not None else {},
            connectors=dict(self.found),
            spending=self.engine.spending,
            host=self,
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            work=self.engine.data_dir / WORK,
        )

    def _ctx(self, run_id: str, spec: AgentSpec) -> ToolContext:
        meaning = self.engine.meaning
        services = self.engine.services
        if services is not None:
            services = oneshot.for_run(services, self.models(run_id))
        return ToolContext(
            brief_id=self.brief_id,
            run_id=run_id,
            agent=spec,
            rec=self.place.rec,
            store=self.store,
            host=self,
            fence=new_fence(),
            embedder=meaning.embedder() if meaning is not None else None,
            services=services,
            projects=self.engine.projects,
        )

    def _toolset(self, spec: AgentSpec, ctx: ToolContext):
        found = tools.toolset(spec.tools, ctx)
        found.max_retries = TOOL_RETRIES
        return found

    def _save(self, run_id: str, messages: list) -> None:
        if self.cancel_mode != "crash":
            self.store.save_history(run_id, _dump(messages))

    def _say_tools(self, run_id: str, spec: AgentSpec, response: ModelResponse) -> None:
        for c in _calls(response):
            if c.tool_name == tool_groups.OPEN:
                continue  # ONE's own step, not work the engineer sees
            tool = REGISTRY.get(c.tool_name)
            words = copy.tool_step(c.tool_name)
            if tool is not None:
                try:
                    words = tool.activity(tool.args.model_validate(c.args_as_dict()))
                except Exception:  # noqa: BLE001 - its own words are only for the Progress Line
                    pass
            on = self._focus(c.tool_name, c.args_as_dict())
            words = self._plain(words)
            self.emit(Progress(self.brief_id, run_id, spec.name, words, on, tool=True))

    def _plain(self, words: Text) -> Text:
        """The work log's words with each record id the model gave named as the engineer knows
        it: an item by its code, a file by its name (never «البند 707d81e9…»)."""
        rec = self.place.rec
        ids = {i for text in words.values() for i in _RECORD_ID.findall(text)}
        if rec is None or not ids:
            return words
        names: dict[str, str] = {}
        try:
            with rec.read() as c:
                for i in ids:
                    row = (
                        c.execute(
                            "SELECT coalesce(code, '') FROM items WHERE id = ?", (i,)
                        ).fetchone()
                        or c.execute("SELECT name FROM files WHERE id = ?", (i,)).fetchone()
                        or c.execute(
                            "SELECT coalesce(i.code, '') FROM numbers n JOIN items i"
                            " ON i.id = n.item_id WHERE n.id = ?",
                            (i,),
                        ).fetchone()
                    )
                    if row and row[0]:
                        names[i] = row[0]
        except RecordsError:
            return words
        return {
            lang: _RECORD_ID.sub(lambda m: names.get(m[0], m[0]), text)
            for lang, text in words.items()
        }

    def _focus(self, tool: str, args: dict) -> dict | None:
        try:
            return focus.of(tool, args, self.place.rec)
        except RecordsError:  # only for the canvas: the tool call itself says what is wrong
            return None

    # Failures --------------------------------------------------------------------------------

    async def _attempts(
        self,
        run_id: str,
        spec: AgentSpec,
        once: Callable[[ModelChoice], Awaitable[Any]],
        *,
        avoid: frozenset[ModelChoice] = frozenset(),
    ):
        """Runs `once` on the run's model, from its Checkpoint each time, through the failures
        that have a plan: busy (once more, then another model), offline (wait), refused key."""
        retried = False
        waits = iter(OFFLINE_WAITS)
        while True:
            choice = self.store.run(run_id)["choice"]
            try:
                return await once(choice)
            except (CapReached, CallRefused, _Fail, asyncio.CancelledError):
                raise
            except Exception as error:  # noqa: BLE001 - sorted below; anything else is re-raised
                gave_up = self._gave_up(run_id, error)
                if gave_up is not None:
                    raise _Fail(gave_up) from None
                kind = _error_kind(error)
                if kind is None:
                    raise
                provider = self._provider(choice)
                log.warning("run %s on %s: %s %s", run_id, choice.connector, kind, error)
                if kind == "auth":
                    raise _Fail(connectors_mod.key_refused(provider)) from None
                if kind == "other":  # the provider's reason when ONE knows it (audit B7)
                    said = connectors_mod.provider_reason(error, provider, choice.model)
                    if getattr(error, "status_code", None) == 404:
                        connectors_mod.note_refused(choice)  # no longer listed (audit C4)
                    raise _Fail(said or copy.fill(copy.AI_FAILED, provider=provider)) from None
                if kind == "offline":
                    before = self.step
                    self.set_state("waiting_connection", copy.WAITING_INTERNET)
                    await self.engine.sleep(next(waits, OFFLINE_WAITS[-1]))
                    self.set_state("running", before)
                    continue
                if not retried:
                    retried = True
                    await self.engine.sleep(BUSY_WAIT)
                    continue
                retried = False
                await self._move(run_id, spec, choice, avoid, provider)

    def _gave_up(self, run_id: str, error: BaseException) -> Text | None:
        """The plain words for a run that stopped on ONE's own refusals (a tool call refused
        until the model gave up, or an answer sent back too often); None for any other error.
        The provider is never named for these: they are ONE's."""
        if not isinstance(error, UnexpectedModelBehavior):
            return None
        tool = _TOOL_GAVE_UP.match(error.message)
        if tool is not None:
            name, n = tool[1], tool[2]
            said = _refused(self.store.run(run_id)["history"], name) or ""
            why = self._refusal(name, said)
            return copy.fill(copy.TOOL_GAVE_UP, n=str(int(n) + 1), why=why)
        if _REPLY_GAVE_UP.match(error.message):
            return copy.REPLY_GAVE_UP
        return None

    async def _move(
        self,
        run_id: str,
        spec: AgentSpec,
        failed: ModelChoice,
        avoid: frozenset[ModelChoice],
        provider: str,
    ) -> None:
        """The run moves to the closest model of the same price or cheaper; a costlier one only
        after the engineer's yes. Raises `_Fail` when there is none, or on "no"."""
        skip = set(avoid) | {failed}
        old = self.card(failed).name
        cheaper = [c for c in roles.same_or_cheaper(self.sheet, failed, skip) if self._model(c)]
        if cheaper:
            new = cheaper[0]
            self.store.set_run(run_id, choice=new)
            self._agent(run_id, model=new.model)
            moved = copy.fill(copy.FALLBACK_MOVED, old=old, role=spec.name, new=self.card(new).name)
            self.emit(Progress(self.brief_id, run_id, spec.name, moved))
            return
        pricier = [c for c in roles.costlier(self.sheet, failed, skip) if self._model(c)]
        if pricier:
            new = pricier[0]
            card = self.card(new)
            detail = copy.fill(
                copy.FALLBACK_COSTLIER,
                old=old,
                new=card.name,
                price_in=format(card.price_in, "f") if card.price_in is not None else "?",
                price_out=format(card.price_out, "f") if card.price_out is not None else "?",
            )
            answer = await self.ask(Card(uuid4().hex, "fallback", spec.name, detail, ("yes", "no")))
            if answer == "yes":
                self.store.set_run(run_id, choice=new)
                self._agent(run_id, model=new.model)
                return
        raise _Fail(copy.fill(copy.AI_FAILED, provider=provider))

    # The Lead --------------------------------------------------------------------------------

    def _earlier(self) -> list:
        found = []
        for history in self.store.lead_histories(self.chat_id, self.brief_id):
            found += heard(settled(_load(history)))
        return found

    def _instructions(self, choice: ModelChoice) -> str:
        # a small model repeated "you run on …" in every reply (audit R15): only when asked
        said = (
            f"The AI model you run on is {choice.model}. Say it only if the engineer asks which "
            "model answers; never mention it otherwise."
        )
        found = (
            said,
            truth.today_line(self.engine.clock()),  # dates come from the core, in Cairo time
            reply_line(self.text),
            self._search_line(),
            self.instruction,
            selection.line(self.selection),
        )
        return "\n\n".join(part for part in found if part)

    def _search_line(self) -> str | None:
        """With no web search at all (a Standard Link, no search key), the Lead is told so
        (audit B8): it said nothing and gave remembered prices as today's."""
        from qsone.tools import web as web_tools

        services = self.engine.services
        if services is not None and self.lead_run_id is not None:
            services = oneshot.for_run(services, self.models(self.lead_run_id))
        if web_tools.searchable(services):
            return None
        if self.place.rec is not None:  # a project's Lead has no web_search: ONE adds the way
            return (
                "No web search is set up in ONE. When the engineer asks for something from the "
                "web or today's price, say in one line that ONE could not search the web (ONE "
                "shows them how to set it up), and give no remembered price as today's."
            )
        return (
            "No web search is set up in ONE. When the engineer asks for something from the web "
            "or today's price, call web_search once (ONE shows them how to set search up), say "
            "in one line that you could not search, and give no remembered price as today's."
        )

    async def _lead(self, *, report: bool = False) -> Any:
        assert self.lead_run_id is not None
        spec = self.lead_ctx.agent
        while True:
            if not report:
                own = cut_back(_load(self.store.run(self.lead_run_id)["history"]))
                pending = pending_deferred(own)
                if pending:
                    await self._run_deferred(self.lead_run_id, pending)
            try:
                out = await self._attempts(
                    self.lead_run_id, spec, lambda c: self._lead_pass(c, report=report)
                )
            except UsageLimitExceeded:
                if report:  # a report that keeps calling tools ends with what was said
                    return None
                return await self._step_limit()
            if out is not _DEFERRED:
                return out
            if report:
                return None

    async def _step_limit(self) -> Any:
        """The Lead reached ONE's step limit for one request: the engineer hears why, and the
        Lead says, without another tool, what it got so far (the top 5 of SGH took 50 steps of
        one item each and ended "problem inside ONE", 6 Nov 2026)."""
        log.info("brief %s at the step limit", self.brief_id)
        notice = copy.fill(copy.STEP_LIMIT_REACHED, n=str(STEP_LIMIT))
        self.emit(Data(self.brief_id, "notice", f"{self.brief_id}-step-limit", {"text": notice}))
        self.worklog.truth = (self.worklog.truth or {}) | {"step_limit": notice}
        self.step_limited = True
        try:
            out = await self._attempts(
                self.lead_run_id,
                self.lead_ctx.agent,
                lambda c: self._lead_pass(c, report=True, prompt=copy.STEP_LIMIT_NOW),
            )
        except UsageLimitExceeded:
            out = None
        return out if isinstance(out, str) and out.strip() else ""

    async def _run_deferred(self, run_id: str, calls: list[ToolCallPart]) -> None:
        """Runs the deferred calls that have no stored result, at the same time, storing each
        result as it finishes. The first failure that ends the Brief stops the others."""
        done = self.store.results(run_id)
        todo = [c for c in calls if c.tool_call_id not in done]
        if not todo:
            return
        self._agent(run_id, state="waiting")

        async def one(c: ToolCallPart) -> None:
            try:
                found = {"ok": await tools.call(c.tool_name, c.args_as_dict(), self.lead_ctx)}
            except ModelRetry as e:
                found = {"retry": e.message}
            except Denied:
                found = {"failed": DENIED.format(tool=c.tool_name)}
            if self.cancel_mode != "crash":
                self.store.save_result(
                    run_id, c.tool_call_id, json.dumps(found, ensure_ascii=False)
                )

        tasks = [asyncio.create_task(one(c)) for c in todo]
        try:
            for finished in asyncio.as_completed(tasks):
                await finished
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._agent(run_id, state="working")

    async def _lead_pass(
        self, choice: ModelChoice, *, report: bool = False, prompt: str | None = None
    ) -> Any:
        run_id = self.lead_run_id
        assert run_id is not None and self.lead_ctx is not None
        spec = self.lead_ctx.agent
        if not self._model(choice):
            return await self._lead_job(run_id, spec, choice)
        own = cut_back(_load(self.store.run(run_id)["history"]))
        done = final_text(own)
        if done is not None and not report and self.output_type is None:
            return done
        results = None
        pending = pending_deferred(own)
        if pending:
            stored = self.store.results(run_id)
            calls = {}
            for c in pending:
                if c.tool_call_id in stored:
                    calls[c.tool_call_id] = _result_value(stored[c.tool_call_id])
                else:  # only when reporting at a cap: the work was not done
                    calls[c.tool_call_id] = ToolFailed("Stopped by the Spending Cap.")
            results = DeferredToolResults(calls=calls)
        prompt = (prompt or copy.REPORT_NOW) if report else (None if own else self.text)
        earlier = self._earlier()
        effort = self.lead_effort(choice)
        # the Lead is sent the tool groups its Brief opened (tool_groups)
        model = tool_groups.ToolGroups(self._costed(run_id, "lead", choice, effort))
        agent = agents.build_agent(
            spec,
            model,
            self._toolset(spec, self.lead_ctx),
            output_type=[self.output_type or str, DeferredToolRequests],
        )
        if not report and self.output_type is None:
            agent.output_validator(self._truthful)
        said = bool(lead_text(own))
        self._agent(run_id, state="thinking", model=choice.model)
        async with agent.iter(
            prompt,
            message_history=(earlier + own) or None,
            deferred_tool_results=results,
            instructions=self._instructions(choice),
            retries=TOOL_RETRIES,
            model_settings=None if effort is None else ModelSettings(thinking=effort),
            usage_limits=UsageLimits(request_limit=REPORT_LIMIT if report else STEP_LIMIT),
        ) as run:
            self.lead_run = run
            try:
                while self.steering:
                    run.enqueue(self.steering.pop(0))
                async for node in run:
                    if not Agent.is_call_tools_node(node):
                        self._tools_done(run_id)
                    if Agent.is_model_request_node(node):
                        self._agent(run_id, state="thinking")
                        self.answer_from = self.said  # where this response's words begin
                        if self.redo_cleared:  # the screen dropped every word said so far
                            said, self.redo_cleared = False, False
                        async with node.stream(run.ctx) as events:
                            first = True
                            async for ev in events:
                                text = None
                                if isinstance(ev, PartStartEvent) and isinstance(ev.part, TextPart):
                                    text = ev.part.content
                                    if said and first:
                                        self.emit(TextDelta(self.brief_id, "\n\n"))
                                    first = False
                                elif isinstance(ev, PartDeltaEvent) and isinstance(
                                    ev.delta, TextPartDelta
                                ):
                                    text = ev.delta.content_delta
                                if text:
                                    said = True
                                    self.emit(TextDelta(self.brief_id, text))
                    elif Agent.is_call_tools_node(node):
                        self._say_tools(run_id, spec, node.model_response)
                    self._save(run_id, run.all_messages()[len(earlier) :])
            finally:
                self.lead_run = None
                self._tools_done(run_id)
            self._save(run_id, run.all_messages()[len(earlier) :])
            output = run.result.output
        if isinstance(output, DeferredToolRequests):
            return _DEFERRED
        return output

    # The Subscription Link -------------------------------------------------------------------

    async def _job(self, run_id: str, spec: AgentSpec, choice: ModelChoice, task: str) -> str:
        """One run on an agent connector (the engineer's Claude Code), with its own MCP token.
        Keeps a mirror of what it did as an ordinary history."""
        connector = self.found[choice.connector]
        run = self.store.run(run_id)
        card = self.card(choice)
        role: Role = spec.role if spec.role != "specialist" else spec.tier
        effort = self.lead_effort(choice) if run_id == self.lead_run_id else None
        await self.engine.spending.before_request(self, brief_id=self.brief_id, card=card)
        mirror = _load(run["history"])
        prompt = task
        if run["session_id"] is not None:
            prompt = copy.CONTINUE_AFTER_RESTART if final_text(mirror) is None else task
        if not mirror or final_text(mirror) is not None:
            mirror.append(ModelRequest(parts=[UserPromptPart(task)]))

        def on_result(name: str, args: dict, text: str) -> None:
            call_id = f"mcp-{uuid4().hex[:12]}"
            mirror.append(ModelResponse(parts=[ToolCallPart(name, args, tool_call_id=call_id)]))
            mirror.append(ModelRequest(parts=[ToolReturnPart(name, text, tool_call_id=call_id)]))
            self._save(run_id, mirror)
            on = self._focus(name, args)
            if on is not None:
                self._agent(run_id, focus=on)

        ctx = self.lead_ctx if run_id == self.lead_run_id else self._ctx(run_id, spec)
        # Claude Code is given every tool at once: no group to open
        spec = replace(spec, tools=tuple(t for t in spec.tools if t != tool_groups.OPEN))
        token = self.engine.mcp.issue(RunScope(ctx, spec.tools, on_result))
        self.tokens.add(token)
        job_type = _agent_job()
        job = job_type(
            run_id=run_id,
            brief_id=self.brief_id,
            spec=spec,
            task=prompt,
            model=choice.model,
            mcp_url=self.engine.mcp_url(),
            mcp_token=token,
            tools=spec.tools,
            cwd=self.engine.data_dir / WORK / run_id,
            resume=run["session_id"],
            effort=effort,
        )
        if run_id == self.lead_run_id:
            self.claude_lead = (connector, run_id)
        try:
            outcome = await connector.run(job, self.emit)
        finally:
            self.claude_lead = None
            self.engine.mcp.revoke(token)
            self.tokens.discard(token)
        if outcome.session_id and self.cancel_mode != "crash":
            self.store.set_run(run_id, session_id=outcome.session_id)
        self.engine.spending.after_response(
            brief_id=self.brief_id,
            project_id=self.place.project_id,
            run_id=run_id,
            role=role,
            card=card,
            input_tokens=sum(n for _, n, _ in outcome.usage),
            output_tokens=sum(n for _, _, n in outcome.usage),
            reported_usd=outcome.reported_usd,
            effort=effort,
        )
        if outcome.ended == "limit":
            raise _Busy()
        if outcome.ended == "signed_out":
            raise _Fail(copy.CLAUDE_CODE_SIGNED_OUT)
        if outcome.ended == "stopped":
            raise asyncio.CancelledError()
        if outcome.ended not in ("done", "max_tokens"):
            raise _Fail(copy.fill(copy.AI_FAILED, provider=connector.name))
        mirror.append(ModelResponse(parts=[TextPart(outcome.text)]))
        self._save(run_id, mirror)
        return outcome.text

    async def _lead_job(self, run_id: str, spec: AgentSpec, choice: ModelChoice) -> str:
        self._agent(run_id, state="working", model=choice.model)
        # Claude Code reads only its instructions file: a Brief from code's own instruction
        # (Plan 8) and the canvas selection go there.
        for extra in (reply_line(self.text), self.instruction, selection.line(self.selection)):
            if extra:
                spec = replace(spec, instructions=f"{spec.instructions}\n\n{extra}")
        return await self._job(run_id, spec, choice, self.text)

    # Specialists and the checker ---------------------------------------------------------------

    async def _specialist_pass(
        self, run_id: str, spec: AgentSpec, task: str, choice: ModelChoice
    ) -> str:
        if not self._model(choice):
            return await self._job(run_id, spec, choice, task)
        own = cut_back(_load(self.store.run(run_id)["history"]))
        prompt = task if not own or final_text(own) is not None else None
        ctx = self._ctx(run_id, spec)
        agent = agents.build_agent(
            spec, self._costed(run_id, spec.tier, choice), self._toolset(spec, ctx), output_type=str
        )
        # what a specialist writes for the engineer is in the engineer's language (audit C6)
        extra = reply_line(self.text) if spec.role == "specialist" else None
        if spec.role == "specialist":  # ONE's own principles, whatever the Lead wrote (5 Nov)
            extra = "\n\n".join((truth.today_line(self.engine.clock()), extra, SPECIALIST_RULES))
        async with agent.iter(
            prompt, message_history=own or None, instructions=extra, retries=TOOL_RETRIES
        ) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    self._say_tools(run_id, spec, node.model_response)
                else:
                    self._tools_done(run_id)
                self._save(run_id, run.all_messages())
            self._tools_done(run_id)
            self._save(run_id, run.all_messages())
            return run.result.output

    async def _check_pass(
        self,
        run_id: str,
        spec: AgentSpec,
        packet: CheckPacket,
        maker: ModelChoice,
        choice: ModelChoice,
    ) -> Review:
        ctx = self._ctx(run_id, spec)
        mine, theirs = self.card(choice), self.card(maker)
        if not self._model(choice):
            text = await self._job(
                run_id,
                spec,
                choice,
                f"{checker.packet_text(packet, ctx.fence)}\n\n{REVIEW_AS_JSON}",
            )
            try:
                out = checker.ReviewOut.model_validate_json(
                    text[text.index("{") : text.rindex("}") + 1]
                )
            except ValueError:
                raise _Fail(copy.fill(copy.AI_FAILED, provider=self._provider(choice))) from None
            return Review(
                code=out.code,
                comments=tuple(c.model_dump() for c in out.comments),
                checker=choice,
                same_provider=mine.provider == theirs.provider,
                round=1,
                checked=tuple(out.checked),
            )
        return await checker.review(
            packet,
            self._costed(run_id, "checker", choice),
            checker=mine,
            maker=theirs,
            toolset=self._toolset(spec, ctx),
            fence=ctx.fence,
        )

    # The whole Brief ---------------------------------------------------------------------------

    async def _prepare(self) -> None:
        if self._given_sheet is not None:
            sheet, found = self._given_sheet
        else:
            sheet, found = await self.engine.sheet()
        self.sheet, self.found = sheet, {c.id: c for c in found}
        allowed = {c.choice for c in sheet}
        defaults = roles.defaults(sheet)
        saved = {r: c for r, c in roles.saved().items() if c in allowed}
        self.saved_roles = set(saved)
        picked: dict[Role, ModelChoice] = defaults | saved
        if self.lead_choice in allowed:  # picked in the message box for this Brief
            picked["lead"] = self.lead_choice
        if "lead" not in picked:
            picked["lead"] = sheet[0].choice
        for role in roles.ROLES:
            picked.setdefault(role, picked["lead"])
        book, project = self.engine.book, self.place.project_id
        measured = book.tokens_per_request(project)
        # the Lead's requests as measured at this Brief's effort (each effort costs its own)
        effort = self.lead_effort(picked["lead"])
        lead_measured = measured if effort is None else book.tokens_per_request(project, effort)
        self.setup = TeamSetup(tuple(sheet), picked, measured, lead_measured)
        lead = next(
            (
                r
                for r in self.store.runs(self.brief_id)
                if r["parent_id"] is None and r["spec"].role == "lead"
            ),
            None,
        )
        # The General chat's Lead has its three tools only; a project's has the project's.
        spec = general.lead_spec() if self.place.rec is None else agents.lead_spec()
        introduced = engineer.card_line(engineer.card(self.engine.engineer_records()))
        if introduced:  # the introduction card's one line (Plan 8)
            spec = replace(spec, instructions=f"{spec.instructions}\n\n{introduced}")
        if lead is None:
            self.lead_run_id = self.store.new_run(self.brief_id, spec, picked["lead"], None)
        else:
            self.lead_run_id = lead["id"]
        self.lead_ctx = self._ctx(self.lead_run_id, spec)
        choice = self.store.run(self.lead_run_id)["choice"]
        self._agent(self.lead_run_id, spec=spec, model=choice.model, state="thinking")

    def results(self) -> list[str]:
        """What the Brief's tools gave (the team's own words do not count)."""
        return _tool_results(self.store.runs(self.brief_id))

    # The truth checks (engine.truth) ---------------------------------------------------------

    def _did(self) -> truth.Brief:
        """What this Brief did, from its runs' tool results: the facts a reply is checked on."""
        did = truth.Brief(tool_names=frozenset(n for n in REGISTRY if "_" in n))
        for run in self.store.runs(self.brief_id):
            spec = run["spec"]
            if spec.role == "specialist":
                did.specialists += (spec.name["en"], spec.name["ar"])
            if not run["history"]:
                continue
            for name, ok, said in outcomes(run["history"]):
                if ok:
                    did.done.add(name)
                    did.refused.pop(name, None)
                else:
                    did.refused[name] = self._refusal(name, said)
            for name, text in agents.tool_returns(run["history"]):
                tool = REGISTRY.get(name)
                if tool is None or text.startswith(NOT_DONE):
                    continue
                if tool.writes and (name not in team.TEAM_TOOLS or name == "make_deliverable"):
                    did.writes += 1
                if name in ("deliverable_create", "make_deliverable"):
                    did.deliverables += 1
                did.shown = did.shown or name == view.TOOL
                did.understood = did.understood or name == understand.TOOL
                if name == "add_source":
                    try:
                        found = json.loads(text)
                    except ValueError:
                        continue
                    if isinstance(found, dict) and found.get("covers") == "supply":
                        did.supply_only += (str(found.get("title", "")),)
            if not did.understood:
                refused = _refused(run["history"], understand.TOOL)
                did.understood_refused = refused or did.understood_refused
        if self.place.rec is not None and "deliverable_create" in did.done:
            did.item_rows = self._item_rows()
        return did

    def _refusal(self, tool: str, said: str) -> Text:
        """Why a call of `tool` was refused, in the engineer's words: as the tool said it, or the
        words of ONE's own text in the refusal, or a plain line naming the step."""
        found = self.refusals.get(tool) or copy.words_for(said)
        if found is not None:
            return {lang: words.rstrip() for lang, words in found.items()}
        step = copy.tool_step(tool)
        step = step if "{" not in step["en"] else copy.TOOL_STEP
        return copy.fill(copy.REFUSED_STEP, step=step)

    def _item_rows(self) -> int | None:
        """The item rows in the Sheets this Brief made, and the numbers it set or added on items
        through suggested changes; None when it made no Sheet."""
        made: list[str] = []
        changes: list[str] = []
        for run in self.store.runs(self.brief_id):
            if not run["history"]:
                continue
            for name, text in agents.tool_returns(run["history"]):
                try:
                    out = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(out, dict):
                    continue
                if name == "deliverable_create" and isinstance(out.get("id"), str):
                    made.append(out["id"])
                elif name == "deliverable_propose" and isinstance(out.get("change_ids"), list):
                    changes += [c for c in out["change_ids"] if isinstance(c, str)]
        try:
            with self.place.rec.read() as c:
                made = [
                    d
                    for d in made
                    if c.execute(
                        "SELECT 1 FROM deliverables WHERE id = ? AND kind = 'sheet'", (d,)
                    ).fetchone()
                ]
                if not made:
                    return None
                rows = 0
                for d in made:
                    (n,) = c.execute(
                        "SELECT count(*) FROM parts WHERE deliverable_id = ? AND kind = 'item'"
                        " AND valid_until IS NULL AND removed = 0",
                        (d,),
                    ).fetchone()
                    rows += n
                for change in changes:
                    row = c.execute("SELECT op FROM changes WHERE id = ?", (change,)).fetchone()
                    op = json.loads(row[0]).get("op") if row else None
                    rows += op in ("set_number", "add_item_row")
        except Exception:  # noqa: BLE001 - an older file: the check is left out, never the reply
            return 1
        return rows

    def _reply_problems(self, output: str) -> list[truth.Problem]:
        rec = self.place.rec
        found = truth.reply_problems(
            output,
            cov=truth.coverage(rec) if rec is not None else None,
            did=self._did(),
            engineer_text=self.text,
            understand_brief=self.instruction == understand.INSTRUCTION,
        )
        if rec is not None:  # each number at the row or page the reply cites for it
            with rec.read() as c:
                found += truth.miscited(c, output)
        return found

    async def _truthful(self, output: Any) -> Any:
        """The Lead's answer against ONE's records, before the engineer relies on it. Once per
        Brief, what it says that the records do not show (a blank for a value, a promise of work
        that is not running, more priced items than there are, a change never made) goes back
        for the Lead to fix, and the screen drops the words it replaces (`data-redo`)."""
        if not isinstance(output, str) or self.truth_retried:
            return output
        problems = await asyncio.to_thread(self._reply_problems, output)
        if not problems:
            return output
        self.truth_retried = True
        cut = {"from": self.answer_from, "to": self.said}
        self.redo_cleared = self.answer_from == 0
        self.emit(Data(self.brief_id, "redo", self.brief_id, cut))
        raise ModelRetry(
            "ONE checked your answer against its records before the engineer reads it. Answer "
            "again, fixing this:\n- " + "\n- ".join(p.fix for p in problems)
        )

    async def _facts(self, output: str) -> None:
        """The facts beside the reply, from ONE's own records (`data-facts`): the BOQ's real
        coverage and its Deliverables, with a flag for each claim the records do not show; and
        the way to set up web search when the reply says ONE could not search."""
        problems = await asyncio.to_thread(self._reply_problems, output)
        rec = self.place.rec
        cov = await asyncio.to_thread(truth.coverage, rec) if rec is not None else None
        flags = [p.flag for p in problems if p.flag]
        did = self._did()
        worked = did.writes or truth.PRICED.search(output)
        found = truth.facts(cov, flags) if flags or worked else None
        no_search = bool(
            rec is not None and _NO_SEARCH_SAID.search(output) and self._search_line() is not None
        )
        if found is not None:
            self.emit(Data(self.brief_id, "facts", self.brief_id, found))
        if no_search:
            self.emit(_no_search_notice(self.brief_id))
        self.worklog.truth = (self.worklog.truth or {}) | {"facts": found, "no_search": no_search}

    async def _finish(self, output: Any) -> None:
        if isinstance(output, str):
            results = self.results()
            marked = await asyncio.to_thread(_marked, self.place.rec, output, results)
            if marked:
                self.emit(Unsourced(self.brief_id, tuple(marked)))
            self.worklog.truth = (self.worklog.truth or {}) | {"unsourced": marked}
            named = numbers_guard.sourced(output, results)
            if named:  # decision 16.3: each opens into its ledger number's source card
                self.emit(Data(self.brief_id, "sourced", self.brief_id, {"numbers": named}))
            await self._facts(output)
        drafts = self.store.unchecked(self.brief_id)
        if self.place.rec is not None:  # Plan 6: the Deliverables this Brief made or changed
            returns = [
                found
                for run in self.store.runs(self.brief_id)
                if run["history"]
                for found in agents.tool_returns(run["history"])
            ]
            drafts += await asyncio.to_thread(outputs.unchecked, self.place.rec, returns)
        for draft in drafts:
            if checker.has_numbers(draft):
                try:
                    await team.check_deliverable(self.lead_ctx, draft.id)
                except ModelRetry:
                    pass  # settled meanwhile

    def _withdraw(self) -> None:
        for card in self.store.pending(self.brief_id):
            self.emit(Data(self.brief_id, "card", card.id, {"status": "withdrawn"}))
        self.store.withdraw_pending(self.brief_id)

    def _track_done(self) -> None:
        """Usage Stats' one `brief_done`: counts only, never a Desk's name (Plan 8)."""
        specialists = [
            r["spec"] for r in self.store.runs(self.brief_id) if r["spec"].role == "specialist"
        ]
        cost = self.engine.book.spent(brief_id=self.brief_id, count_equivalent=True)
        started = datetime.fromisoformat(self.store.brief(self.brief_id)["created_at"])
        usage.track(
            "brief_done",
            desks=len({s.desk or self.brief_id for s in specialists}),
            specialists=len(specialists),
            off_desk=bool(specialists),  # every Desk is Temporary or Draft until Plan 9
            cost_usd_cents=int((cost * 100).to_integral_value(ROUND_HALF_UP)),
            minutes=max(0, round((utc_now() - started).total_seconds() / 60)),
        )

    async def main(self) -> None:
        try:
            if self.step is None:
                self.step = copy.STEP_QUEUED
            self.set_state("queued")
            async with self.engine._brief_slots:
                self.set_state(
                    "running", copy.STEP_STARTED if self.step == copy.STEP_QUEUED else None
                )
                await self._prepare()
                try:
                    output = await self._lead()
                except CapReached as reached:
                    if not reached.report:
                        raise
                    self.set_state("paused_cap")
                    try:
                        await self._lead(report=True)
                    except CapReached:
                        pass
                    raise
                await self._finish(output)
                self.output = output
                self.set_state("done", copy.STEP_DONE)
                self._track_done()
        except asyncio.CancelledError:
            if self.cancel_mode == "crash":
                raise
            self._withdraw()
            if self.cancel_mode == "stop":
                self.set_state("stopped", copy.STOPPED)
            else:
                self.emit(Status(self.brief_id, self.state, self.step))
        except CapReached:
            self.set_state("stopped", copy.STOPPED)
        except (CallRefused, _Fail) as failed:
            self._withdraw()
            self.set_state("failed", failed.text)
        except RecordsError as failed:
            log.warning("brief %s: records error", self.brief_id)
            self.set_state("failed", failed.text)
        except Exception as error:
            log.exception("brief %s failed", self.brief_id)
            usage.crash(error)  # a bug in One: its class and line, never the message
            self._withdraw()
            # only `_attempts` knows a provider's error; anything that reaches here is ONE's own
            self.set_state("failed", copy.CORE_FAILED)
        finally:
            self.finished = True
            for token in tuple(self.tokens):
                self.engine.mcp.revoke(token)
            self.engine._ended(self)
            self._notify()


def _agent_job():
    from qsone.engine.connectors.claude_code import AgentJob

    return AgentJob


# The engine ----------------------------------------------------------------------------------


class Engine:
    """Every Brief of this core. One for the app (`app.state.engine`)."""

    def __init__(
        self,
        *,
        projects: Projects,
        data_dir: Path,
        connectors: Callable[[], list] | None = None,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        max_briefs: int = 3,
        max_agents: int = 3,
        mcp: McpGate | None = None,
        meaning: Any = None,
        services: Any = None,
    ) -> None:
        self.projects = projects
        self.data_dir = Path(data_dir)
        self.connectors = connectors or (lambda: connectors_mod.connectors())
        self.clock = clock
        self.sleep = sleep
        self.mcp = mcp or McpGate()
        self.meaning = meaning
        self.services = services  # Plan 5's `tools.services.Services`, set by the app (Task 15)
        self.base_url: str | None = None  # the core's own address, for the MCP config
        self._brief_slots = asyncio.Semaphore(max_briefs)
        self._agent_slots = asyncio.Semaphore(max_agents)
        self._briefs: dict[str, _Brief] = {}
        self._outputs: dict[str, Any] = {}
        self._ended_unseen: dict[str, dict] = {}  # chat id: its last Brief, done or failed, unseen
        self._close_after: set[str] = set()  # projects to close when their Brief ends
        self._general: Records | None = None
        self.book: CostBook
        self.spending: Spending

    # Life ------------------------------------------------------------------------------------

    def _ready(self) -> None:
        if self._general is None or not self._general.is_open:
            self._general = general.open_engineer_records(self.data_dir, self._escrow)
            self.book = CostBook(self._general)
            self.spending = Spending(self.book, clock=self.clock)

    def _escrow(self):
        """The account's Backup key escrow, asked only when a lost key is looked for."""
        backups = getattr(self.projects, "backups", None)
        return backups.escrow() if backups is not None else None

    def engineer_records(self) -> Records:
        """The open Engineer Records file (Plan 5's tools use it). Raises `RecordsError` when
        it does not open."""
        self._ready()
        assert self._general is not None
        return self._general

    def cost_book(self) -> CostBook | None:
        """The open cost book, or None before `start` or while the file is not open."""
        return self.book if self._general is not None and self._general.is_open else None

    async def start(self) -> None:
        """Opens the Engineer Records file. Never continues a Brief by itself. A file that does
        not open leaves the app up: each Brief then answers why, in plain words."""
        try:
            self._ready()
        except (RecordsError, OSError) as e:  # the core starts anyway
            log.warning("The Engineer Records file did not open (%s)", type(e).__name__)

    async def _cancel(self, mode: str) -> int:
        briefs = [b for b in self._briefs.values() if b.task is not None and not b.finished]
        for b in briefs:
            b.cancel_mode = mode
            b.task.cancel()
        await asyncio.gather(*(b.task for b in briefs), return_exceptions=True)
        return len(briefs)

    async def pause_all(self) -> int:
        """Plan 8: every running Brief stops at its Checkpoint and waits for Continue."""
        return await self._cancel("pause")

    async def shutdown(self) -> None:
        """Stops every Brief, keeping its Checkpoint, and closes the Engineer Records file."""
        await self._cancel("pause")
        if self._general is not None:
            self._general.close()

    async def crash(self) -> None:
        """For tests: what a power cut leaves (no bookkeeping at all)."""
        await self._cancel("crash")
        if self._general is not None:
            self._general.close()

    def mcp_url(self) -> str:
        if self.base_url is None:
            raise _Fail(copy.fill(copy.AI_FAILED, provider="Claude Code"))
        return self.base_url.rstrip("/") + "/mcp"

    # Where a chat lives ------------------------------------------------------------------------

    def _place(self, chat_id: str) -> _Place:
        """Raises `RecordsError` when the project is not open."""
        self._ready()
        if chat_id == GENERAL:
            return _Place(Store(self._general, project_id=None), None, None, None)
        rec = self.projects.get(chat_id)
        return _Place(Store(rec, project_id=chat_id), rec, chat_id, rec.meta()["name"])

    def _places(self) -> list[_Place]:
        """General and every project on this computer, opened if needed."""
        found = [self._place(GENERAL)]
        for project in self.projects.list():
            if "error" in project:
                continue
            try:
                self.projects.open(project["id"])
                found.append(self._place(project["id"]))
            except RecordsError:
                continue
        return found

    def _in(self, channel: str) -> list[_Brief]:
        return [b for b in self._briefs.values() if b.place.channel == channel]

    def _publish(self, channel: str, event: dict) -> None:
        activity.publish(channel, event)

    def _ended(self, brief: _Brief) -> None:
        self._briefs.pop(brief.brief_id, None)
        self._outputs[brief.brief_id] = brief.output
        if brief.cancel_mode == "crash":
            return
        if brief.state in ("done", "failed"):
            self._ended_unseen[brief.chat_id] = _chat_activity(brief, brief.state)
        else:  # stopped by the engineer, or paused with the core: nothing to tell
            self._ended_unseen.pop(brief.chat_id, None)
        if brief.chat_id in self._close_after and self.active(brief.chat_id) is None:
            self._close_after.discard(brief.chat_id)
            asyncio.get_running_loop().run_in_executor(None, self._close, brief.chat_id)
        for agent in brief.agents.values():
            self._publish(brief.place.channel, {"type": "agent-gone", "id": agent.run_id})
        if brief.state in ("done", "stopped", "failed"):
            for run in brief.store.runs(brief.brief_id):
                shutil.rmtree(self.data_dir / WORK / run["id"], ignore_errors=True)

    async def sheet(self) -> tuple[list[ModelCard], list]:
        """The Model Data Sheet and the connectors. Raises `NoAI` when it is empty."""
        found = self.connectors()
        listed, errors = await cards.listed(found)
        if not listed:
            raise NoAI(next(iter(errors.values()), copy.NO_AI))
        return listed, found

    # Briefs ----------------------------------------------------------------------------------

    def active(self, chat_id: str) -> str | None:
        for b in self._briefs.values():
            if b.chat_id == chat_id and not b.finished:
                return b.brief_id
        return None

    async def start_brief(
        self,
        chat_id: str,
        text: str,
        *,
        instruction: str | None = None,
        output_type: type | None = None,
        selection: list[dict] | None = None,
        lead: ModelChoice | None = None,
        effort: Effort | None = None,
    ) -> str:
        """Starts a Brief in the chat (a project id or "general"), under the caps. `selection`
        is what the engineer selected on the canvas (`engine.selection.read`). `lead` and
        `effort` are the Lead QS's model and effort picked in the message box; without them the
        Lead runs on its role's model at its provider's own effort. An effort the model does not
        accept is dropped. Raises `BriefBusy`, `NoAI` (also for a `lead` no longer on the Model
        Data Sheet) and `RecordsError`."""
        place = self._place(chat_id)
        busy = self.active(chat_id)
        if busy is not None:
            raise BriefBusy(busy)
        sheet = await self.sheet()
        busy = self.active(chat_id)
        if busy is not None:
            raise BriefBusy(busy)
        if lead is not None:
            card = next((c for c in sheet[0] if c.choice == lead), None)
            if card is None:
                raise NoAI(copy.CHAT_MODEL_GONE)
            if effort not in card.efforts:
                effort = None
        brief_id = place.store.new_brief(chat_id, text, selection, effort=effort)
        self._launch(
            _Brief(
                self,
                place,
                place.store.brief(brief_id),
                instruction=instruction,
                output_type=output_type,
                sheet=sheet,
                lead=lead,
            )
        )
        log.info("brief %s started", brief_id)
        return brief_id

    def _launch(self, brief: _Brief) -> None:
        self._briefs[brief.brief_id] = brief
        self._ended_unseen.pop(brief.chat_id, None)  # the chat's new Brief is what it does now
        brief.task = asyncio.create_task(brief.main(), name=f"brief-{brief.brief_id}")

    async def result(self, brief_id: str) -> Any:
        """The Brief's output when it ends (Plan 8: a Brief from code with its `output_type`)."""
        brief = self._briefs.get(brief_id)
        if brief is not None and brief.task is not None:
            await asyncio.gather(brief.task, return_exceptions=True)
        return self._outputs.get(brief_id)

    def _brief(self, brief_id: str) -> _Brief:
        brief = self._briefs.get(brief_id)
        if brief is None or brief.finished:
            raise LookupError(brief_id)
        return brief

    def events(self, brief_id: str) -> AsyncIterator[Event]:
        """The Brief's events from its start, then live until it ends."""
        brief = self._briefs.get(brief_id)
        if brief is None:
            raise LookupError(brief_id)
        return brief.events()

    async def stop(self, brief_id: str) -> None:
        """Raises `LookupError` when the Brief is not running."""
        brief = self._brief(brief_id)
        brief.cancel_mode = "stop"
        assert brief.task is not None
        brief.task.cancel()
        await asyncio.gather(brief.task, return_exceptions=True)

    async def steer(self, brief_id: str, text: str) -> None:
        """Raises `LookupError` when the Brief is not running."""
        brief = self._brief(brief_id)
        if brief.lead_run is not None:
            brief.lead_run.enqueue(text)
        elif brief.claude_lead is not None:
            connector, run_id = brief.claude_lead
            try:
                await connector.steer(run_id, text)
            except LookupError:
                brief.steering.append(text)
        else:
            brief.steering.append(text)
        log.info("brief %s steered", brief_id)

    async def answer(self, card_id: str, choice: str) -> None:
        """Raises `LookupError` when no running Brief waits on the card, `ValueError` with a
        choice that is not one of its options."""
        for brief in tuple(self._briefs.values()):
            if card_id in brief.waiting:
                brief.answer(card_id, choice)
                return
        raise LookupError(card_id)

    def options(self, card_id: str) -> list[str]:
        card = self.card(card_id)
        return [] if card is None else list(card.options)

    def card(self, card_id: str) -> Card | None:
        """The card a running Brief waits on, or None."""
        for brief in self._briefs.values():
            if card_id in brief.waiting:
                return brief.waiting[card_id][0]
        return None

    def unfinished(self) -> list[dict]:
        """Every unfinished Brief that is not running now, in every project and General."""
        found = []
        for place in self._places():
            for b in place.store.unfinished():
                if b["id"] in self._briefs:
                    continue
                found.append(
                    {
                        "id": b["id"],
                        "chat_id": b["chat_id"],
                        "project_name": place.project_name,
                        "step": b["step"] or copy.STEP_STARTED,
                        "state": b["status"],
                    }
                )
        return found

    async def continue_brief(self, brief_id: str) -> None:
        """Continues an unfinished Brief from its last Checkpoint. Raises `LookupError`."""
        if brief_id in self._briefs:
            return
        for place in self._places():
            try:
                brief = place.store.brief(brief_id)
            except LookupError:
                continue
            if brief["status"] not in UNFINISHED:
                break
            busy = self.active(brief["chat_id"])
            if busy is not None:
                raise BriefBusy(busy)
            place.store.withdraw_pending(brief_id)  # a stale approval: the redone call asks again
            runner = _Brief(self, place, brief)
            runner.log += _stored_events(place.store, brief, self)
            self._launch(runner)
            log.info("brief %s continued", brief_id)
            return
        raise LookupError(brief_id)

    def leave_brief(self, brief_id: str) -> None:
        """The engineer chose not to continue an unfinished Brief: it ends as stopped, its
        waiting cards withdrawn, so it is never offered again. Raises `BriefBusy` while it
        runs, `LookupError` when no unfinished Brief has the id."""
        if brief_id in self._briefs:
            raise BriefBusy(brief_id)
        for place in self._places():
            try:
                brief = place.store.brief(brief_id)
            except LookupError:
                continue
            if brief["status"] not in UNFINISHED:
                break
            place.store.withdraw_pending(brief_id)
            place.store.set_status(brief_id, "stopped", copy.STOPPED)
            log.info("brief %s left", brief_id)
            return
        raise LookupError(brief_id)

    # The chat as stored ----------------------------------------------------------------------

    def chat_messages(self, chat_id: str) -> list[dict]:
        """AI SDK UI messages, rebuilt from the chat's stored Briefs, oldest first."""
        from qsone.engine.stream import message_parts

        place = self._place(chat_id)
        with place.store.rec.read() as c:
            ids = [
                i
                for (i,) in c.execute(
                    "SELECT id FROM briefs WHERE chat_id = ? ORDER BY created_at, rowid",
                    (chat_id,),
                ).fetchall()
            ]
        messages = []
        for brief_id in ids:
            brief = place.store.brief(brief_id)
            question = {
                "id": question_id(brief_id),
                "role": "user",
                "parts": [{"type": "text", "text": brief["text"]}],
            }
            if brief["selection"]:  # the chip on the engineer's message (Plan 7)
                question["metadata"] = {"selection": brief["selection"]}
            messages.append(question)
            running = self._briefs.get(brief_id)
            if running is not None:
                parts = message_parts(running.log)
            else:
                waiting = brief["status"] in UNFINISHED
                events = _stored_events(place.store, brief, self, unfinished=waiting)
                parts = message_parts(events, with_status=not waiting)
            messages.append({"id": reply_id(brief_id), "role": "assistant", "parts": parts})
        if place.rec is not None:  # what ONE found in each drop of files, in its place in time
            messages = _with_reports(messages, place.rec)
        return messages

    # Plan 7 ------------------------------------------------------------------------------------

    def team(self, project_id: str) -> dict:
        """Plan 7's `{desks: [DeskInfo], agents: [AgentInfo]}` for the project ("general" for
        the General chat)."""
        running = self._in(project_id)
        saved = [
            {"id": d["slug"], "name": d["name"], "stage": "draft"}
            for d in desks.saved(self.data_dir)
        ]
        temporary = [
            b.desk() for b in running if any(a.spec.role == "specialist" for a in b.agents.values())
        ]
        agents_now = [b.agent_info(a) for b in running for a in b.agents.values()]
        return {"desks": temporary + saved, "agents": agents_now}

    def activity(self, project_id: str) -> AsyncIterator[dict]:
        """Plan 7's `ActivityEvent`s for the project, as they come."""
        return activity.subscribe(project_id)

    def waiting(self, project_id: str) -> int:
        """How many cards wait for the engineer in the project's running Briefs."""
        return sum(len(b.waiting) for b in self._in(project_id))

    # Every chat at once, for the screen outside each chat (the top bar, the projects, notices)

    def chats(self) -> list[dict]:
        """Each chat with a running Brief ("working", or "waiting" while a card waits for the
        engineer) or a last Brief that ended unseen ("done", "failed"), as
        `{chat_id, brief_id, state, name}` (`name`: the project's, None for the General chat).
        From memory only: no project file is opened, so the screen may ask every few seconds."""
        found = {
            b.chat_id: _chat_activity(b, "waiting" if b.waiting else "working")
            for b in self._briefs.values()
            if not b.finished
        }
        ended = [e for chat_id, e in self._ended_unseen.items() if chat_id not in found]
        return list(found.values()) + ended

    def seen(self, chat_id: str) -> None:
        """The engineer has the chat open: its ended Brief's mark clears."""
        self._ended_unseen.pop(chat_id, None)

    def keep_open(self, project_id: str) -> bool:
        """Asked before the screen closes a project: True while a Brief runs in it, whose file
        then stays open and closes when the Brief ends, so moving on never cuts it short."""
        if self.active(project_id) is None:
            return False
        self._close_after.add(project_id)
        return True

    def opened(self, project_id: str) -> None:
        """The project was opened again: it stays open after its Brief ends."""
        self._close_after.discard(project_id)

    def _close(self, project_id: str) -> None:
        try:
            self.projects.close(project_id)
        except (RecordsError, OSError) as e:  # it closes with the core anyway
            log.warning(
                "project %s did not close after its Brief (%s)", project_id, type(e).__name__
            )


def _chat_activity(brief: _Brief, state: str) -> dict:
    return {
        "chat_id": brief.chat_id,
        "brief_id": brief.brief_id,
        "state": state,
        "name": brief.place.project_name,
    }


def _marked(rec: Records | None, reply: str, results: list[str]) -> list[str]:
    """The numbers of a reply with no source: none of the Brief's tools gave them, no item's
    own words have them (a size, «طوب 25 سم»), and no place the reply cites has them (a number
    read from a cited page carries that source: the bid security on page 26, 6 Nov 2026)."""
    marked = numbers_guard.unsourced(reply, numbers_guard.known_values(results))
    if marked and rec is not None:
        marked = numbers_guard.described(reply, marked, _descriptions(rec))
    if marked and rec is not None:
        with rec.read() as c:
            cited = truth.cited_values(c, reply)
        if cited:
            marked = [m for m in marked if numbers_guard.known_values([m]) - cited]
    return marked


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


def _first_said(history: bytes | None) -> datetime | None:
    """When the Lead first said something: its first response with words."""
    for m in _load(history):
        if isinstance(m, ModelResponse) and any(
            isinstance(p, TextPart) and p.content for p in m.parts
        ):
            return m.timestamp
    return None


def _stored_events(
    store: Store, brief: dict, engine: Engine, *, unfinished: bool = False
) -> list[Event]:
    """A Brief as events again, from what is stored: the Lead's words, the Coordination Room,
    the cards and their answers, the Deliverable cards, the Reviews, the unsourced marks and the
    state. A card asked before the Lead first spoke comes before its words, as it did live.
    `unfinished`: the Brief waits for Continue, so a card still pending shows as withdrawn (no
    one waits on it; Continue asks it again)."""
    brief_id = brief["id"]
    events: list[Event] = []
    runs = store.runs(brief_id)
    lead = next((r for r in runs if r["parent_id"] is None and r["spec"].role == "lead"), None)
    reply = lead_text(_load(lead["history"])) if lead is not None else ""
    said_at = _first_said(lead["history"]) if reply and lead is not None else None
    with store.rec.read() as c:
        approvals = c.execute(
            "SELECT card, status, choice, asked_at, settled_at FROM approvals"
            " WHERE brief_id = ? ORDER BY asked_at, rowid",
            (brief_id,),
        ).fetchall()
    before: list[Event] = []  # the cards asked before the Lead spoke (a prefix: oldest first)
    after: list[Event] = []
    for card_text, status, choice, asked_at, settled_at in approvals:
        d = json.loads(card_text)
        card = Card(**{**d, "options": tuple(d["options"])})
        early = said_at is not None and not after and datetime.fromisoformat(asked_at) < said_at
        found = before if early else after
        found.append(Asked(brief_id, card))
        if status == "settled":
            found.append(Settled(brief_id, card.id, choice, settled_at))
        elif status == "withdrawn" or (unfinished and status == "pending"):
            found.append(Data(brief_id, "card", card.id, {"status": "withdrawn"}))
    events += before
    if reply:
        events.append(TextDelta(brief_id, reply))
    if lead is not None and lead["history"]:
        returns = agents.tool_returns(lead["history"])
        events += general.stored_cards(brief_id, returns)
        events += understand.stored_cards(brief_id, returns)  # Plan 8's card
        events += view.stored_views(store.rec, brief_id, lead["history"])  # decision 16.1
    for run in runs:  # the Deliverable cards, from whichever agent made them (Plan 6)
        if run["history"]:
            events += outputs.stored_cards(brief_id, agents.tool_returns(run["history"]))
    for m in store.team(brief_id):
        events.append(TeamMessage(brief_id, m["id"], m["sender"], m["recipient"], m["text"]))
    with store.rec.read() as c:
        reviews = c.execute(
            "SELECT r.deliverable_id, r.code, r.comments, r.checker, r.same_provider, r.round"
            " FROM reviews r JOIN deliverable_drafts d ON d.id = r.deliverable_id"
            " WHERE d.brief_id = ? ORDER BY r.at, r.rowid",
            (brief_id,),
        ).fetchall()
    events += after
    for deliverable_id, code, comments, choice, same, round_ in reviews:
        review = Review(
            code=code,
            comments=tuple(json.loads(comments)),
            checker=ModelChoice(**json.loads(choice)),
            same_provider=bool(same),
            round=round_,
        )
        events.append(Reviewed(brief_id, deliverable_id, review))
    said = json.loads(brief["worklog"]).get("truth") if brief["worklog"] else None
    said = said if isinstance(said, dict) else {}
    if reply and brief["status"] == "done":
        results = _tool_results(runs)
        marked = said.get("unsourced")  # as the core marked them then
        if marked is None:
            marked = numbers_guard.unsourced(reply, numbers_guard.known_values(results))
        if marked:
            events.append(Unsourced(brief_id, tuple(marked)))
        named = numbers_guard.sourced(reply, results)
        if named:
            events.append(Data(brief_id, "sourced", brief_id, {"numbers": named}))
    if brief["worklog"]:
        worklog = WorkLog.load(brief["worklog"], stopped_at=brief["updated_at"])
        worklog.ended = json.loads(brief["worklog"]).get("ended")
        events.append(Data(brief_id, "worklog", brief_id, worklog.as_json()))
        said = worklog.truth or {}  # the facts the core put beside the reply, as they were then
        if said.get("facts"):
            events.append(Data(brief_id, "facts", brief_id, said["facts"]))
        if said.get("no_search"):
            events.append(_no_search_notice(brief_id))
        if said.get("step_limit"):
            limit = {"text": said["step_limit"]}
            events.append(Data(brief_id, "notice", f"{brief_id}-step-limit", limit))
    events.append(Status(brief_id, brief["status"], brief["step"]))
    return events
