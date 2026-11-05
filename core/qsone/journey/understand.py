"""The "I understood this" card (Plan 8, decision 16): one Brief to the Lead QS after a tender
folder comes in, and the card the engineer corrects and approves.

- **The Brief.** `start` gives the Lead QS `INSTRUCTION`. The Lead reads the files with its own
  tools, imports a BOQ through `boq_import` (so the client's BOQ shows as its Client BOQ frame,
  the one import path), then hands its result to the tool `understood`, typed as
  `ProjectUnderstood`. The tool serves both AI links the same way (a model, or the engineer's
  Claude Code over MCP).
- **The check is the tool's validator** (`check`): a result with a fact that has no source, a
  file that is not a current file, a place that is not in that file, a date that is not a real
  one, or a count that no code gave, goes back to the Lead with the exact fix, and nothing is
  saved. A count is never typed: its `trace_id` names a BOQ import or a calculation, and the
  value saved is the one that trace gives.
- **What is saved:** items of kind `project_fact` (client, submission date, contract type, the
  number of BOQ items, the missing documents), each with its source, and one `file_sort` item
  per file (the Lead's own label and why). Labels are the Lead's: there is no fixed list.
- **The engineer's corrections** are item updates by `engineer`, with the source "the engineer,
  <date>". Approving is kept in the project's meta and audited; the Lead saving again takes the
  approval back. Plans 4 and 5 have no Project Procedure writer yet, so approving starts nothing
  else for now.
- **In the chat**, the tool's result shows as a `data-understood` part; `stored_cards` gives it
  again from the stored tool results.

Never logs a fact, a name or a label: ids only."""

import asyncio
import json
import re
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from qsone import copy, usage
from qsone.engine.tools import ModelRetry, Tool, ToolContext, register
from qsone.engine.types import Data
from qsone.journey import setup_state
from qsone.records import audit, ledger
from qsone.records.project import Records, RecordsError

TOOL = "understood"
CARD = "understood"  # the chat's `data-understood` part
FACT = "project_fact"
SORT = "file_sort"
SOURCED = ("client", "submission_date", "contract_type")
NAMES = (*SOURCED, "items_count")
APPROVED = "understood_approved_at"  # meta: when the engineer approved the card
NEW_SENT = "usage_project_new"  # meta: Usage Stats' project_new went once
ENGINEER = "engineer"
LEAD = "lead_qs"
_PLACES = ("page", "sheet", "row", "line", "paragraph", "layer")
_PREFIX = re.compile(r"^(?:file|calc|calculation|import|trace):")

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Sourced(_Model):
    value: Line
    file_id: str | None = Field(None, max_length=80)  # the file it comes from (files_list)
    locator: dict | None = None  # where in it: {"page": 3} or {"sheet": "BOQ", "row": 12}


class Counted(_Model):
    value: str = Field(max_length=20)
    trace_id: str | None = Field(None, max_length=80)  # a boq_import import_id or a calculation


class FileSort(_Model):
    file_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    why: str = Field(min_length=1, max_length=300)


class ProjectUnderstood(_Model):
    client: Sourced | None = None
    submission_date: Sourced | None = None  # YYYY-MM-DD
    contract_type: Sourced | None = None  # in the Lead QS's words
    items_count: Counted | None = None  # from code, never typed by the AI
    missing: list[Line] = Field(default_factory=list, max_length=50)
    files: list[FileSort] = Field(default_factory=list, max_length=5000)


INSTRUCTION = (
    "This Brief is the first look at a tender folder the engineer has just added. Know every "
    "file well enough to say what it is, then call understood once with what the folder shows. "
    "Each fact (client, submission date, contract type) takes the file and the place in it that "
    "says so; leave out a fact no file states. The number of BOQ items comes from code: import "
    "the BOQ with boq_import and give its import_id as the trace_id. Sort every file with a "
    "label of your own and a short reason. List the documents a tender like this needs that "
    "are not there. Then say in two lines what the card holds; the engineer checks and approves "
    "it."
)

