"""`add_source` and the evidence check (`evidence`): a source must point at real
evidence, and its link, title and dates come from that evidence, never from the model.
`UNDATED_FILES` is read here and only here: patch it on this module."""

import asyncio
import json
import math
import re
from datetime import datetime
from typing import Literal

from pydantic import Field

from qsone import copy
from qsone.engine import truth
from qsone.engine.tools import ModelRetry, ToolContext
from qsone.engine.tools_records.shared import (
    _DATE,
    _ENGINEER_REFUSED,
    Where,
    _actor,
    _Args,
    _engineer,
    _engineer_ok,
    _json,
    _target,
)
from qsone.records import boq, ledger
from qsone.records.project import Records, RecordsError

# Writing to the Source Ledger ------------------------------------------------------------------

# What a quote's price covers: the material alone, or its installation (labour) as well.
Covers = Literal["supply", "supply_and_install", "install"]


class SourceArgs(_Args):
    kind: str = Field(min_length=1, max_length=64)
    title: str | None = Field(None, min_length=1, max_length=300)
    file_id: str | None = Field(None, min_length=1, max_length=64)
    locator: dict = Field(default_factory=dict)
    dated: str | None = Field(None, pattern=_DATE)
    log_id: str | None = Field(None, min_length=1, max_length=64)
    ref: str | None = Field(None, min_length=1, max_length=200)
    card_id: str | None = Field(None, min_length=1, max_length=64)
    question: str | None = Field(None, min_length=1, max_length=40)
    call_id: str | None = Field(None, min_length=1, max_length=64)
    covers: Covers | None = None
    where: Where = "project"


_SOURCE_EXAMPLE = {
    "kind": "quote",
    "file_id": "<file id>",
    "locator": {"sheet": "Quote", "row": 12},
    "dated": "2026-11-02",
}

_SOURCE_DOC = """Add real evidence before recording a number; computed numbers use calculate.
File kind quote/boq/specification/contract/drawing: file_id and locator from a read
(page or sheet/row);
dated: document date, omit if unknown. Web: log_id from web_read; prices: ref from prices_lookup;
engineer: card_id/question from ask_engineer; connector: call_id. Quote covers: supply,
supply_and_install/install. where=engineer keeps it across projects after approval.
Drawing picture evidence: locator {page, box:[x0,y0,x1,y1]} in PDF points, top-left origin.
Keep take-off observations unchecked in ask_engineer cards, each naming file/page/region;
record quantities only after confirmation, using the answer as evidence. calculate makes totals.
Returns source_id/date.
Example:
""" + _json(_SOURCE_EXAMPLE)

# An undated file (founder question pending): "received" dates it the day One received it,
# labelled `dated_how: "received"` («تاريخ الاستلام» / "date received", `copy.DATED_RECEIVED`);
# "refuse" refuses it until a date is given. Never an invented date.
UNDATED_FILES: Literal["received", "refuse"] = "received"

_COMPUTED = {"calculation", "sandbox"}  # only the QS Calc Engine writes a computed number
_UNCHECKED = {"column"}  # a place inside a row, kept as given
_KEY = re.compile(r"^[a-z_]{1,20}$")
_REF = re.compile(r"^(?:prices:)?([A-Z]{2})/([^@\s]+)@([0-9]{4}-[0-9]{2}-[0-9]{2})$")
OWN_PRICE_REF = "prices:own/"  # + a rate's number id in Engineer Records (prices_lookup's own)
_COUNTRIES = {"EG": "egypt", "SA": "saudi", "AE": "uae"}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _no_evidence(field: str) -> RecordsError:
    return RecordsError(copy.SOURCE_NOT_EVIDENCE, status=422, field=field)


def _day(stamp: str) -> str:
    """The local day of a stored UTC moment."""
    return datetime.fromisoformat(stamp).astimezone().date().isoformat()


def _place(locator: dict) -> dict:
    """The locator, with a page or row given as text ("3", "٣") read as its number."""
    place = {}
    for key, value in locator.items():
        # Page geometry is measured in PDF points, not a sourced financial number.
        if key == "box":
            if (
                not isinstance(value, list | tuple)
                or len(value) != 4
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, int | float)
                    or not math.isfinite(v)
                    or v < 0
                    for v in value
                )
                or value[0] >= value[2]
                or value[1] >= value[3]
                or "page" not in locator
            ):
                raise _no_evidence("locator")
            place[key] = list(value)
            continue
        if key == "ocr_low_confidence" and isinstance(value, bool):
            place[key] = value
            continue
        if key == "confidence":
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or not 0 <= value <= 100
            ):
                raise _no_evidence("locator")
            place[key] = value
            continue
        if not _KEY.match(str(key)) or not isinstance(value, str | int) or isinstance(value, bool):
            raise _no_evidence("locator")
        if key in ("page", "row") and isinstance(value, str) and value.translate(_DIGITS).isdigit():
            value = int(value.translate(_DIGITS))
        place[key] = value
    return place


