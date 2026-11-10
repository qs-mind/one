"""The two Finding tools (`findings`). Importing this module registers them."""

import asyncio

from qsone import copy
from qsone.engine.findings import PART, RaiseArgs, RecordArgs, publish, raise_finding, record
from qsone.engine.tools import Tool, ToolContext, register
from qsone.engine.tools_records.shared import _actor, _json, _project
from qsone.engine.types import Data

_RECORD_EXAMPLE = {
    "title": {"en": "Roof insulation has no quantity", "ar": "عزل الأسطح مالوش كمية"},
    "text": "Item 7/03 has no quantity in the BOQ.",
    "sources": [{"file_id": "<file id>", "locator": {"sheet": "BOQ", "row": 212}, "kind": "boq"}],
}
_RECORD_DOC = """Record a conflict or risk in the tender as a Finding; the whole team sees it at
once (search_records returns it). title: short {en, ar}; text: what conflicts, in your words;
sources: each {file_id, locator} from a read: a page or a sheet row inside that file, kind its
document (boq, specification, contract). item_ids: every BOQ item it concerns, in one Finding.
Search first; never record a Finding twice.
Example:
""" + _json(_RECORD_EXAMPLE)

_RAISE_EXAMPLE = {
    "finding_id": "<finding id>",
    "opinion": "Ask the consultant before pricing it.",
    "options": [
        {"en": "Ask the consultant", "ar": "نسأل الاستشاري"},
        {"en": "Price a provisional quantity", "ar": "نسعّر كمية مؤقتة"},
    ],
}
_RAISE_DOC = """Raise a recorded Finding to the engineer: your opinion and exactly two options
{en, ar}, your recommendation first. Returns at once: raised, or queued behind the one waiting.
Never wait for the decision: go on with what does not depend on it, or end your reply. The
decision reaches you as a message.
Example:
""" + _json(_RAISE_EXAMPLE)


async def _record_tool(ctx: ToolContext, args: RecordArgs) -> str:
    rec = _project(ctx)
    found = await asyncio.to_thread(record, rec, args, actor=_actor(ctx), brief_id=ctx.brief_id)
    publish(rec.id, [found])
    return _json({"finding_id": found["id"], "status": found["status"]})


async def _raise_tool(ctx: ToolContext, args: RaiseArgs) -> str:
    rec = _project(ctx)
    found, ahead = await asyncio.to_thread(raise_finding, rec, args, actor=_actor(ctx))
    publish(rec.id, [found])
    ctx.host.emit(Data(ctx.brief_id, PART, found["id"], {"finding_id": found["id"]}))
    from qsone.engine import room  # the Lead's message to the engineer in the team room (C6)

    room.finding_raised(ctx, found)
    out = {"finding_id": found["id"], "status": found["status"], "queued_ahead": ahead}
    return _json(out | {"next": "Do not wait for the decision; it reaches you as a message."})


register(
    Tool(
        "record_finding",
        _RECORD_DOC,
        RecordArgs,
        "write",
        _record_tool,
        lambda a: copy.tool_step("record_finding"),
        writes=True,
        example=_RECORD_EXAMPLE,
        roles=frozenset({"lead", "specialist"}),
        group="records",
    )
)
register(
    Tool(
        "raise_finding",
        _RAISE_DOC,
        RaiseArgs,
        "write",
        _raise_tool,
        lambda a: copy.tool_step("raise_finding"),
        writes=True,
        example=_RAISE_EXAMPLE,
        lead_only=True,
        roles=frozenset({"lead"}),
        group="records",
    )
)
