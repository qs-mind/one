"""Types shared by every part of the engine, and the events it sends to the screen.

No PydanticAI import here: tools, team tools and the stream build on these alone.
Money is `Decimal`, and goes out as text.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

Text = dict[str, str]  # {"en": ..., "ar": ...}
Role = Literal["lead", "checker", "specialist", "quick"]
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


@dataclass(frozen=True)
class Review:
    code: Literal["A", "B", "C"]
    comments: tuple[dict, ...]  # {"about": str, "text": str}
    checker: ModelChoice
    same_provider: bool
    round: int


@dataclass(frozen=True)
class Card:
    """Anything the engineer must answer."""

    id: str
    kind: Literal["outside", "online", "cap", "budget", "fallback", "desk", "disagreement"]
    title: Text
    detail: Text
    options: tuple[str, ...]  # e.g. ("yes", "brief", "no")


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
