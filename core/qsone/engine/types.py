"""Types shared by every part of the engine, and the events it sends to the screen.

No PydanticAI import here: tools, team tools and the stream build on these alone.
Money is `Decimal`, and goes out as text.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

Text = dict[str, str]  # {"en": ..., "ar": ...}
Role = Literal["lead", "checker", "specialist", "quick"]
# How hard the Lead QS thinks, as the engineer picks it in the message box; sent as PydanticAI's
# unified `thinking` setting (Claude Code: `--effort`). Only the levels a model accepts are offered.
Effort = Literal["low", "medium", "high"]
EFFORTS: tuple[Effort, ...] = ("low", "medium", "high")
Risk = Literal["read", "write", "online", "outside"]
BriefState = Literal[
    "queued",
    "running",
    "waiting_engineer",
    "waiting_connection",
    "paused_cap",
    "stopped",
    "done",
    "failed",
]


def brief_language(text: str) -> Literal["ar", "en"]:
    """The Brief's language, the engineer's: English when its message has more Latin letters
    than Arabic ones, else Arabic (the default). The Brief's Progress words follow it."""
    latin = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin > len(re.findall("[\u0600-\u06ff]", text)) else "ar"


# Words only Egyptian Arabic uses (formal Arabic says هذا، ماذا، كيف، أين، لماذا، ليس، الآن…),
# and its "do it for me" imperatives (قولي، احسبلي، قارنلي). One is enough to answer in Egyptian.
_EGYPTIAN = re.compile(
    r"(?<![\u0600-\u06ff])(?:\u062f\u0647|\u062f\u064a|\u062f\u0648\u0644|\u0625\u064a\u0647|\u0627\u064a\u0647|\u0625\u0632\u0627\u064a|\u0627\u0632\u0627\u064a|\u0639\u0627\u064a\u0632|\u0639\u0627\u064a\u0632\u0629|\u0639\u0627\u0648\u0632|\u0639\u0627\u0648\u0632\u0629|\u0641\u064a\u0646|\u0625\u0645\u062a\u0649|\u0627\u0645\u062a\u0649|"
    r"\u0644\u064a\u0647|\u0645\u0634|\u0643\u062f\u0647|\u0643\u062f\u0627|\u062f\u0644\u0648\u0642\u062a\u064a|\u0627\u0644\u0646\u0647\u0627\u0631\u062f\u0647|\u0627\u0644\u0646\u0647\u0627\u0631\u062f\u0647|\u0628\u062a\u0627\u0639|\u0628\u062a\u0627\u0639\u0629|\u0628\u062a\u0627\u0639\u062a|\u0644\u0633\u0647|\u0628\u0631\u0636\u0647|\u0628\u0631\u062f\u0648|\u0627\u0644\u0644\u064a|"
    r"(?:\u0642\u0648\u0644|\u0642\u0627\u0631\u0646|\u0627\u062d\u0633\u0628|\u0647\u0627\u062a|\u0627\u0639\u0645\u0644|\u0627\u0628\u0639\u062a|\u0648\u0631\u064a|\u0648\u0631\u0651\u064a|\u0637\u0644\u0639|\u0637\u0644\u0651\u0639|\u062c\u064a\u0628|\u0627\u0643\u062a\u0628|\u0634\u0648\u0641)(?:\u0644)?\u0644\u064a)(?![\u0600-\u06ff])"
)


def reply_line(text: str) -> str:
    """The line that tells the Lead which language and register to answer the engineer's
    message in: the language most of it is written in (a few words of the other do not change
    it), and Egyptian Arabic when the engineer writes Egyptian."""
    if brief_language(text) == "en":
        return (
            "The engineer wrote in English: reply in English, even if the message has a few "
            "Arabic words."
        )
    if _EGYPTIAN.search(text):
        return (
            "The engineer wrote in Egyptian Arabic: reply in plain Egyptian Arabic, as they "
            "write, not formal Arabic."
        )
    return "The engineer wrote in Arabic: reply in Arabic."


@dataclass(frozen=True)
class ModelChoice:
    connector: str  # "anthropic" | "standard:<id>" | "claude-code"
    model: str  # the provider's model id


