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
    counts_page: int = Field(1, ge=1)
    mode: Literal["overview", "file", "facts", "links", "find"] = "overview"
    file_id: str | None = None
    label: str | None = Field(None, max_length=200)
    parent: str | None = None
    cursor: str | None = None
    limit: int = Field(10, ge=1, le=20)


def local_evidence(rec, row, args):
    """Bound each collection separately; locators and file ids travel with evidence."""
    fid = row["file_id"]
    offset = (args.page - 1) * args.limit
    with rec.read() as c:
        base = store.rows(
            c,
            "SELECT f.name,f.folder,f.kind,f.pages,m.read_how,m.structure FROM files f "
            "LEFT JOIN map_files m ON m.file_id=f.id WHERE f.id=? AND f.valid_until IS NULL",
            (fid,),
        )
        if not base:
            return row
        fields = store.decoded(base[0])
        structure = fields.pop("structure") or {}
        row.update(fields)
        row["headings"] = structure.get("headings", [])[:10]
        tables = store.rows(
            c,
            "SELECT id,locator,header,row_count,column_guess FROM map_tables "
            "WHERE file_id=? AND valid_until IS NULL AND looks_like_boq=1 "
            "ORDER BY id LIMIT ? OFFSET ?",
            (fid, args.limit + 1, offset),
        )
        sheets = store.rows(
            c,
            "SELECT file_id,sheet,number,title,revision,scale,discipline,counts,"
            "source FROM map_sheets WHERE file_id=? AND valid_until IS NULL "
            "ORDER BY sheet,id LIMIT ? OFFSET ?",
            (fid, args.limit + 1, offset),
        )
    row["boq_tables"] = [store.decoded(t) for t in tables[: args.limit]]
    row["boq_tables_next_page"] = args.page + 1 if len(tables) > args.limit else None
    row["sheets"] = [store.decoded(t) for t in sheets[: args.limit]]
    for sheet in row["sheets"]:
        counts = sorted(sheet["counts"].items(), key=lambda pair: (-pair[1], pair[0]))
        sheet["counts"] = dict(
            counts[(args.counts_page - 1) * args.limit : args.counts_page * args.limit]
        )
        sheet["counts_next_page"] = (
            args.counts_page + 1 if len(counts) > args.counts_page * args.limit else None
        )
    row["sheets_next_page"] = args.page + 1 if len(sheets) > args.limit else None
    return row


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
        result = local_evidence(ctx.rec, store.decoded(rows[0]), args)
        for name in ("facts", "links"):
            child = store.entries(
                ctx.rec, name, cursor=args.cursor, limit=args.limit, file_id=args.file_id
            )
            result[name] = child[name]
            result[name + "_next_cursor"] = child["next_cursor"]

    elif args.mode == "find":
        if not args.label:
            raise ModelRetry("Supply label for find.")
        # Search local evidence too, before AI classification has ever run.
        with ctx.rec.read() as c:
            c.create_function("map_normalise", 1, lambda text: normalise(text or ""))
            rows = store.rows(
                c,
                "SELECT m.file_id,m.ai_title,m.key_pages FROM map_files m JOIN files f "
                "ON f.id=m.file_id WHERE m.valid_until IS NULL AND f.valid_until IS NULL "
                "AND m.file_id>? AND (instr(map_normalise(f.name||' '||coalesce(f.folder,'')),?)>0 "
                "OR instr(map_normalise(coalesce(m.ai_title,'')||' '||m.key_pages||' '||"
                "m.structure),?)>0 "
                "OR EXISTS (SELECT 1 FROM map_sheets s WHERE s.file_id=m.file_id AND "
                "s.valid_until IS NULL AND instr(map_normalise(coalesce(s.number,'')||' '||"
                "coalesce(s.title,'')||' '||coalesce(s.discipline,'')),?)>0)) "
                "ORDER BY m.file_id LIMIT ?",
                (args.cursor or "", *([normalise(args.label)] * 3), args.limit + 1),
            )
        result = {
            "files": [
                local_evidence(ctx.rec, store.decoded(row), args) for row in rows[: args.limit]
            ],
            "next_cursor": rows[args.limit - 1]["file_id"] if len(rows) > args.limit else None,
        }
    else:
        result = store.list_map(ctx.rec, parent=args.parent, cursor=args.cursor, limit=args.limit)
        result["files"] = [local_evidence(ctx.rec, row, args) for row in result["files"]]
    return json.dumps(result, ensure_ascii=False)


register(
    Tool(
        "project_map",
        "Read first: overview; file(file_id); find(label); facts; links. Local headings, BOQ "
        "tables, drawing sheets and block counts include sources. cursor pages files/facts/links; "
        "page pages sheets/tables; counts_page pages blocks. Read cited prose with files_read.",
        MapArgs,
        "read",
        read_map,
        lambda _: copy.MAP_AI_LABEL,
        untrusted=True,
        self_paged=True,
        group="files",
        example={"mode": "overview"},
    )
)
