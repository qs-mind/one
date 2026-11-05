"""The one approval gate, in the tool layer, for every connector (decision 12).

- `read` and `write` tools run without asking.
- `outside` tools always ask: they send or delete something outside One.
- `online` tools ask once the Brief has read file, web or email text, unless the engineer
  allowed that tool for this Brief.
- A tool whose risk depends on its arguments (`Tool.risk_for`, a Connector's tool) is gated by
  the risk of this call.

The card is stored as pending before it is shown, so a restart can withdraw it and the redone
call asks again. `host.ask` shows it and waits; the gate then saves the answer."""

from uuid import uuid4

from pydantic import BaseModel

from qsone import copy
from qsone.engine.tools import Denied, Tool, ToolContext, risk_of
from qsone.engine.types import Card, Risk

_OPTIONS = {"outside": ("yes", "no"), "online": ("yes", "brief", "no")}


def _needs_asking(tool: Tool, risk: Risk, ctx: ToolContext) -> bool:
    if risk == "outside":
        return True
    if risk != "online":
        return False
    brief = ctx.store.brief(ctx.brief_id)
    return bool(brief["read_untrusted"]) and tool.name not in brief["allowed"]


async def guard(tool: Tool, args: BaseModel, ctx: ToolContext) -> None:
    """Returns when the call may run; raises `Denied` when the engineer said no."""
    kind = risk_of(tool, args)
    if not _needs_asking(tool, kind, ctx):
        return
    action = tool.activity(args)
    text = copy.ASK_OUTSIDE if kind == "outside" else copy.ASK_ONLINE
    card = Card(
        id=uuid4().hex,
        kind=kind,
        title=action,
        detail=copy.fill(text, agent=ctx.agent.name, action=action),
        options=_OPTIONS[kind],
    )
    ctx.store.add_approval(ctx.brief_id, card, run_id=ctx.run_id)
    choice = await ctx.host.ask(card)
    try:
        ctx.store.settle(card.id, choice)
    except LookupError:
        pass  # the host saved the answer itself
    if choice == "no":
        raise Denied(tool.name)
    if choice == "brief":
        ctx.store.allow(ctx.brief_id, tool.name)