def _inside(conn, file_id: str, pages: int | None, place: dict) -> None:
    """Raises `RecordsError` unless `place` is inside the file: a page within its pages, or a
    sheet, row, line, paragraph … that one of its passages has."""
    if "page" in place:
        if pages is None:
            raise _no_evidence("locator")
        if not isinstance(place["page"], int) or not 1 <= place["page"] <= pages:
            text = copy.fill(copy.FILE_PAGES_OUT_OF_RANGE, pages=str(pages))
            raise RecordsError(text, status=422, field="locator")
        return
    if "sheet" in place:
        matched = boq.source_sheet(conn, file_id, place["sheet"])
        if matched is None:
            raise _no_evidence("locator")
        place["sheet"] = matched
    keys = {k: v for k, v in place.items() if k not in _UNCHECKED}
    if not keys:
        raise _no_evidence("locator")
    where = " AND ".join(f"json_extract(locator, '$.{k}') = ?" for k in keys)
    found = conn.execute(
        f"SELECT 1 FROM chunks WHERE file_id = ? AND {where} LIMIT 1", (file_id, *keys.values())
    ).fetchone()
    if found is None:
        raise _no_evidence("locator")


def _made_by_a_script(conn, file_id: str) -> bool:
    """A file a Sandbox script wrote (and nobody had before): what it holds was computed."""
    return (
        conn.execute(
            "SELECT 1 FROM sandbox_runs r, json_each(r.outputs, '$.files') o"
            " WHERE json_extract(o.value, '$.file_id') = ? AND json_extract(o.value, '$.new')",
            (file_id,),
        ).fetchone()
        is not None
    )


def _file_source(conn, args: SourceArgs) -> dict:
    if args.file_id is None:
        raise _no_evidence("file_id")
    row = conn.execute(
        "SELECT name, pages, added_at FROM files WHERE id = ?", (args.file_id,)
    ).fetchone()
    if row is None:
        raise RecordsError(copy.FILE_NOT_IN_PROJECT, status=422, field="file_id")
    if _made_by_a_script(conn, args.file_id):  # Guardrail 2: a script's numbers are evidence
        raise RecordsError(copy.NUMBER_NEEDS_CALC, status=422, field="file_id")
    name, pages, added_at = row
    place = _place(args.locator)
    if not place:
        raise _no_evidence("locator")
    _inside(conn, args.file_id, pages, place)
    if args.dated is not None:
        dated, how = args.dated, "document"
    elif UNDATED_FILES == "received":
        dated, how = _day(added_at), "received"
    else:
        raise RecordsError(copy.NUMBER_NEEDS_DATE, status=422, field="dated")
    return {
        "kind": args.kind,
        "title": args.title or name,
        "file_id": args.file_id,
        "locator": place | {"dated_how": how} | _covers(conn, args, place),
        "dated": dated,
    }


def _covers(conn, args: SourceArgs, place: dict) -> dict:
    """What a quote's price covers, from the quote itself: {"covers": …}, or {} for another
    kind of file. A quote that says nothing of installation or labour covers supply alone, and
    one cannot be cited as covering it (the masonry priced at the block's price «شامل العمالة
    كما ورد في العرض», 5 Nov 2026)."""
    if args.kind.strip().lower() != "quote":
        return {"covers": args.covers} if args.covers else {}
    here = "\n".join(truth.texts_at(conn, args.file_id, place) or [])
    whole = truth.file_text(conn, args.file_id)
    labour = truth.covers_labour(here) or truth.covers_labour(whole)
    if args.covers in ("supply_and_install", "install") and not labour:
        raise ModelRetry(
            "add_source: this quote says nothing of installation or labour, so it covers "
            "supply only. Add it with covers supply (or leave covers out); price labour from "
            "another source, with calculate."
        )
    return {
        "covers": args.covers or ("supply_and_install" if truth.covers_labour(here) else "supply")
    }


def _web_source(conn, args: SourceArgs) -> dict:
    row = None
    if args.log_id is not None:
        row = conn.execute(
            "SELECT url, final_url, title, dated, dated_how, at, file_id FROM web_log"
            " WHERE id = ? AND action = 'read'",
            (args.log_id,),
        ).fetchone()
    if row is None:
        raise _no_evidence("log_id")
    url, final_url, title, dated, how, at, file_id = row
    link = final_url or url
    return {
        "kind": "web",
        "title": title or link,
        "file_id": file_id,
        "locator": {"log_id": args.log_id, "dated_how": how if dated else "read"},
        "url": link,
        "dated": dated or _day(at),
    }


def _own_price_source(eng: Records, number_id: str) -> dict:
    """An own price: a current rate in Engineer Records, by its number id."""
    with eng.read() as conn:
        row = conn.execute(
            "SELECT i.fields, n.dated FROM numbers n JOIN items i ON i.id = n.item_id"
            " WHERE n.id = ? AND n.name = 'rate' AND n.valid_until IS NULL",
            (number_id,),
        ).fetchone()
    if row is None:
        raise _no_evidence("ref")
    fields, dated = json.loads(row[0]), row[1]
    said = fields.get("description")
    return {
        "kind": "prices",
        "title": (said if isinstance(said, str) and said else "The engineer's own price")[:300],
        "locator": {"ref": f"{OWN_PRICE_REF}{number_id}"},
        "dated": dated,
    }


