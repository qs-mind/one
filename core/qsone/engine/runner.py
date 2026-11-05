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
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
)
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from qsone import activity, copy
from qsone.engine import agents, cards, checker, desks, general, numbers_guard, roles, team, tools
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
)
from qsone.projects import Projects
from qsone.records.project import Records, RecordsError

log = logging.getLogger("qsone.engine.runner")

GENERAL = "general"  # the General chat's id; it lives in the Engineer Records file
WORK = "claude-work"  # <data>/claude-work/<run id>/: one Claude Code run's folder
TOOL_RETRIES = 3  # how often a model may fix one tool call, or its final answer
BUSY_WAIT = 5  # seconds before the one more try at a busy provider
OFFLINE_WAITS = (5, 15, 30, 60)  # then every 60 s while the app runs
REVIEW_AS_JSON = (  # the model reads it: a check on Claude Code answers in text
    'Answer with one JSON object only: {"code": "A" | "B" | "C", "comments": '
    '[{"about": "...", "text": "..."}]}.'
)
_ROLE_NAMES: dict[str, Text] = {
    "lead": copy.ROLE_LEAD,
    "checker": copy.ROLE_CHECKER,
    "specialist": copy.ROLE_SPECIALIST,
    "quick": copy.ROLE_QUICK,
}
_DEFERRED = object()  # the Lead's pass ended with deferred calls to run


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