_EXAMPLE = {
    "client": {"value": "هيئة - عينة", "file_id": "<file id>", "locator": {"page": 1}},
    "submission_date": {"value": "2026-12-01", "file_id": "<file id>", "locator": {"page": 2}},
    "items_count": {"value": "118", "trace_id": "<import_id>"},
    "missing": ["Soil report"],
    "files": [{"file_id": "<file id>", "label": "Tender letter", "why": "Names the client"}],
}

_DOC = f"""Save what you understood of the tender folder, for the engineer's "I understood \
this" card. Call it once, after reading the files; a refusal says exactly what to fix.
- client, submission_date (YYYY-MM-DD), contract_type: each {{"value", "file_id", "locator"}}: \
the file it comes from (from files_list) and a locator of that file, as files_read gives it, \
such as {{"page": 3}} or {{"sheet": "Cover", "row": 2}}. Leave out a fact that no file states.
- items_count: {{"value", "trace_id"}}: the import_id of a boq_import (or a calculation id). \
Never count by hand.
- missing: the documents a tender like this needs that are not in the folder, in plain words.
- files: every file with a label of your own (what it is) and why, in the engineer's language.
Example:
{json.dumps(_EXAMPLE, ensure_ascii=False)}"""


# The check -----------------------------------------------------------------------------------


def _id(value: str) -> str:
    return _PREFIX.sub("", value.strip())


def _current(conn, file_id: str) -> tuple[int | None] | None:
    """(pages,) of a current file, or None."""
    return conn.execute(
        "SELECT pages FROM files WHERE id = ? AND valid_until IS NULL", (file_id,)
    ).fetchone()


def _same(a: Any, b: Any) -> bool:
    return str(a).strip().casefold() == str(b).strip().casefold()


def _in_file(conn, file_id: str, pages: int | None, locator: dict) -> bool:
    """True when the locator names a page, a row, a line or a paragraph the file has."""
    wanted = {k: v for k, v in locator.items() if k in _PLACES}
    if not wanted or wanted.keys() == {"sheet"}:
        return False
    page = wanted.get("page")
    if set(wanted) == {"page"} and pages and str(page).isdigit() and 1 <= int(page) <= pages:
        return True  # a scanned page with no text yet is still a page of the file
    for (text,) in conn.execute("SELECT locator FROM chunks WHERE file_id = ?", (file_id,)):
        found = json.loads(text)
        if all(k in found and _same(found[k], v) for k, v in wanted.items()):
            return True
    return False


