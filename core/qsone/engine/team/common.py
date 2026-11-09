"""What every team tool shares: the tools' names and limits, the Brief Runner's `TeamSetup`, and
the small helpers (JSON text, strict arguments, a card to the engineer, {en, ar} paragraphs)."""

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from qsone.engine.tools import ToolContext
from qsone.engine.types import Card, ModelCard, ModelChoice, Role, Text

TEAM_TOOLS: tuple[str, ...] = (
    "plan_brief",
    "build_specialist",
    "delegate",
    "send_message",
    "make_deliverable",
    "submit_for_check",
    "save_desk",
    "use_desk",
)
SPECIALIST_TEAM_TOOLS = ("send_message", "make_deliverable")
MAX_SPECIALISTS = 6
PLANNED = "team:plan_brief"  # the brief_writes key that says the Brief has a plan
READY = "ready"  # the status of a specialist's run before its first task


@dataclass(frozen=True)
class TeamSetup:
    """Given by the Brief Runner as `host.setup`."""

    sheet: tuple[ModelCard, ...]  # the Model Data Sheet, priced
    roles: dict[Role, ModelChoice]  # `roles.chosen(sheet)`
    measured: tuple[int, int, int] | None = None  # `CostBook.tokens_per_request(project)`
    # the same at the Lead QS's effort in this Brief, for the Lead's lines of the Brief Budget
    lead_measured: tuple[int, int, int] | None | Literal["same"] = "same"


def _setup(ctx: ToolContext) -> TeamSetup:
    setup = getattr(ctx.host, "setup", None)
    if not isinstance(setup, TeamSetup):
        raise RuntimeError("the Brief Runner's host must give the team tools `setup`")
    return setup


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


async def _ask(ctx: ToolContext, card: Card) -> str:
    """Stores the card as pending, shows it and waits, then saves the answer (as the gate does)."""
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    choice = await ctx.host.ask(card)
    try:
        ctx.store.settle(card.id, choice)
    except LookupError:
        pass  # the host saved the answer itself
    return choice


def _join(*pieces: Text | str) -> Text:
    """{en, ar} pieces, and text that is the same in both, as paragraphs."""
    return {
        lang: "\n\n".join(p if isinstance(p, str) else p[lang] for p in pieces if p)
        for lang in ("en", "ar")
    }
