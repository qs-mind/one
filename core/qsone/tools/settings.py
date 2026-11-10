"""settings_set (Phase 1, C10): the Lead changes a setting the engineer asked about, through the
same registry the Settings screen uses (`qsone.settings_registry`), so both change one stored
value. The Lead reads tender documents nobody has vetted, so a change that spends more, sends more
out or weakens a Confidential rule asks the engineer first with a `setting` card; every other
change is made at once. Either way the screens get a `setting` event.

Importing this module registers the tool. No PydanticAI here."""

import json
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from qsone import copy, settings_registry
from qsone.engine.tools import Denied, Tool, ToolContext, register
from qsone.engine.types import Card

KEYS = ", ".join(e.key for e in settings_registry.ENTRIES)


class SettingArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    key: str = Field(min_length=1, max_length=60)
    value: StrictBool | Annotated[str, Field(min_length=1, max_length=40)]


_EXAMPLE = {"key": "caps.month_usd", "value": "50"}

_DOC = f"""Change one of ONE's settings, only when the engineer asks you to.
- key: one of {KEYS}.
- value: true or false for a toggle (confidential_on_device, subscription_stops, usage_stats); \
otherwise text: a choice (ai.models: recommended or own; look.language: ar or en; look.theme: \
system, light or dark), an exact USD amount for caps.*, or a zoom from 0.8 to 1.5.
A change that spends more, sends more out or weakens a Confidential rule asks the engineer \
first. Returns the setting as stored.
Example:
{json.dumps(_EXAMPLE)}"""


def _value(entry: settings_registry.Entry, raw: bool | str) -> object:
    """A toggle's value as a model may write it: true, or the text "true"."""
    if entry.control == "toggle" and isinstance(raw, str) and raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    return raw


def _said(e: settings_registry.Entry, value) -> dict[str, str]:
    """A value in words, for the Lead's card: on or off, a choice's title, an amount in USD."""
    if e.control == "toggle":
        return copy.SET_TOGGLE_ON if value else copy.SET_TOGGLE_OFF
    if e.control == "choice":
        return dict(e.choices)[value]
    if e.control == "money":
        return copy.fill(copy.SET_USD, usd=value)
    return {"en": str(value), "ar": str(value)}


async def _ask(ctx: ToolContext, entry: settings_registry.Entry, before, after) -> None:
    """The `setting` card; "no" raises `Denied`."""
    detail = copy.fill(
        copy.SETTING_ASK,
        agent=ctx.agent.name,
        setting=entry.title,
        now=_said(entry, before),
        asked=_said(entry, after),
    )
    card = Card(uuid4().hex, "setting", entry.title, detail, ("yes", "no"))
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)  # stored before it is shown
    choice = await ctx.host.ask(card)
    try:
        ctx.store.settle(card.id, choice)
    except LookupError:
        pass  # the host saved the answer itself
    if choice != "yes":
        raise Denied("settings_set")


async def _set(ctx: ToolContext, args: SettingArgs) -> str:
    entry = settings_registry.entry(args.key)
    value = settings_registry.parse(entry, _value(entry, args.value))
    before = entry.read()
    if settings_registry.asks_first(entry, before, value):
        await _ask(ctx, entry, before, value)
    stored = settings_registry.save(entry, value)
    return json.dumps({"key": stored.key, "value": stored.value})


register(
    Tool(
        name="settings_set",
        description=_DOC,
        args=SettingArgs,
        risk="write",
        run=_set,
        activity=lambda _: copy.TOOL_WORDS["settings_set"],
        writes=True,
        example=_EXAMPLE,
        roles=frozenset({"lead"}),
        lead_only=True,
        group="settings",
    )
)
