"""Test fakes for the agent engine. Not product code: no test calls a real AI.

- `scripted(*steps)`: a PydanticAI `FunctionModel` that plays a list of steps.
- `FakeHost`: a `TeamHost` that records events and answers cards from a dict.
- `SAMPLE_SHEET`: a Model Data Sheet of sample cards, with sample prices.
- `fake_claude_command()` and `read_fake_log()`: the stand-in `claude` in `fakes/fake_claude.py`.
- `FakeClock` and `FakeSleep`: behind the `fake_clock` and `fake_sleep` fixtures.
"""

import asyncio
import contextvars
import inspect
import json
import sys
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.usage import RequestUsage

from qsone.engine.types import (
    AgentSpec,
    Card,
    CheckPacket,
    Event,
    ModelCard,
    ModelChoice,
    Review,
    TeamMessage,
)

# Clock and sleep ------------------------------------------------------------------------------


class FakeClock:
    """Call it for the time now: an aware UTC `datetime` that moves only when told to."""

    def __init__(self, start: datetime = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeSleep:
    """Stands in for `asyncio.sleep`: records each delay, moves the clock, returns at once."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.clock = clock
        self.delays: list[float] = []

    async def __call__(self, delay: float, result=None):
        self.delays.append(delay)
        if self.clock is not None:
            self.clock.advance(delay)
        await asyncio.sleep(0)  # still lets other tasks run, as a real sleep would
        return result


# Scripted models ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One model response: text, or one or more tool calls. `usage` is (input, output) tokens;
    without it, PydanticAI's own estimate is used."""

    parts: tuple[TextPart | ToolCallPart, ...]
    usage: tuple[int, int] | None = None


def text(content: str, *, usage: tuple[int, int] | None = None) -> Step:
    return Step((TextPart(content),), usage)


def call(
    tool: str,
    args: dict | None = None,
    *,
    id: str | None = None,
    usage: tuple[int, int] | None = None,
) -> Step:
    """One tool call. Join several into one response with `calls`."""
    return Step(
        (ToolCallPart(tool, args or {}, tool_call_id=id or f"call-{uuid4().hex[:8]}"),), usage
    )


def calls(*steps: Step, usage: tuple[int, int] | None = None) -> Step:
    """Several tool calls in one response (the model asks for them at once)."""
    return Step(tuple(p for s in steps for p in s.parts), usage)


# A callable step gets (messages, info) and returns a Step, a str or a ModelResponse; it may be
# async, to wait on an event or to block until cancelled.
StepLike = Step | Callable


def _usage(tokens: tuple[int, int] | None) -> RequestUsage:
    """No tokens gives an empty usage, which `FunctionModel` replaces with its own estimate."""
    if tokens is None:
        return RequestUsage()
    return RequestUsage(input_tokens=tokens[0], output_tokens=tokens[1])


_stream_usage: contextvars.ContextVar[tuple[int, int] | None] = contextvars.ContextVar(
    "stream_usage", default=None
)


class Scripted(FunctionModel):
    """Plays `steps` in order, one per model request, streamed or not.

    `calls` counts requests, `seen` holds the messages of each request, and `cancelled` turns
    True when a request is cancelled while it runs. It fails plainly when it runs out of steps."""

    def __init__(self, steps: list[StepLike], *, model_name: str = "scripted") -> None:
        self.steps = list(steps)
        self.calls = 0
        self.seen: list[list] = []
        self.cancelled = False
        super().__init__(self._respond, stream_function=self._stream, model_name=model_name)

    async def _next(self, messages: list, info: AgentInfo) -> Step:
        self.calls += 1
        self.seen.append(list(messages))
        if not self.steps:
            raise AssertionError(f"the scripted model has no step for request {self.calls}")
        step = self.steps.pop(0)
        if isinstance(step, Step):
            return step
        try:
            out = step(messages, info)
            if inspect.isawaitable(out):
                out = await out
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if isinstance(out, str):
            return text(out)
        if isinstance(out, ModelResponse):
            return Step(tuple(out.parts))
        assert isinstance(out, Step), out
        return out

    async def _respond(self, messages: list, info: AgentInfo) -> ModelResponse:
        step = await self._next(messages, info)
        usage = _usage(step.usage)
        return ModelResponse(parts=list(step.parts), usage=usage)

    async def _stream(self, messages: list, info: AgentInfo):
        step = await self._next(messages, info)
        _stream_usage.set(step.usage)
        texts = [p for p in step.parts if isinstance(p, TextPart)]
        tool_calls = [p for p in step.parts if isinstance(p, ToolCallPart)]
        assert not (texts and tool_calls), "a streamed step is text or tool calls, not both"
        try:
            for part in texts:
                yield part.content
            if tool_calls:
                yield {
                    i: DeltaToolCall(p.tool_name, p.args_as_json_str(), tool_call_id=p.tool_call_id)
                    for i, p in enumerate(tool_calls)
                }
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        async with super().request_stream(
            messages, model_settings, model_request_parameters, run_context
        ) as response:
            # The first chunk is read before this point, so the step (and its usage) is known.
            usage = _stream_usage.get()
            if usage is not None:
                events = response._get_event_iterator

                async def with_usage():
                    async for event in events():
                        yield event
                    response._usage = _usage(usage)

                response._get_event_iterator = with_usage
            yield response


def scripted(*steps: StepLike, model_name: str = "scripted") -> Scripted:
    return Scripted(list(steps), model_name=model_name)


# FakeHost -------------------------------------------------------------------------------------


@dataclass
class FakeHost:
    """A `TeamHost` for tests.

    `answers` maps a card id or kind to a choice; a card with no answer waits until
    `settle(card_id, choice)`. `specialist` and `checker` are async callables standing in for
    `run_specialist` and `run_checker`."""

    brief_id: str = "brief-sample"
    answers: dict[str, str] = field(default_factory=dict)
    specialist: Callable | None = None
    checker: Callable | None = None
    events: list[Event] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    posted: list[TeamMessage] = field(default_factory=list)
    _waiting: dict[str, asyncio.Future] = field(default_factory=dict)

    def emit(self, event: Event) -> None:
        self.events.append(event)

    async def ask(self, card: Card) -> str:
        self.cards.append(card)
        for key in (card.id, card.kind):
            if key in self.answers:
                return self.answers[key]
        future = self._waiting[card.id] = asyncio.get_running_loop().create_future()
        return await future

    def settle(self, card_id: str, choice: str) -> None:
        self._waiting.pop(card_id).set_result(choice)

    async def run_specialist(self, spec: AgentSpec, task: str, kit: dict) -> str:
        assert self.specialist is not None, "FakeHost.specialist is not set"
        return await self.specialist(spec, task, kit)

    async def run_checker(self, packet: CheckPacket, maker: ModelChoice) -> Review:
        assert self.checker is not None, "FakeHost.checker is not set"
        return await self.checker(packet, maker)

    def post(self, message: TeamMessage) -> None:
        self.posted.append(message)
        self.emit(message)


# The sample Model Data Sheet -----------------------------------------------------------------

SAMPLE_PRICE = "sample price for tests, not real"


def _card(connector: str, model: str, provider: str, price_in: str, price_out: str) -> ModelCard:
    return ModelCard(
        choice=ModelChoice(connector, model),
        name=f"{model} (sample)",
        provider=provider,
        images=True,
        tools=True,
        context=200_000,
        price_in=Decimal(price_in),
        price_out=Decimal(price_out),
        price_source=SAMPLE_PRICE,
    )


OPUS = _card("anthropic", "claude-opus-5-5", "anthropic", "15", "75")
SONNET = _card("anthropic", "claude-sonnet-5-5", "anthropic", "3", "15")
HAIKU = _card("anthropic", "claude-haiku-5-5", "anthropic", "1", "5")
DEEPSEEK = _card("standard:deepseek", "deepseek-chat", "deepseek", "0.28", "0.42")
SAMPLE_SHEET = [OPUS, SONNET, HAIKU, DEEPSEEK]


# The fake `claude` ---------------------------------------------------------------------------

FAKE_CLAUDE = Path(__file__).parent / "fakes" / "fake_claude.py"


def fake_claude_command(
    *,
    script: list | dict | Path | None = None,
    log: Path | None = None,
    drop: tuple[str, ...] = (),
    signed_out: bool = False,
) -> list[str]:
    """The argv prefix that runs the fake `claude` (Task 5's `command_prefix`).

    The settings travel as `--fake-*` arguments, because One clears the environment it gives
    Claude Code; the fake strips them before it parses or logs its argv."""
    command = [sys.executable, str(FAKE_CLAUDE)]
    if script is not None:
        value = str(script) if isinstance(script, Path) else json.dumps(script, ensure_ascii=False)
        command.append(f"--fake-script={value}")
    if log is not None:
        command.append(f"--fake-log={log}")
    if drop:
        command.append(f"--fake-drop={','.join(drop)}")
    if signed_out:
        command.append("--fake-signed-out")
    return command


def read_fake_log(path: Path) -> list[dict]:
    """One dict per `-p` run, oldest first: argv, env_names, cwd, files (the text of the
    files named by --mcp-config and --system-prompt-file), stdin (each line as JSON) and ended
    ("done", "interrupted", "terminated", "dropped", or None while it runs)."""
    runs: dict[int, dict] = {}  # by run number: runs started at once may log out of order
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["kind"] == "start":
            runs[record["run"]["n"]] = {**record["run"], "stdin": [], "ended": None}
        elif record["kind"] == "stdin":
            runs[record["n"]]["stdin"].append(record["line"])
        elif record["kind"] == "end":
            runs[record["n"]]["ended"] = record["how"]
    return [runs[n] for n in sorted(runs)]
