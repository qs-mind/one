"""Read the map as untrusted navigation evidence, never as proof a page was read."""

import json
from difflib import get_close_matches
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from qsone import copy
from qsone.engine.tools import ModelRetry, Tool, register
from qsone.records.arabic import normalise
from qsone.records.mapping import store
from qsone.records.mapping.roles import file_role


class MapArgs(BaseModel):
    page: int = Field(1, ge=1)
    counts_page: int = Field(1, ge=1)
    mode: Literal["overview", "file", "facts", "links", "find", "sheets", "counts"] = "overview"
    file_id: str | None = None
    label: str | None = Field(None, max_length=200)
    parent: str | None = None
    cursor: str | None = None
    limit: int = Field(10, ge=1, le=100)
    rejected_cursor: str | None = None

    @model_validator(mode="after")
    def mode_limit(self):
        if self.mode == "sheets" and "limit" not in self.model_fields_set:
            self.limit = 50
        elif self.mode != "sheets" and self.limit > 20:
            raise ValueError("limit is at most 20 outside sheets mode")
        return self


def local_evidence(rec, row, args):
    """Bound each collection separately; locators and file ids travel with evidence."""
    fid = row["file_id"]
    offset = (args.page - 1) * args.limit
    with rec.read() as c:
        base = store.rows(
            c,
            "SELECT f.name,f.folder,f.kind,f.pages,m.ai_kind,m.read_how,m.structure FROM files f "
            "LEFT JOIN map_files m ON m.file_id=f.id WHERE f.id=? AND f.valid_until IS NULL",
            (fid,),
        )
        if not base:
            return row
        fields = store.decoded(base[0])
        structure = fields.pop("structure") or {}
        row.update(fields)
        row["role"] = file_role(fields.get("folder"), row.get("ai_kind"))
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
            "source FROM map_sheets s WHERE file_id=? AND valid_until IS NULL "
            "AND (sheet<>'Model' OR NOT EXISTS (SELECT 1 FROM map_sheets p "
            "WHERE p.file_id=s.file_id AND p.sheet<>'Model' AND p.valid_until IS NULL)) "
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
    if args.file_id:
        with ctx.rec.read() as c:
            candidates = c.execute("SELECT id,name FROM files WHERE valid_until IS NULL").fetchall()
        match = next((fid for fid, name in candidates if args.file_id == fid), None)
        if match is None:
            matches = [
                fid for fid, name in candidates if normalise(name) == normalise(args.file_id)
            ]
            match = matches[0] if len(matches) == 1 else None
        if match is None:
            names = [name for _, name in candidates]
            closest = get_close_matches(args.file_id, names, n=5, cutoff=0)
            raise ModelRetry(
                copy.FILE_NOT_IN_PROJECT["en"]
                + " Closest file names: "
                + json.dumps(closest, ensure_ascii=False)
            )
        args = args.model_copy(update={"file_id": match})
    if args.mode in ("sheets", "counts"):
        result = drawing_evidence(ctx.rec, args)
        from qsone.tools.drawing_guidance import GUIDANCE

        result["drawing_guidance"] = GUIDANCE
    elif args.mode in ("facts", "links"):
        result = store.entries(ctx.rec, args.mode, cursor=args.cursor, limit=args.limit)
        if args.mode == "facts":
            rejected = store.rejected_entries(
                ctx.rec, cursor=args.rejected_cursor, limit=args.limit
            )
            result["rejected"] = rejected["rejected"]
            result["rejected_next_cursor"] = rejected["next_cursor"]
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
    if "facts" in result:
        with ctx.rec.read() as c:
            for fact in result["facts"]:
                row = c.execute(
                    "SELECT f.folder,m.ai_kind FROM files f LEFT JOIN map_files m "
                    "ON m.file_id=f.id WHERE f.id=?",
                    (fact["file_id"],),
                ).fetchone()
                fact["role"] = file_role(*row) if row else file_role(None)
    return json.dumps(result, ensure_ascii=False)


register(
    Tool(
        "project_map",
        "Read first: overview; file(file_id); find(label); facts; links; sheets lists drawings "
        "sorted by number (default 50, max 100); page until next_page is null "
        "for a complete list; counts(label optional block-name filter) gives sourced sheet/file "
        "counts and project_total. file_id filters either mode; page paginates. Headings, BOQ "
        "tables, drawing sheets and block counts include sources. cursor pages files/facts/links; "
        "rejected_cursor pages unverified proposals; "
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


def drawing_evidence(rec, args):
    with rec.read() as c:
        rows = [
            store.decoded(r)
            for r in store.rows(
                c,
                "SELECT s.id,s.file_id,s.sheet,s.number,s.title,s.revision,s.scale,s.discipline,"
                "s.counts,s.source,f.name AS file,f.folder,m.ai_kind FROM map_sheets s "
                "JOIN files f ON f.id=s.file_id LEFT JOIN map_files m ON m.file_id=f.id "
                "WHERE s.valid_until IS NULL AND f.valid_until IS NULL "
                "ORDER BY coalesce(s.number,''),s.file_id,s.sheet,s.id",
            )
        ]
    paper_files = {row["file_id"] for row in rows if row["sheet"] != "Model"}
    project_total, file_totals, entries = 0, {}, []
    for row in rows:
        row["layout"] = row["sheet"]
        row["source"] = {"file_id": row["file_id"], "sheet": row["sheet"]}

        row["role"] = file_role(row.pop("folder", None), row.pop("ai_kind", None))
        if args.mode == "sheets":
            if row["sheet"] == "Model" and row["file_id"] in paper_files:
                continue
            row.pop("counts", None)
            if args.file_id is None or row["file_id"] == args.file_id:
                entries.append({k: row[k] for k in ("number", "title", "file", "layout")})
            continue
        counts = {
            name: count
            for name, count in row["counts"].items()
            if not args.label or normalise(args.label) in normalise(name)
        }
        total = sum(counts.values())
        project_total += total
        file_totals[row["file_id"]] = file_totals.get(row["file_id"], 0) + total
        if counts and (args.file_id is None or row["file_id"] == args.file_id):
            entries.extend(
                {
                    k: row[k]
                    for k in ("file_id", "file", "sheet", "layout", "number", "title", "source")
                }
                | {"counts": {name: count}, "total": count, "sheet_total": total}
                for name, count in sorted(counts.items())
            )
    # Page by both rows and UTF-8 bytes before the dispatcher's 8 KB guard.
    # Rebuild the same deterministic partitions on every request, so page 1
    # through next_page covers all sheets even with long Arabic titles.
    pages, batch, size = [], [], 0
    for entry in entries:
        width = len(json.dumps(entry, ensure_ascii=False).encode()) + 2
        if batch and (len(batch) >= args.limit or size + width > 6500):
            pages.append(batch)
            batch, size = [], 0
        batch.append(entry)
        size += width
    if batch:
        pages.append(batch)
    result = {
        args.mode: pages[args.page - 1] if args.page <= len(pages) else [],
        "total": len(entries),
        "next_page": args.page + 1 if args.page < len(pages) else None,
    }
    if args.mode == "counts":
        result.update(
            project_total=project_total,
            file_totals={row["file_id"]: file_totals[row["file_id"]] for row in result["counts"]},
        )
    return result