@dataclass(frozen=True)
class ModelCard:
    """One line of the Model Data Sheet."""

    choice: ModelChoice
    name: str
    provider: str  # decides a Same-provider check
    images: bool
    tools: bool
    context: int | None
    price_in: Decimal | None  # USD per million tokens
    price_out: Decimal | None
    price_source: str | None  # "genai-prices 0.2.1: https://…" | "engineer, 2026-11-05"
    on_device: bool = False
    subscription: bool = False
    efforts: tuple[Effort, ...] = ()  # the effort levels it accepts; none: no effort to pick
    effort_default: Effort | None = None  # the provider's own level when none is sent, if known


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: Text
    role: Role
    instructions: str
    tools: tuple[str, ...]
    tier: Role  # picks the model: that role's choice in Settings
    desk: str | None = None  # slug of a saved Desk, or None (Temporary Desk)


@dataclass(frozen=True)
class DeliverableDraft:
    id: str
    kind: Literal["table", "document", "answer"]
    title: str
    body: str  # Markdown
    rows: tuple[dict, ...] = ()  # each numeric cell is {"number_id": …} or {"calc_id": …}
    sources: tuple[str, ...] = ()  # Source Ledger source ids
    replaces: str | None = None
    off_desk: bool = False


@dataclass(frozen=True)
class CheckPacket:
    """Everything the blind Checking QS sees, and nothing else."""

    brief_text: str
    deliverable: DeliverableDraft
    numbers: tuple[dict, ...]
    formulas: tuple[dict, ...]
    sources: tuple[dict, ...]
    unsourced: tuple[str, ...]
    previous_comments: tuple[dict, ...]
    # Priced BOQ rows whose item is not in the client's imported BOQ, found by code (not AI):
    # {"row", "code", "description"}; One puts a comment on each for the engineer.
    not_in_client_boq: tuple[dict, ...] = ()
    # ONE's own checks (engine.truth, code not AI): how much of the client's BOQ the Deliverable
    # covers in the divisions it touches, {"client_items", "in_deliverable", "missing"}, or None;
    # and each file-sourced number looked for at its place, {"number_id", "value", "where",
    # "found", "there"}. The Checking QS cannot give Code A over either.
    coverage: dict | None = None
    citations: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Review:
    code: Literal["A", "B", "C"]
    comments: tuple[dict, ...]  # {"about": str, "text": str}
    checker: ModelChoice
    same_provider: bool
    round: int
    checked: tuple[str, ...] = ()  # what the Checking QS says it checked, in its own words


CardKind = Literal[
    "outside",
    "online",
    "cap",
    "price",
    "budget",
    "fallback",
    "desk",
    "disagreement",
    "question",  # Plan 5: the agent asks the engineer (ask_engineer, what to keep)
    "keep",  # Plan 5: keep this for every project (Engineer Records)
    "rows",  # Plan 5: tick the rows to keep (prices)
    "cost",  # Plan 5: a tool's own cost asked first (scanned pages read by the AI)
    "connector",  # Plan 5: add an MCP Connector
]


@dataclass(frozen=True)
class Card:
    """Anything the engineer must answer.

    `payload`, when given, is what the card shows beyond its words, and what its answer fills:
    - `questions`: [{"id", "text", "options"?: [str], "free_text"?: bool}]; each needs an answer:
      one of its options, or any text when it has no options or takes free text;
    - `columns` [{"key", "label": Text}] and `rows` [{key: str}], a table; with `tick` true the
      engineer ticks the rows to take.
    A card with a payload settles as JSON text (`answer_value`)."""

    id: str
    kind: CardKind
    title: Text
    detail: Text
    options: tuple[str, ...]  # e.g. ("yes", "brief", "no")
    payload: dict | None = None


