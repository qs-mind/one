"""note_lesson (Plan 5, Task 7): a Lessons Learned note, an item of kind `lesson` in Project
Records (fields `text`, `kind`, `source_ref`). Moving one to Engineer Records is Plan 8's
`closing.carry`, one at a time, after the engineer's yes.

Importing this module registers the tool. No PydanticAI here."""

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from qsone import copy
from qsone.engine.tools import Tool, ToolContext, register
from qsone.records import ledger
from qsone.records.project import RecordsError

KIND = "lesson"


class LessonArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["method", "correction", "warning"]
    source_ref: str | None = Field(None, min_length=1, max_length=300)


_EXAMPLE = {
    "text": "The client's BOQ gives slab concrete in m2, not m3: check units before pricing.",
    "kind": "warning",
    "source_ref": "file:<file id>#sheet=BOQ&row=41",
}

_DOC = f"""Note a lesson learned in this project, for the engineer's next ones: a method that \
worked, a correction the engineer made, or a warning about a trap.
- text: the lesson in one or two plain sentences, in the engineer's language.
- kind: method, correction or warning.
- source_ref: where it came from, as a result's sources line gives it (file:…, card:…), when \
there is one.
Write a lesson when the engineer corrects you or a check catches a mistake. The engineer \
chooses at close-out which lessons go to every project. Returns lesson_id.
Example:
{json.dumps(_EXAMPLE, ensure_ascii=False)}"""


def _note(ctx: ToolContext, args: LessonArgs) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    actor = ctx.agent.name["en"]
    fields = args.model_dump(exclude={"source_ref"} if args.source_ref is None else set())
    with ctx.rec.write(actor) as conn:
        lesson_id = ledger.write_item(
            conn, at=ctx.rec.clock(), actor=actor, kind=KIND, fields=fields
        )
    return json.dumps({"lesson_id": lesson_id})


async def _note_lesson(ctx: ToolContext, args: LessonArgs) -> str:
    return await asyncio.to_thread(_note, ctx, args)


register(
    Tool(
        name="note_lesson",
        description=_DOC,
        args=LessonArgs,
        risk="write",
        run=_note_lesson,
        activity=lambda _: copy.TOOL_NOTE_LESSON,
        writes=True,
        example=_EXAMPLE,
        roles=frozenset({"lead", "specialist"}),
        group="records",
    )
)