def _prices_source(eng: Records, args: SourceArgs) -> dict:
    if (args.ref or "").startswith(OWN_PRICE_REF):
        return _own_price_source(eng, args.ref.removeprefix(OWN_PRICE_REF))
    found = _REF.match(args.ref or "")
    row = None
    if found:
        code, item_id, day = found.groups()
        with eng.read() as conn:
            row = conn.execute(
                "SELECT payload FROM price_cache WHERE country IN (?, ?) AND item_id = ?"
                " AND day = ?",
                (code, _COUNTRIES.get(code, code), item_id, day),
            ).fetchone()
    if row is None:
        raise _no_evidence("ref")
    payload = json.loads(row[0])
    name = payload.get("name") or {}
    links = [s["url"] for s in payload.get("sources") or () if s.get("url")]
    return {
        "kind": "prices",
        "title": name.get("ar") or name.get("en") or f"QS Mind Prices {item_id}",
        "locator": {"ref": f"prices:{code}/{item_id}@{day}"},
        "url": links[0] if links else None,
        "dated": day,
    }


def _engineer_source(ctx: ToolContext, args: SourceArgs) -> dict:
    from qsone.tools import engineer  # Plan 5 Task 3's tool module, which imports the engine

    found = None if args.card_id is None else engineer.answered(ctx.store, args.card_id)
    if found is None:
        raise _no_evidence("card_id")
    locator: dict = {"card_id": args.card_id}
    title = "The engineer's answers"
    if args.question is not None:
        if args.question not in found["answers"]:
            raise _no_evidence("question")
        asked = {q["id"]: q["text"] for q in found["questions"]}
        locator |= {"question": args.question, "answer": found["answers"][args.question]}
        title = asked[args.question][:300]
    return {"kind": "engineer", "title": title, "locator": locator, "dated": found["dated"]}


def _connector_source(conn, args: SourceArgs) -> dict:
    row = None
    if args.call_id is not None:
        row = conn.execute(
            "SELECT connector, tool, at FROM connector_calls WHERE id = ? AND ok = 1",
            (args.call_id,),
        ).fetchone()
    if row is None:
        raise _no_evidence("call_id")
    connector, tool, at = row
    return {
        "kind": "connector",
        "title": f"{connector}: {tool}",
        "locator": {"call_id": args.call_id, "dated_how": "read"},
        "dated": _day(at),
    }


def evidence(ctx: ToolContext, target: Records, args: SourceArgs) -> dict:
    """The source row for `args`, from its evidence: in `target` for a file, a Web Log page or
    a Connector call; in Engineer Records for a QS Mind price or an own price; in the Brief's
    own file for an answered card. Raises `RecordsError`: NUMBER_NEEDS_CALC for a computed kind;
    SOURCE_NOT_EVIDENCE, FILE_NOT_IN_PROJECT or FILE_PAGES_OUT_OF_RANGE when it points at
    nothing; NUMBER_NEEDS_DATE for an undated file when `UNDATED_FILES` is "refuse"."""
    kind = args.kind.strip().lower()
    if kind in _COMPUTED:
        raise RecordsError(copy.NUMBER_NEEDS_CALC, status=422, field="kind")
    if kind == "prices":
        return _prices_source(_engineer(ctx), args)
    if kind == "engineer":
        return _engineer_source(ctx, args)
    with target.read() as conn:
        if kind == "web":
            return _web_source(conn, args)
        if kind == "connector":
            return _connector_source(conn, args)
        return _file_source(conn, args)  # quote, boq, specification, …: a document


def _write_source(rec: Records, row: dict, actor: str) -> dict:
    with rec.write(actor) as conn:
        source_id = ledger.write_source(conn, at=rec.clock(), actor=actor, **row)
    how = row["locator"].get("dated_how")
    out = {"source_id": source_id, "dated": row["dated"]} | ({"dated_how": how} if how else {})
    covers = row["locator"].get("covers")
    if covers:
        out |= {"title": row["title"], "covers": covers}
    if covers == "supply":
        out["note"] = (
            "Supply only: a rate from it is the material's price. Say so; an item that is "
            "installed takes labour from another source, with calculate."
        )
    return out


async def _add_source_tool(ctx: ToolContext, args: SourceArgs) -> str:
    target = _target(ctx, args.where)
    row = await asyncio.to_thread(evidence, ctx, target, args)
    if args.where == "engineer":
        action = copy.fill(copy.TOOL_ADD_SOURCE, title=row["title"])
        if not await _engineer_ok(ctx, action):
            return _ENGINEER_REFUSED
    out = await asyncio.to_thread(_write_source, target, row, _actor(ctx))
    return _json(out | {"where": args.where})
