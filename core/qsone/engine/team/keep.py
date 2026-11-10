"""`keep_member`: at the end of a tender the Lead asks the engineer whether to keep a member for
later tenders (the `keep_member` card); "yes" makes it permanent. Never asked in a Confidential
Project: a member's identity was written inside that tender and stays in it. Registered when
the package is imported."""

from uuid import uuid4

from pydantic import Field

from qsone import copy
from qsone.engine import identity, identity_live
from qsone.engine.tools import Denied, ModelRetry, Tool, ToolContext, register
from qsone.engine.types import Card, read_answer
from qsone.records.project import RecordsError

from .common import _Args, _ask, _join, _json


class KeepArgs(_Args):
    member_id: str = Field(min_length=1, max_length=64)


_KEEP_EXAMPLE = {"member_id": "<member id>"}

_KEEP_DOC = f"""At the end of a tender, ask the engineer whether to keep one member of its \
team for later tenders: member_id is its id in this tender's team. ONE shows the engineer the \
member's identity and record; "yes" makes it permanent, "no" ends it with this tender. Ask \
once per member. Never in a Confidential Project, and never for the Lead QS or the Checking QS.
Example:
{_json(_KEEP_EXAMPLE)}"""


async def _keep_member(ctx: ToolContext, args: KeepArgs) -> str:
    if ctx.rec is None:
        raise ModelRetry("keep_member: members are kept from a tender's own conversation.")
    if ctx.rec.meta().get("confidential") == "1":
        raise RecordsError(copy.KEEP_MEMBER_CONFIDENTIAL)
    if args.member_id in identity.FIXED_ROLES:
        raise RecordsError(copy.KEEP_MEMBER_FIXED, field="member_id")
    found = identity.project_member(ctx.rec, args.member_id)
    if found is None or found[2]:  # not in the team, or only proposed
        raise RecordsError(copy.IDENTITY_MEMBER_NOT_FOUND, field="member_id")
    card_text, kind, _ = found
    if kind == "permanent":
        return _json({"member_id": args.member_id, "kind": "permanent"})
    engineer = identity.engineer_of(ctx.host)
    if engineer is None:
        raise RuntimeError("keep_member needs the Brief's Engineer Records")
    card = Card(
        uuid4().hex,
        "keep_member",
        copy.fill(copy.KEEP_MEMBER_TITLE, name=card_text["name"]),
        _join(
            copy.fill(
                copy.KEEP_MEMBER_DETAIL,
                title=card_text["title"],
                speciality=card_text["speciality"],
            )
        ),
        ("yes", "no"),
        payload={"member_id": args.member_id},
    )
    if read_answer(card, await _ask(ctx, card))["choice"] != "yes":
        raise Denied("keep_member")
    identity.keep(engineer, ctx.rec, args.member_id)
    identity_live.changed(getattr(ctx.host, "engine", None), ctx.rec.id, args.member_id)
    return _json({"member_id": args.member_id, "kind": "permanent"})


register(
    Tool(
        "keep_member",
        _KEEP_DOC,
        KeepArgs,
        "write",
        _keep_member,
        lambda a: copy.TOOL_KEEP_MEMBER,
        lead_only=True,
        writes=True,
        example=_KEEP_EXAMPLE,
        roles=frozenset({"lead"}),
        group="team",
    )
)
