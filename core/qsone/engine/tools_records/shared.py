"""What the records tools share: the open Project Records and Engineer Records, the
actor, the engineer's yes to a write in Engineer Records, the tools' request model, and
the names more than one of their modules reads."""

import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from qsone import copy
from qsone.engine.tools import ToolContext
from qsone.engine.types import Card, Text
from qsone.records import keep
from qsone.records.project import Records, RecordsError


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _project(ctx: ToolContext) -> Records:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    return ctx.rec


def _actor(ctx: ToolContext) -> str:
    return ctx.agent.name["en"]


Where = Literal["project", "engineer"]


def _engineer(ctx: ToolContext) -> Records:
    """The open Engineer Records file. Raises `RecordsError` when it is not open."""
    if ctx.services is None:
        raise RecordsError(copy.ENGINEER_RECORDS_CLOSED)
    return ctx.services.engineer()


def _target(ctx: ToolContext, where: str) -> Records:
    return _engineer(ctx) if where == "engineer" else _project(ctx)


_ENGINEER_REFUSED = (
    "not done: the engineer chose not to keep this for all projects.\n"
    'instead: write it with where "project", or leave it.'
)


def _engineer_allowed(ctx: ToolContext) -> bool:
    with ctx.store.rec.read() as c:
        found = c.execute(
            "SELECT 1 FROM approvals WHERE brief_id = ? AND status = 'settled' AND choice = 'yes'"
            " AND json_extract(card, '$.kind') = 'keep' LIMIT 1",
            (ctx.brief_id,),
        ).fetchone()
    return found is not None


async def _engineer_ok(ctx: ToolContext, action: Text) -> bool:
    """True once the engineer said yes, in this Brief, to writing in Engineer Records: a write
    there crosses projects, so a `keep` card asks first, once per Brief."""
    if _engineer_allowed(ctx):
        return True
    card = Card(
        id=uuid4().hex,
        kind="keep",
        title=copy.KEEP_ENGINEER_ASK,
        detail=copy.fill(copy.KEEP_ENGINEER_DETAIL, agent=ctx.agent.name, action=action),
        options=("yes", "no"),
    )
    return await keep.ask(ctx, card) == "yes"


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"

_RATES = {"rate", "price", "unit_rate", "unit_price"}


def _field(name: str) -> dict | str:
    """A number's name in the engineer's words: rate is «الفئة», quantity «الكمية»."""
    words = copy.BOQ_FIELDS.get(name.lower())
    return {"en": words["en"].lower(), "ar": words["ar"]} if words else name