class BadAnswer(ValueError):
    """The answers do not fit the card's payload; `field` is "answers" or "rows_ok"."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


REFUSE = "no"  # the choice that takes nothing: its answers and ticked rows are dropped
MAX_ANSWER = 4000  # characters in one written answer


def _answers(card: Card, answers: dict) -> dict[str, str]:
    questions = {q["id"]: q for q in (card.payload or {}).get("questions") or ()}
    if set(answers) - set(questions) or set(questions) - set(answers):
        raise BadAnswer("answers")
    found = {}
    for qid, question in questions.items():
        answer = answers[qid]
        if not isinstance(answer, str) or not answer.strip() or len(answer) > MAX_ANSWER:
            raise BadAnswer("answers")
        options = question.get("options") or ()
        if options and not question.get("free_text") and answer not in options:
            raise BadAnswer("answers")
        found[qid] = answer.strip()
    return found


def _rows_ok(card: Card, rows_ok: list) -> list[int]:
    payload = card.payload or {}
    count = len(payload.get("rows") or ()) if payload.get("tick") else 0
    picked = [r for r in rows_ok if isinstance(r, int) and not isinstance(r, bool)]
    if len(picked) != len(rows_ok) or len(set(picked)) != len(picked):
        raise BadAnswer("rows_ok")
    if any(not 0 <= r < count for r in picked):
        raise BadAnswer("rows_ok")
    return sorted(picked)


def answer_value(
    card: Card, choice: str, *, answers: dict | None = None, rows_ok: list | None = None
) -> str:
    """What the card settles with. A card without a payload: the choice itself. With one: JSON
    text {"choice", "answers", "rows_ok"}, where every question has its answer and each ticked
    row exists; "no" takes nothing. Raises `ValueError` for a choice that is not one of its
    options, and `BadAnswer` for answers that do not fit."""
    if choice not in card.options:
        raise ValueError(choice)
    if card.payload is None:
        return choice
    taken = choice != REFUSE
    value = {
        "choice": choice,
        "answers": _answers(card, answers or {}) if taken else {},
        "rows_ok": _rows_ok(card, rows_ok or []) if taken else [],
    }
    return json.dumps(value, ensure_ascii=False)


def read_answer(card: Card, value: str) -> dict:
    """{"choice", "answers", "rows_ok"} from a settled value. A payload card settled with a bare
    choice (by a test host, or before its answers were asked) has no answers and no rows."""
    if card.payload is not None:
        try:
            found = json.loads(value)
        except ValueError:
            found = None
        if isinstance(found, dict) and isinstance(found.get("choice"), str):
            return {
                "choice": found["choice"],
                "answers": dict(found.get("answers") or {}),
                "rows_ok": list(found.get("rows_ok") or []),
            }
    return {"choice": value, "answers": {}, "rows_ok": []}


def choice_of(card: Card, value: str) -> str:
    """The option a settled value chose."""
    return read_answer(card, value)["choice"]


# Events from the engine to the stream. Each has the id of its Brief.


@dataclass(frozen=True)
class TextDelta:
    brief_id: str
    text: str


@dataclass(frozen=True)
class Progress:
    brief_id: str
    run_id: str
    agent: Text
    text: Text
    focus: dict | None = None  # the canvas frame the agent now works on (Plan 7), when known
    lang: str | None = None  # the Brief's language; the Brief sets it as it sends the event
    tool: bool = False  # a tool call: a step of its own, open until the agent's tools return
    at: str | None = None  # when it began (ISO 8601 UTC); the Brief sets it as it sends the event


@dataclass(frozen=True)
class TeamMessage:
    brief_id: str
    id: str
    sender: Text
    recipient: Text
    text: str


@dataclass(frozen=True)
class Asked:
    brief_id: str
    card: Card


@dataclass(frozen=True)
class Settled:
    brief_id: str
    card_id: str
    choice: str
    at: str | None = None  # when the engineer answered (ISO 8601), for the card's one-line trace


@dataclass(frozen=True)
class CostNotice:
    brief_id: str
    level: Literal["info", "paused", "stopped"]
    scope: Literal["brief", "day", "month"]
    spent: str
    cap: str
    equivalent: bool
    text: Text


@dataclass(frozen=True)
class Reviewed:
    brief_id: str
    deliverable_id: str
    review: Review


@dataclass(frozen=True)
class Unsourced:
    brief_id: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Status:
    brief_id: str
    state: BriefState
    step: Text | None


@dataclass(frozen=True)
class Data:
    """Becomes a `data-<name>` part (Plans 6 and 7)."""

    brief_id: str
    name: str
    id: str
    data: dict


Event = (
    TextDelta
    | Progress
    | TeamMessage
    | Asked
    | Settled
    | CostNotice
    | Reviewed
    | Unsourced
    | Status
    | Data
)


@runtime_checkable
class TeamHost(Protocol):
    """What tools and team tools may ask of their Brief. The Brief Runner implements it."""

    brief_id: str

    def emit(self, event: Event) -> None: ...

    async def ask(self, card: Card) -> str:
        """Waits for the engineer's choice, one of `card.options`."""
        ...

    async def run_specialist(self, spec: AgentSpec, task: str, kit: dict) -> str: ...

    async def run_checker(self, packet: CheckPacket, maker: ModelChoice) -> Review: ...

    def post(self, message: TeamMessage) -> None:
        """Shows the message in the Coordination Room and puts it in its recipient's inbox."""
        ...
