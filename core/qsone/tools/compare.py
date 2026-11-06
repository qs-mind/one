"""Lead QS's revision comparison, using the same records operation as the screen."""

import asyncio
import json

from pydantic import Field

from qsone import copy
from qsone.compare import CompareArgs
from qsone.engine.tools import Tool, ToolContext, register
from qsone.records.compare import compare_files
from qsone.records.project import RecordsError


class Args(CompareArgs):
    page: int = Field(default=1, ge=1)


async def run(ctx: ToolContext, args: Args) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    result = await asyncio.to_thread(compare_files, ctx.rec, args.old_file_id, args.new_file_id)
    # Registry pagination keeps even a large word diff accessible instead of silently truncating.
    return json.dumps(result, ensure_ascii=False)


register(
    Tool(
        "compare_files",
        "Compare two stored PDF file ids, including an older revision with the same name. "
        "Returns exact added/removed words, observed image changes, unchanged count and unpaired "
        "pages. Pairing is by unique sheet number, then title, then remaining order; order is a "
        "fallback, not proof of sheet identity. Cite both file names and page numbers from each "
        "result. Never infer an engineering change from pixels alone. Raster checks use 1400px "
        "page-box renders, not subpixel or semantic detection. File date is its upload date. "
        "Use page for subsequent result pages. "
        'Example: {"old_file_id":"old-id","new_file_id":"new-id"}',
        Args,
        "read",
        run,
        lambda _: copy.COMPARE_STEP,
        untrusted=True,
        lead_only=True,
        roles=frozenset({"lead"}),
        example={"old_file_id": "old-id", "new_file_id": "new-id"},
    )
)