def _real_date(value: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def trace_value(conn, trace_id: str) -> str | None:
    """The count a trace gives: a BOQ import's number of items, or a calculation's value."""
    row = conn.execute(
        "SELECT after FROM audit WHERE action = 'import' AND table_name = 'boq_imports'"
        " AND row_id = ? ORDER BY id LIMIT 1",
        (trace_id,),
    ).fetchone()
    if row is not None:
        return str(json.loads(row[0]).get("items", 0))
    row = conn.execute("SELECT value FROM calculations WHERE id = ?", (trace_id,)).fetchone()
    return None if row is None else str(row[0])


def check(rec: Records, result: ProjectUnderstood) -> list[str]:
    """What is wrong with the result, each said exactly as the Lead must fix it (English)."""
    return settle(rec, result)[1]


def _place_of(conn, file_id: str, value: str) -> dict | None:
    """The place in the file whose text has `value` (its first passage that does), or None."""
    wanted = value.strip().casefold()
    if len(wanted) < 3:
        return None
    for text, locator in conn.execute(
        "SELECT text, locator FROM chunks WHERE file_id = ? ORDER BY id", (file_id,)
    ):
        if wanted in text.casefold():
            place = {k: v for k, v in json.loads(locator).items() if k in _PLACES}
            return place or None
    return None


def _newest_import(conn) -> str | None:
    row = conn.execute(
        "SELECT row_id FROM audit WHERE action = 'import' AND table_name = 'boq_imports'"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def settle(rec: Records, result: ProjectUnderstood) -> tuple[ProjectUnderstood, list[str]]:
    """The result as ONE can save it, and what was left out of it, each said as the Lead must
    fix it (English). A fact whose locator names no place of its file is found by its value in
    that file's text, and saved at that place (a weak model gave pages for a text file, was
    refused three times, and the card never showed: 5 Nov 2026); a count with no trace takes the
    project's newest BOQ import; a fact or a file that still does not check is left out."""
    wrong: list[str] = []
    fixed: dict[str, Any] = {}
    with rec.read() as conn:
        for name in SOURCED:
            fact: Sourced | None = getattr(result, name)
            if fact is None:
                continue
            if not fact.file_id or not fact.locator:
                wrong.append(copy.FACT_NEEDS_SOURCE["en"].format(fact=name))
                fixed[name] = None
                continue
            file_id = _id(fact.file_id)
            found = _current(conn, file_id)
            if found is None:
                wrong.append(copy.FACT_FILE_UNKNOWN["en"].format(file_id=fact.file_id))
                fixed[name] = None
            elif not _in_file(conn, file_id, found[0], fact.locator):
                place = _place_of(conn, file_id, fact.value)
                if place is None:
                    text = copy.FACT_LOCATOR_UNKNOWN["en"]
                    wrong.append(text.format(fact=name, file_id=fact.file_id))
                    fixed[name] = None
                else:
                    fixed[name] = fact.model_copy(update={"locator": place})
            if name == "submission_date" and not _real_date(fact.value):
                wrong.append(copy.FACT_DATE_BAD["en"].format(fact=name))
                fixed[name] = None
        count = result.items_count
        if count is not None and (
            not count.trace_id or trace_value(conn, _id(count.trace_id)) is None
        ):
            newest = _newest_import(conn)
            if newest is None:
                wrong.append(copy.COUNT_NEEDS_TRACE["en"])
                fixed["items_count"] = None
            else:
                fixed["items_count"] = Counted(value="0", trace_id=newest)
        files = []
        for sort in result.files:
            if _current(conn, _id(sort.file_id)) is None:
                wrong.append(copy.FACT_FILE_UNKNOWN["en"].format(file_id=sort.file_id))
            else:
                files.append(sort)
    return result.model_copy(update=fixed | {"files": files}), list(dict.fromkeys(wrong))


# Saving and reading --------------------------------------------------------------------------


def _items(conn, kind: str) -> dict[str, dict]:
    """{name or file id: item} of the kind, newest last."""
    key = "$.name" if kind == FACT else "$.file_id"
    rows = conn.execute(
        f"SELECT id, fields, updated_by, json_extract(fields, '{key}') FROM items"
        " WHERE kind = ? ORDER BY created_at, rowid",
        (kind,),
    ).fetchall()
    return {k: {"id": i, "fields": json.loads(f), "by": by} for i, f, by, k in rows}


def _put(conn, rec: Records, found: dict, kind: str, key: str, fields: dict, actor: str) -> None:
    """Inside `rec.write`: creates the item, or updates it (audited, its version up) when its
    fields changed."""
    item = found.get(key)
    if item is None:
        ledger.write_item(conn, at=rec.clock(), actor=actor, kind=kind, fields=fields)
    elif item["fields"] != fields:
        ledger.update_item(rec, item["id"], fields=fields, actor=actor)  # joins the transaction


def _approve(conn, rec: Records, on: bool, actor: str) -> None:
    before = conn.execute("SELECT value FROM meta WHERE key = ?", (APPROVED,)).fetchone()
    was = before is not None and bool(before[0])
    if was == on:
        return
    at = rec.clock()
    rec.set_meta(conn, APPROVED, at if on else "")
    audit.record(
        conn,
        at=at,
        actor=actor,
        action="approve" if on else "unapprove",
        table="meta",
        row_id=APPROVED,
        before={"approved": was},
        after={"approved": on},
    )


def save(rec: Records, result: ProjectUnderstood, *, actor: str) -> None:
    """Saves a checked result in one transaction: each fact with its source, the missing
    documents, and one sort item per file. A count's value is the one its trace gives. Facts
    the result leaves out stay as they were. Takes back an approval."""
    with rec.write(actor) as conn:
        facts = _items(conn, FACT)
        for name in SOURCED:
            fact: Sourced | None = getattr(result, name)
            if fact is None:
                continue
            source = {"kind": "file", "file_id": _id(fact.file_id or ""), "locator": fact.locator}
            fields = {"name": name, "value": fact.value, "source": source}
            _put(conn, rec, facts, FACT, name, fields, actor)
        count = result.items_count
        if count is not None and count.trace_id:
            trace = _id(count.trace_id)
            value = trace_value(conn, trace)
            if value is not None:
                source = {"kind": "count", "trace_id": trace}
                fields = {"name": "items_count", "value": value, "source": source}
                _put(conn, rec, facts, FACT, "items_count", fields, actor)
        if result.missing or "missing" not in facts:  # a call that fixes facts keeps the list
            missing = {"name": "missing", "value": list(result.missing), "source": {"kind": "lead"}}
            _put(conn, rec, facts, FACT, "missing", missing, actor)
        sorts = _items(conn, SORT)
        for sort in result.files:
            file_id = _id(sort.file_id)
            fields = {"file_id": file_id, "label": sort.label, "why": sort.why}
            _put(conn, rec, sorts, SORT, file_id, fields, actor)
        _approve(conn, rec, False, actor)


def _source(conn, source: dict) -> dict:
    """A fact's source as the card shows it: a file with its name, a count, or the engineer."""
    if source.get("kind") != "file":
        return source
    row = conn.execute("SELECT name FROM files WHERE id = ?", (source["file_id"],)).fetchone()
    return source | {"file_name": row[0] if row else None}


def facts(rec: Records) -> dict:
    """The GET /facts answer: {"facts": {name: {"value", "source", "by"}}, "missing": [str],
    "files": [{"file_id", "name", "folder", "label", "why"}], "approved": bool}. `by` is
    "engineer" or "lead_qs"; a file replaced since is not listed."""
    with rec.read() as conn:
        found = _items(conn, FACT)
        out = {
            name: {
                "value": item["fields"]["value"],
                "source": _source(conn, item["fields"]["source"]),
                "by": ENGINEER if item["by"] == ENGINEER else LEAD,
            }
            for name, item in found.items()
            if name in NAMES
        }
        missing = found.get("missing", {}).get("fields", {}).get("value", [])
        current = {
            i: (n, f)
            for i, n, f in conn.execute(
                "SELECT id, name, folder FROM files WHERE valid_until IS NULL"
            )
        }
        sorted_files = [
            {
                "file_id": file_id,
                "name": current[file_id][0],
                "folder": current[file_id][1],
                "label": item["fields"]["label"],
                "why": item["fields"]["why"],
            }
            for file_id, item in _items(conn, SORT).items()
            if file_id in current
        ]
        approved = conn.execute("SELECT value FROM meta WHERE key = ?", (APPROVED,)).fetchone()
    return {
        "facts": out,
        "missing": missing,
        "files": sorted_files,
        "approved": approved is not None and bool(approved[0]),
    }


def correct(rec: Records, values: dict[str, str], *, approve: bool) -> dict:
    """The engineer's corrections, by `engineer`, each with the source "the engineer, <date>",
    then the approval as given. Raises `RecordsError` FACT_DATE_BAD (422) for a submission
    date that is not a real YYYY-MM-DD, and then nothing is saved."""
    date_given = values.get("submission_date")
    if date_given is not None and not _real_date(date_given.strip()):
        text = copy.fill(copy.FACT_DATE_BAD, fact=copy.FACT_SUBMISSION_DATE)
        raise RecordsError(text, status=422, field="submission_date")
    with rec.write(ENGINEER) as conn:
        found = _items(conn, FACT)
        today = rec.clock()[:10]
        for name, value in values.items():
            item = found.get(name)
            if item is not None and item["fields"]["value"] == value.strip():
                continue  # unchanged: its source stays
            source = {"kind": "engineer", "date": today}
            fields = {"name": name, "value": value.strip(), "source": source}
            _put(conn, rec, found, FACT, name, fields, ENGINEER)
        _approve(conn, rec, approve, ENGINEER)
    return facts(rec)


# The Brief -----------------------------------------------------------------------------------


def _counts(rec: Records) -> dict:
    with rec.read() as conn:
        (files_n,) = conn.execute("SELECT count(*) FROM files WHERE valid_until IS NULL").fetchone()
        (zips,) = conn.execute(
            "SELECT count(*) FROM audit WHERE action = 'unzip' AND table_name = 'zips'"
            " AND json_extract(after, '$.opened')"
        ).fetchone()
        (folder,) = conn.execute(
            "SELECT count(*) FROM files WHERE folder IS NOT NULL AND valid_until IS NULL"
        ).fetchone()
    return {"files": files_n, "zips": zips, "from_folder": folder > 0}


def project_new_once(rec: Records) -> None:
    """Usage Stats' `project_new`, once per project: when its folder is first understood, or
    archived as old work. Counts only."""
    if rec.meta().get(NEW_SENT):
        return
    usage.track("project_new", **_counts(rec))
    with rec.write(ENGINEER) as conn:
        rec.set_meta(conn, NEW_SENT, "1")


async def start(rec: Records, engine) -> str:
    """Starts the Brief in the project's chat, in the engineer's language; returns its id.
    Raises what `Engine.start_brief` raises (BriefBusy, NoAI, RecordsError)."""
    text = copy.UNDERSTAND_BRIEF[setup_state.language()]
    brief_id = await engine.start_brief(rec.id, text, instruction=INSTRUCTION)
    await asyncio.to_thread(project_new_once, rec)
    return brief_id


# The tool ------------------------------------------------------------------------------------


def _card(brief_id: str, project_id: str) -> Data:
    return Data(brief_id, CARD, f"{CARD}-{brief_id}", {"project_id": project_id})


async def _understood(ctx: ToolContext, args: ProjectUnderstood) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    rec = ctx.rec
    args, wrong = await asyncio.to_thread(settle, rec, args)
    saved = [n for n in NAMES if getattr(args, n) is not None]
    if wrong and not (saved or args.files or args.missing):
        raise ModelRetry("Nothing was saved. Fix these, then call understood again:\n- "
                         + "\n- ".join(wrong))  # fmt: skip
    await asyncio.to_thread(save, rec, args, actor=ctx.agent.name["en"])
    ctx.host.emit(_card(ctx.brief_id, rec.id))  # the card shows what checks, always
    out = {"saved": True, "card": CARD, "project_id": rec.id, "facts": saved,
           "files": len(args.files), "missing": len(args.missing)}  # fmt: skip
    if wrong:
        out["not_saved"] = wrong
        out["note"] = (
            "The card shows what was saved. Tell the engineer plainly what was left out; to add "
            "it, call understood again with only those facts fixed (the rest stays)."
        )
    return json.dumps(out)


def stored_cards(brief_id: str, results: list[tuple[str, str]]) -> list[Data]:
    """The card's chat part again, from the Lead's stored tool results."""
    found = []
    for name, text in results:
        if name != TOOL:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("saved") and isinstance(data.get("project_id"), str):
            found.append(_card(brief_id, data["project_id"]))
    return found


register(
    Tool(
        name=TOOL,
        description=_DOC,
        args=ProjectUnderstood,
        risk="write",
        run=_understood,
        activity=lambda _: copy.tool_step(TOOL),
        writes=True,
        lead_only=True,
        example=_EXAMPLE,
        roles=frozenset({"lead"}),
        group="records",
    )
)
