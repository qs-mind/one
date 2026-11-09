"""The team as stored: a Brief's specialists and their runs, a Deliverable's maker, and the
numbers that have a source in the Brief."""

from dataclasses import replace

from qsone.engine import agents, checker, numbers_guard
from qsone.engine.store import Store
from qsone.engine.tools import ModelRetry, ToolContext
from qsone.engine.types import AgentSpec, CheckPacket, DeliverableDraft

from .common import TEAM_TOOLS

# The team as stored ---------------------------------------------------------------------------


def specialists(store: Store, brief_id: str) -> list[AgentSpec]:
    """The Brief's specialists, in the order they were built."""
    return [r["spec"] for r in store.runs(brief_id) if r["spec"].role == "specialist"]


def specialist_run(store: Store, brief_id: str, specialist_id: str) -> str:
    """The id of the agent run that holds the specialist. Raises `LookupError`."""
    for r in store.runs(brief_id):
        if r["spec"].role == "specialist" and r["spec"].id == specialist_id:
            return r["id"]
    raise LookupError(specialist_id)


def _specialist(ctx: ToolContext, specialist_id: str, tool: str) -> AgentSpec:
    team = specialists(ctx.store, ctx.brief_id)
    for spec in team:
        if spec.id == specialist_id:
            return spec
    known = ", ".join(f"{s.id} ({s.name['en']})" for s in team) or "none yet: build_specialist"
    raise ModelRetry(f"{tool}: no specialist has the id «{specialist_id}». This Brief's: {known}.")


def _maker(store: Store, deliverable_id: str) -> dict:
    """The agent run that made the Deliverable."""
    with store.rec.read() as c:
        (run_id,) = c.execute(
            "SELECT run_id FROM deliverable_drafts WHERE id = ?", (deliverable_id,)
        ).fetchone()
    return store.run(run_id)


def _known(ctx: ToolContext, packet: CheckPacket) -> set[str]:
    """The numbers that have a source in this Brief: every number in its tool results (team
    tools' results are the team's own words, so they do not count) and the ledger numbers the
    Deliverable uses."""
    results = [
        text
        for run in ctx.store.runs(ctx.brief_id)
        if run["history"]
        for name, text in agents.tool_returns(run["history"])
        if name not in TEAM_TOOLS
    ]
    ledger = [
        *(n["value"] for n in packet.numbers),
        *(f["value"] for f in packet.formulas),
        *(i["value"] for f in packet.formulas for i in f["inputs"]),
    ]
    return numbers_guard.known_values([*results, *ledger])


def _unsourced(ctx: ToolContext, draft: DeliverableDraft) -> CheckPacket:
    """The draft's Check Packet, with the numbers in its title and body that have no source."""
    packet = checker.packet_for(
        draft,
        brief_text=ctx.store.brief(ctx.brief_id)["text"],
        store=ctx.store,
        rec=ctx.rec,
        unsourced=(),
    )
    marked = numbers_guard.unsourced(f"{draft.title}\n{draft.body}", _known(ctx, packet))
    return replace(packet, unsourced=tuple(marked))
