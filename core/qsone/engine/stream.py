"""A Brief's events as the AI SDK UI message stream (sdk_version 6, `ai` 6.0.x), and as the parts
of a stored UI message.

The Lead's words are one text part. One's own events are `data-*` parts with a stable id, so the
screen updates each in place: `data-progress` (id: the agent run), `data-team` (the message),
`data-card` (the card; status pending, settled with the choice and when, or withdrawn; `hold`
names the answers that need press-and-hold), `data-cost` (the scope), `data-review` (the
Deliverable), `data-unsourced` (the Brief), `data-status` (the Brief), and any `Data` event as
`data-<name>`, such as `data-worklog` (the Brief: `engine.worklog`). A failed Brief also ends
with an `error` chunk whose text is its plain {en, ar} words as JSON, as the screen reads it,
with the `fix` the screen can offer (`copy.fix_of`); a card carries its detail's `fix` too.

No PydanticAI here: the chunks are written as the protocol defines them."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterable

from qsone import copy
from qsone.engine.types import (
    Asked,
    CostNotice,
    Data,
    Event,
    Progress,
    Reviewed,
    Settled,
    Status,
    TeamMessage,
    TextDelta,
    Unsourced,
    read_answer,
)

HEADERS = {"x-vercel-ai-ui-message-stream": "v1", "cache-control": "no-cache"}
# A Brief can be quiet for minutes (a long tool, a card waiting for the engineer). An SSE comment
# this often keeps the connection from being dropped as idle by the window or a proxy on the way;
# the screen's parser skips comments.
HEARTBEAT_S = 15.0
HEARTBEAT = ": keep-alive\n\n"
_END = object()


# The answers that spend money or cannot be taken back, by card kind: the screen asks for them by
# press-and-hold, never a single click. "paid": a tool's own cost, a Brief Budget, going on at a
# Spending Cap or with a model of unknown price, a costlier model. "irreversible": an outside tool
# sends or deletes something outside ONE. Every other answer is one click.
HOLD: dict[str, tuple[str, tuple[str, ...]]] = {
    "outside": ("irreversible", ("yes",)),
    "cost": ("paid", ("yes",)),
    "budget": ("paid", ("yes",)),
    "cap": ("paid", ("continue", "yes")),
    "fallback": ("paid", ("yes",)),
}


def _card(card) -> dict:
    found = {
        "kind": card.kind,
        "title": card.title,
        "detail": card.detail,
        "options": list(card.options),
    }
    if card.kind in HOLD:
        why, options = HOLD[card.kind]
        held = [o for o in options if o in card.options]
        if held:
            found["hold"] = {"why": why, "options": held}
    fix = copy.fix_of(card.detail)
    if fix is not None:
        found["fix"] = fix
    if card.payload is not None:
        found["payload"] = card.payload
    return found


def _settled(card, value: str) -> dict:
    """A settled card's answer: the choice, and for a card with a payload its answers and
    ticked rows too (Plan 5)."""
    if card is None or card.payload is None:
        return {"choice": value}
    return read_answer(card, value)


class _Parts:
    """Turns events into data parts; remembers each card, so a settled one is sent whole."""

    def __init__(self) -> None:
        self.cards: dict[str, dict] = {}
        self.asked: dict = {}  # card id -> Card, to read a settled answer

    def data(self, event: Event) -> tuple[str, str, dict] | None:
        """(part type, id, data) for a data event; None for text."""
        if isinstance(event, Progress):
            data = {"agent": event.agent, "text": event.text}
            if event.lang is not None:
                data["lang"] = event.lang  # the Brief's language: the screen shows it in that one
            return "data-progress", event.run_id, data
        if isinstance(event, TeamMessage):
            data = {"sender": event.sender, "recipient": event.recipient, "text": event.text}
            return "data-team", event.id, data
        if isinstance(event, Asked):
            self.asked[event.card.id] = event.card
            self.cards[event.card.id] = _card(event.card)
            return "data-card", event.card.id, self.cards[event.card.id] | {"status": "pending"}
        if isinstance(event, Settled):
            card = self.cards.get(event.card_id, {})
            answer = _settled(self.asked.get(event.card_id), event.choice)
            data = card | {"status": "settled"} | answer
            if event.at is not None:
                data["settled_at"] = event.at
            return "data-card", event.card_id, data
        if isinstance(event, CostNotice):
            data = {
                "level": event.level,
                "scope": event.scope,
                "spent": event.spent,
                "cap": event.cap,
                "equivalent": event.equivalent,
                "text": event.text,
            }
            return "data-cost", event.scope, data
        if isinstance(event, Reviewed):
            review = event.review
            data = {
                "code": review.code,
                "comments": [dict(c) for c in review.comments],
                "same_provider": review.same_provider,
                "round": review.round,
            }
            return "data-review", event.deliverable_id, data
        if isinstance(event, Unsourced):
            return "data-unsourced", event.brief_id, {"values": list(event.values)}
        if isinstance(event, Status):
            data = {"state": event.state, "step": event.step}
            fix = copy.fix_of(event.step) if event.state == "failed" else None
            # a failed Brief keeps its line and its fix in the reply, after later messages too
            return "data-status", event.brief_id, data if fix is None else data | {"fix": fix}
        if isinstance(event, Data):
            if event.name == "card" and event.id in self.cards:  # e.g. withdrawn
                return "data-card", event.id, self.cards[event.id] | event.data
            return f"data-{event.name}", event.id, event.data
        return None


def _sse(chunk: dict | str) -> str:
    body = (
        chunk
        if isinstance(chunk, str)
        else json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
    )
    return f"data: {body}\n\n"


def error_chunk(text: dict) -> str:
    """The `error` chunk: `text` as JSON, with its `fix` when the screen can offer one."""
    fix = copy.fix_of(text)
    said = text if fix is None else text | {"fix": fix}
    return _sse({"type": "error", "errorText": json.dumps(said, ensure_ascii=False)})


def text_id(message_id: str) -> str:
    return f"{message_id}-text"


async def _beating(events: AsyncIterator[Event]) -> AsyncIterator[Event | None]:
    """`events`, with a None after each HEARTBEAT_S without one."""
    queue: asyncio.Queue = asyncio.Queue()

    async def pump() -> None:
        try:
            async for event in events:
                queue.put_nowait(event)
        except Exception as error:  # noqa: BLE001 - raised again by the reader below
            queue.put_nowait(error)
        queue.put_nowait(_END)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), HEARTBEAT_S)
            except TimeoutError:
                yield None
                continue
            if item is _END:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        task.cancel()


async def ui_stream(events: AsyncIterator[Event], *, message_id: str) -> AsyncIterator[str]:
    """SSE lines, from `start` (with `message_id`, the stored id of the Brief's reply) to
    `data: [DONE]`, with a heartbeat comment while the Brief is quiet. Ends when `events` ends."""
    parts = _Parts()
    yield _sse({"type": "start", "messageId": message_id})
    yield _sse({"type": "start-step"})
    text_open = False
    failed: dict | None = None
    async for event in _beating(events):
        if event is None:
            yield HEARTBEAT
            continue
        if isinstance(event, TextDelta):
            if not text_open:
                text_open = True
                yield _sse({"type": "text-start", "id": text_id(message_id)})
            yield _sse({"type": "text-delta", "id": text_id(message_id), "delta": event.text})
            continue
        found = parts.data(event)
        if found is None:
            continue
        kind, part_id, data = found
        yield _sse({"type": kind, "id": part_id, "data": data})
        if isinstance(event, Status) and event.state == "failed":
            failed = event.step
    if text_open:
        yield _sse({"type": "text-end", "id": text_id(message_id)})
    if failed is not None:
        yield error_chunk(failed)
    yield _sse({"type": "finish-step"})
    yield _sse({"type": "finish"})
    yield _sse("[DONE]")


def message_parts(events: Iterable[Event], *, with_status: bool = True) -> list[dict]:
    """The parts of the UI message that `events` stream, each once, at its first place: one text
    part where the words began, and each data part with its latest data. `with_status=False`
    leaves out the Brief's status, for a Brief that waits for Continue (the screen must not
    steer it)."""
    parts = _Parts()
    found: list[dict] = []
    index: dict[tuple[str, str], int] = {}
    text: list[str] = []
    text_at = 0  # where the text part goes: before the data parts that came after the first words
    for event in events:
        if isinstance(event, TextDelta):
            if not text:
                text_at = len(found)
            text.append(event.text)
            continue
        data = parts.data(event)
        if data is None:
            continue
        kind, part_id, value = data
        if kind == "data-status" and not with_status:
            continue
        key = (kind, part_id)
        if key in index:
            found[index[key]]["data"] = value
        else:
            index[key] = len(found)
            found.append({"type": kind, "id": part_id, "data": value})
    if text:
        found.insert(text_at, {"type": "text", "text": "".join(text), "state": "done"})
    return found