def lead_text(messages: list) -> str:
    """Everything the Lead said, its answers' text, as one reply."""
    said = [
        "".join(p.content for p in m.parts if isinstance(p, TextPart))
        for m in messages
        if isinstance(m, ModelResponse)
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
    if isinstance(error, ModelAPIError | anthropic.APIError | openai.APIError):
        return "other"
    return None


def _result_value(stored: str):
    found = json.loads(stored)
    if "ok" in found:
        return found["ok"]
    if "retry" in found:
        return ModelRetry(found["retry"])
    return ToolFailed(found["failed"])


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
    ) -> None:
        self.engine = engine
        self.place = place
        self.store = place.store
        self.brief_id: str = brief["id"]
        self.chat_id: str = brief["chat_id"]
        self.text: str = brief["text"]
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
        self.sheet: list[ModelCard] = []
        self.found: dict[str, Any] = {}
        self._given_sheet = sheet
        self.lead_run_id: str | None = None
        self.lead_ctx: ToolContext | None = None
        self._news = asyncio.Event()

    # Events --------------------------------------------------------------------------------

    def _notify(self) -> None:
        self._news.set()
        self._news = asyncio.Event()

    def emit(self, event: Event) -> None:
        self.log.append(event)
        if isinstance(event, Progress):
            self._agent(event.run_id, state="working", line=event.text)
            self.step = event.text
            if self.state == "running" and self.cancel_mode != "crash":
                self.store.set_status(self.brief_id, "running", event.text)
        self._notify()

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
    ) -> None:
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
        found.at = utc_now().isoformat()
        self.engine._publish(self.place.channel, {"type": "agent", "agent": self.agent_info(found)})

    def agent_info(self, a: _AgentState) -> dict:
        desk = None
        if a.spec.role == "specialist":
            desk = a.spec.desk or self.brief_id
        return {
            "id": a.run_id,
            "role": a.spec.name,
            "desk_id": desk,
            "model": a.model,
            "state": a.state,
            "line": a.line,
            "brief_id": self.brief_id,
            "focus": None,
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
        card, future = self.waiting[card_id]
        if choice not in card.options:
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
        if choice == maker:
            others = [
                c for c in roles.same_or_cheaper(self.sheet, maker, {maker}) if self._model(c)
            ]
            others += [c for c in roles.costlier(self.sheet, maker, {maker}) if self._model(c)]
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

    def _costed(self, run_id: str, role: Role, choice: ModelChoice):
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
        )

    def _ctx(self, run_id: str, spec: AgentSpec) -> ToolContext:
        meaning = self.engine.meaning
        return ToolContext(
            brief_id=self.brief_id,
            run_id=run_id,
            agent=spec,
            rec=self.place.rec,
            store=self.store,
            host=self,
            fence=new_fence(),
            embedder=meaning.embedder() if meaning is not None else None,
            reranker=meaning.reranker() if meaning is not None else None,
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
            tool = REGISTRY.get(c.tool_name)
            words = copy.fill(copy.TOOL_WORKING, tool=c.tool_name)
            if tool is not None:
                try:
                    words = tool.activity(tool.args.model_validate(c.args_as_dict()))
                except Exception:  # noqa: BLE001 - its own words are only for the Progress Line
                    pass
            self.emit(Progress(self.brief_id, run_id, spec.name, words))

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
                kind = _error_kind(error)
                if kind is None:
                    raise
                provider = self._provider(choice)
                log.warning("run %s on %s: %s %s", run_id, choice.connector, kind, error)
                if kind == "auth":
                    raise _Fail(copy.fill(copy.AI_KEY_REFUSED, provider=provider)) from None
                if kind == "other":
                    raise _Fail(copy.fill(copy.AI_FAILED, provider=provider)) from None
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
            found += settled(_load(history))
        return found

    def _instructions(self, choice: ModelChoice) -> str:
        said = f"You run on the model {choice.model}; say so when asked which model you are."
        return said if not self.instruction else f"{said}\n\n{self.instruction}"

    async def _lead(self, *, report: bool = False) -> Any:
        assert self.lead_run_id is not None
        spec = self.lead_ctx.agent
        while True:
            if not report:
                own = cut_back(_load(self.store.run(self.lead_run_id)["history"]))
                pending = pending_deferred(own)
                if pending:
                    await self._run_deferred(self.lead_run_id, pending)
            out = await self._attempts(
                self.lead_run_id, spec, lambda c: self._lead_pass(c, report=report)
            )
            if out is not _DEFERRED:
                return out
            if report:
                return None

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

    async def _lead_pass(self, choice: ModelChoice, *, report: bool = False) -> Any:
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
        prompt = copy.REPORT_NOW if report else (None if own else self.text)
        earlier = self._earlier()
        model = self._costed(run_id, "lead", choice)
        agent = agents.build_agent(
            spec,
            model,
            self._toolset(spec, self.lead_ctx),
            output_type=[self.output_type or str, DeferredToolRequests],
        )
        said = bool(lead_text(own))
        self._agent(run_id, state="thinking", model=choice.model)
        async with agent.iter(
            prompt,
            message_history=(earlier + own) or None,
            deferred_tool_results=results,
            instructions=self._instructions(choice),
            retries=TOOL_RETRIES,
        ) as run:
            self.lead_run = run
            try:
                while self.steering:
                    run.enqueue(self.steering.pop(0))
                async for node in run:
                    if Agent.is_model_request_node(node):
                        self._agent(run_id, state="thinking")
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

        ctx = self.lead_ctx if run_id == self.lead_run_id else self._ctx(run_id, spec)
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
        async with agent.iter(prompt, message_history=own or None, retries=TOOL_RETRIES) as run:
            async for node in run:
                if Agent.is_call_tools_node(node):
                    self._say_tools(run_id, spec, node.model_response)
                self._save(run_id, run.all_messages())
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
        chosen = {r: c for r, c in roles.chosen(sheet).items() if c in allowed}
        picked: dict[Role, ModelChoice] = defaults | chosen
        if "lead" not in picked:
            picked["lead"] = sheet[0].choice
        for role in roles.ROLES:
            picked.setdefault(role, picked["lead"])
        measured = self.engine.book.tokens_per_request(self.place.project_id)
        self.setup = TeamSetup(tuple(sheet), picked, measured)
        lead = next(
            (
                r
                for r in self.store.runs(self.brief_id)
                if r["parent_id"] is None and r["spec"].role == "lead"
            ),
            None,
        )
        spec = agents.lead_spec()
        if lead is None:
            self.lead_run_id = self.store.new_run(self.brief_id, spec, picked["lead"], None)
        else:
            self.lead_run_id = lead["id"]
        self.lead_ctx = self._ctx(self.lead_run_id, spec)
        choice = self.store.run(self.lead_run_id)["choice"]
        self._agent(self.lead_run_id, spec=spec, model=choice.model, state="thinking")

    def known(self) -> set[str]:
        """Every number the Brief's tools gave (the team's own words do not count)."""
        results = [
            text
            for run in self.store.runs(self.brief_id)
            if run["history"]
            for name, text in agents.tool_returns(run["history"])
            if name not in team.TEAM_TOOLS
        ]
        return numbers_guard.known_values(results)

    async def _finish(self, output: Any) -> None:
        if isinstance(output, str):
            marked = numbers_guard.unsourced(output, self.known())
            if marked:
                self.emit(Unsourced(self.brief_id, tuple(marked)))
        for draft in self.store.unchecked(self.brief_id):
            if checker.has_numbers(draft):
                try:
                    await team.check_deliverable(self.lead_ctx, draft.id)
                except ModelRetry:
                    pass  # settled meanwhile

    def _withdraw(self) -> None:
        for card in self.store.pending(self.brief_id):
            self.emit(Data(self.brief_id, "card", card.id, {"status": "withdrawn"}))
        self.store.withdraw_pending(self.brief_id)

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
        except Exception:
            log.exception("brief %s failed", self.brief_id)
            self._withdraw()
            provider = "One"
            if self.lead_run_id is not None:
                provider = self._provider(self.store.run(self.lead_run_id)["choice"])
            self.set_state("failed", copy.fill(copy.AI_FAILED, provider=provider))
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
    ) -> None:
        self.projects = projects
        self.data_dir = Path(data_dir)
        self.connectors = connectors or (lambda: connectors_mod.connectors())
        self.clock = clock
        self.sleep = sleep
        self.mcp = mcp or McpGate()
        self.meaning = meaning
        self.base_url: str | None = None  # the core's own address, for the MCP config
        self._brief_slots = asyncio.Semaphore(max_briefs)
        self._agent_slots = asyncio.Semaphore(max_agents)
        self._briefs: dict[str, _Brief] = {}
        self._outputs: dict[str, Any] = {}
        self._general: Records | None = None
        self.book: CostBook
        self.spending: Spending

    # Life ------------------------------------------------------------------------------------

    def _ready(self) -> None:
        if self._general is None or not self._general.is_open:
            self._general = general.open_engineer_records(self.data_dir)
            self.book = CostBook(self._general)
            self.spending = Spending(self.book, clock=self.clock)

    async def start(self) -> None:
        """Opens the Engineer Records file. Never continues a Brief by itself. A file that does
        not open leaves the app up: each Brief then answers why, in plain words."""
        try:
            self._ready()
        except RecordsError:
            log.warning("The Engineer Records file did not open")

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
    ) -> str:
        """Starts a Brief in the chat (a project id or "general"), under the caps. Raises
        `BriefBusy`, `NoAI` and `RecordsError`."""
        place = self._place(chat_id)
        busy = self.active(chat_id)
        if busy is not None:
            raise BriefBusy(busy)
        sheet = await self.sheet()
        busy = self.active(chat_id)
        if busy is not None:
            raise BriefBusy(busy)
        brief_id = place.store.new_brief(chat_id, text)
        self._launch(
            _Brief(
                self,
                place,
                place.store.brief(brief_id),
                instruction=instruction,
                output_type=output_type,
                sheet=sheet,
            )
        )
        log.info("brief %s started", brief_id)
        return brief_id

    def _launch(self, brief: _Brief) -> None:
        self._briefs[brief.brief_id] = brief
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
        for brief in self._briefs.values():
            if card_id in brief.waiting:
                return list(brief.waiting[card_id][0].options)
        return []

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
            messages.append(
                {
                    "id": question_id(brief_id),
                    "role": "user",
                    "parts": [{"type": "text", "text": brief["text"]}],
                }
            )
            running = self._briefs.get(brief_id)
            if running is not None:
                parts = message_parts(running.log)
            else:
                waiting = brief["status"] in UNFINISHED
                parts = message_parts(
                    _stored_events(place.store, brief, self), with_status=not waiting
                )
            messages.append({"id": reply_id(brief_id), "role": "assistant", "parts": parts})
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


