"""Read the map as untrusted navigation evidence, never as proof a page was read."""

import json
from typing import Literal

from pydantic import BaseModel, Field

from qsone import copy
from qsone.engine.tools import ModelRetry, Tool, register
from qsone.records.arabic import normalise
from qsone.records.mapping import store


class MapArgs(BaseModel):
    page: int = Field(1, ge=1)
    mode: Literal["overview", "file", "facts", "links", "find"] = "overview"
    file_id: str | None = None
    label: str | None = Field(None, max_length=200)
    parent: str | None = None
    cursor: str | None = None
    limit: int = Field(10, ge=1, le=20)


async def read_map(ctx, args):
    if ctx.rec is None:
        raise ModelRetry(copy.FILE_NOT_IN_PROJECT["en"])
    if args.mode in ("facts", "links"):
        result = store.entries(ctx.rec, args.mode, cursor=args.cursor, limit=args.limit)
    elif args.mode == "file":
        # Exclude full structure/page text and keep all child collections paged.
        with ctx.rec.read() as c:
            rows = store.rows(
                c,
                "SELECT file_id,ai_kind,ai_title,ai_group,key_pages,pages,ai_state,note FROM "
                "map_files WHERE file_id=? AND valid_until IS NULL",
                (args.file_id,),
            )
        if not rows:
            raise ModelRetry(copy.FILE_NOT_IN_PROJECT["en"])
        result = store.decoded(rows[0])
    elif args.mode == "find":
        if not args.label:
            raise ModelRetry("Supply label for find.")
        # Keyset traversal: scan bounded chunks rather than loading every map row.
        with ctx.rec.read() as c:
            rows = store.rows(
                c,
                "SELECT file_id,ai_title,key_pages FROM map_files WHERE valid_until IS NULL AND"
                " file_id>? ORDER BY file_id LIMIT 201",
                (args.cursor or "",),
            )
        found = []
        last = args.cursor
        for row in rows[:200]:
            last = row["file_id"]
            row = store.decoded(row)
            if normalise(args.label) in normalise(
                json.dumps([row["ai_title"], row["key_pages"]], ensure_ascii=False)
            ):
                found.append(row)
            if len(found) == args.limit:
                break
        result = {
            "files": found,
            "next_cursor": last
            if rows and (len(rows) > 200 or last != rows[-1]["file_id"])
            else None,
        }
    else:
        result = store.list_map(ctx.rec, parent=args.parent, cursor=args.cursor, limit=args.limit)
    return json.dumps(result, ensure_ascii=False)


register(
    Tool(
        "project_map",
        "Read this first for tender questions. Modes: overview (groups/files/key pages), file "
        "(file_id), facts (states and confirmations), links, find (label in either language). "
        "Use next_cursor for more entries, page for long results. Then files_read the key page; "
        "map entries do not establish "
        'a citation. Example: {"mode":"find","label":"Contract data"}.',
        MapArgs,
        "read",
        read_map,
        lambda _: copy.MAP_AI_LABEL,
        untrusted=True,
        group="files",
        example={"mode": "overview"},
    )
)