def _stored_events(store: Store, brief: dict, engine: Engine) -> list[Event]:
    """A Brief as events again, from what is stored: the Lead's words, the Coordination Room,
    the cards and their answers, the Reviews, the unsourced marks and the state."""
    brief_id = brief["id"]
    events: list[Event] = []
    runs = store.runs(brief_id)
    lead = next((r for r in runs if r["parent_id"] is None and r["spec"].role == "lead"), None)
    reply = lead_text(_load(lead["history"])) if lead is not None else ""
    if reply:
        events.append(TextDelta(brief_id, reply))
    for m in store.team(brief_id):
        events.append(TeamMessage(brief_id, m["id"], m["sender"], m["recipient"], m["text"]))
    with store.rec.read() as c:
        approvals = c.execute(
            "SELECT card, status, choice FROM approvals WHERE brief_id = ?"
            " ORDER BY asked_at, rowid",
            (brief_id,),
        ).fetchall()
        reviews = c.execute(
            "SELECT r.deliverable_id, r.code, r.comments, r.checker, r.same_provider, r.round"
            " FROM reviews r JOIN deliverable_drafts d ON d.id = r.deliverable_id"
            " WHERE d.brief_id = ? ORDER BY r.at, r.rowid",
            (brief_id,),
        ).fetchall()
    for card_text, status, choice in approvals:
        d = json.loads(card_text)
        card = Card(**{**d, "options": tuple(d["options"])})
        events.append(Asked(brief_id, card))
        if status == "settled":
            events.append(Settled(brief_id, card.id, choice))
        elif status == "withdrawn":
            events.append(Data(brief_id, "card", card.id, {"status": "withdrawn"}))
    for deliverable_id, code, comments, choice, same, round_ in reviews:
        review = Review(
            code=code,
            comments=tuple(json.loads(comments)),
            checker=ModelChoice(**json.loads(choice)),
            same_provider=bool(same),
            round=round_,
        )
        events.append(Reviewed(brief_id, deliverable_id, review))
    if reply and brief["status"] == "done":
        known = numbers_guard.known_values(
            text
            for run in runs
            if run["history"]
            for name, text in agents.tool_returns(run["history"])
            if name not in team.TEAM_TOOLS
        )
        marked = numbers_guard.unsourced(reply, known)
        if marked:
            events.append(Unsourced(brief_id, tuple(marked)))
    events.append(Status(brief_id, brief["status"], brief["step"]))
    return events
