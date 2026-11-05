"""The prices tools (Plan 5, Task 10): `prices_lookup` and `prices_propose`.

`prices_lookup` gives candidates in three groups, each with its value as exact text, unit,
currency, VAT basis, date, age in days, `old` and a source line (link and date only):
- `qsmind`: QS Mind Prices for the country, from the list saved in Engineer Records once a day
  and searched here, so the item's words never leave this computer; only subscribers get it;
- `own`: the engineer's own prices (rates in Engineer Records);
- `project`: this project's rates (its BOQ and the quotes kept in it).
It never picks one and never converts: comparing is the engineer's, computing the Calc
Engine's. A price QS Mind has no check for is "no price" (null), never 0. Source titles and
quotes stay off the model; names, links and dates are QS Mind's own, so the result is not
untrusted text.

`prices_propose` shows the prices an agent read or was told as one table card; the engineer ticks
the rows to keep. Ticked rows from the chat go to Engineer Records (or the project) with the card
as their source; rows of a supplier's quote point at its file and row. A supplier's personal
details are kept only as the engineer said (`records.keep`).

Importing this module registers both tools. No PydanticAI here."""

import asyncio
import json
import re
from datetime import date
from typing import Literal
from urllib.parse import parse_qsl
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from qsone import copy
from qsone.engine import tools_records
from qsone.engine.tools import Tool, ToolContext, register
from qsone.engine.types import Card, Progress, Text, read_answer
from qsone.prices import cache
from qsone.prices.client import COUNTRIES, VATS, PriceItem
from qsone.records import arabic, keep, ledger
from qsone.records.project import Records, RecordsError
from qsone.tools import cite
from qsone.tools.cite import SourceRef

FRESH_DAYS = {"daily": 21, "weekly": 21, "monthly": 45}  # QS Mind Prices' own freshness rule
OWN_FRESH_DAYS = FRESH_DAYS["monthly"]  # an own price or a project rate has no cadence
OWN_REF = tools_records.OWN_PRICE_REF  # "prices:own/<number id>": an own price, cited anywhere
TEXT_CHARS = 120  # of a description in a result
_TEXT_FIELDS = ("description", "name", "spec", "title")
_ROLES = frozenset({"lead", "specialist"})
KEEP = "keep"  # the rows card's option that keeps the ticked rows


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _actor(ctx: ToolContext) -> str:
    return ctx.agent.name["en"]


def _engineer(ctx: ToolContext) -> Records:
    if ctx.services is None:
        raise RecordsError(copy.ENGINEER_RECORDS_CLOSED)
    return ctx.services.engineer()


def _project(ctx: ToolContext) -> Records:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    return ctx.rec


def _say(ctx: ToolContext, text: Text) -> None:
    ctx.host.emit(Progress(ctx.brief_id, ctx.run_id, ctx.agent.name, text))


def _today(ctx: ToolContext) -> date:
    return date.fromisoformat(cache.local_day(ctx.services.clock()))


def _age(today: date, day: str | None) -> int | None:
    return None if day is None else (today - date.fromisoformat(day)).days


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= TEXT_CHARS else text[: TEXT_CHARS - 1] + "…"


# prices_lookup -------------------------------------------------------------------------------


class LookupArgs(_Args):
    item: str = Field(min_length=2, max_length=300, validation_alias=AliasChoices("item", "q"))
    also: list[str] = Field(default_factory=list, max_length=4)
    country: str | None = Field(None, pattern=r"^[A-Za-z]{2}$")
    unit: str | None = Field(None, min_length=1, max_length=40)
    k: int = Field(5, ge=1, le=10)

    @field_validator("also")
    @classmethod
    def _also(cls, value: list[str]) -> list[str]:
        if any(not 1 <= len(v.strip()) <= 300 for v in value):
            raise ValueError("each wording is 1 to 300 characters")
        return [v.strip() for v in value]


_LOOKUP_EXAMPLE = {
    "item": "حديد تسليح 16 مم",
    "also": ["rebar 16 mm"],
    "country": "EG",
    "unit": "طن",
}

_LOOKUP_DOC = f"""Look up an item's price: QS Mind Prices (subscribers), the engineer's own \
prices and this project's rates, each with its source, date, age in days and old flag.
- item: the item in the market's words; also: the same in the other language.
- country: EG, SA or AE; the project's when left out. unit: listed first when it matches.
It never picks or converts: show the candidates to the engineer, compute with the Calc Engine. \
value null means no price. Cite a QS Mind or own price with add_source kind prices and its ref.
Example:
{_json(_LOOKUP_EXAMPLE)}"""


def _country(ctx: ToolContext, asked: str | None) -> tuple[str | None, dict]:
    """The country's code and the default used; raises `RecordsError` (PRICES_COUNTRY) for a
    country Prices does not cover."""
    if asked:
        if asked.upper() not in COUNTRIES:
            raise RecordsError(copy.PRICES_COUNTRY, field="country")
        return asked.upper(), {}
    found = (ctx.rec.meta().get("country") or "").upper() if ctx.rec is not None else ""
    if found in COUNTRIES:
        return found, {"country": f"{found} (the project's)"}
    return None, {}


def _same_unit(a: str | None, b: str | None) -> bool:
    return bool(a and b) and arabic.normalise(a) == arabic.normalise(b)


def _qsmind(item: PriceItem, code: str, today: date) -> dict:
    dated = item.source_date or item.day
    age = _age(today, dated)
    found = {
        "name": item.name,
        "value": item.price,
        "unit": item.unit,
        "currency": item.currency,
        "vat": item.vat,
        "day": item.day,
        "dated": dated,
        "age_days": age,
        "old": age is not None and age > FRESH_DAYS.get(item.cadence, FRESH_DAYS["weekly"]),
        "confidence": item.confidence,
        "cadence": item.cadence,
        "flags": item.flags if item.price is not None else [*item.flags, "no_price"],
    }
    if item.spec["en"] or item.spec["ar"]:
        found["spec"] = item.spec
    if item.price is not None:
        found = {"ref": f"prices:{code}/{item.id}@{item.day}"} | found
    return found


def _ref_of(source_id: str, kind: str, file_id: str | None, locator: dict) -> str:
    """The typed ref of a Source Ledger source (cite's forms)."""
    if kind == "engineer" and locator.get("card_id"):
        return f"card:{locator['card_id']}"
    if locator.get("ref"):
        return str(locator["ref"])
    if locator.get("log_id"):
        return f"web:{locator['log_id']}"
    if file_id:
        place = [f"{k}={locator[k]}" for k in ("sheet", "row", "page") if k in locator]
        return f"file:{file_id}" + ("#" + "&".join(place) if place else "")
    return f"source:{source_id}"


_RATES = (
    "SELECT i.id, i.code, i.fields, n.id, n.value, n.unit, n.currency, n.dated, n.recorded_at,"
    " s.id, s.kind, s.title, s.file_id, s.locator"
    " FROM numbers n JOIN items i ON i.id = n.item_id JOIN sources s ON s.id = n.source_id"
    " WHERE n.name = 'rate' AND n.valid_until IS NULL"
)


def _words(text: str) -> set[str]:
    return set(arabic.normalise(text).split())


def _ledger(
    rec: Records, texts: list[str], today: date, *, own: bool = False
) -> list[tuple[float, dict, SourceRef]]:
    """Current rates in `rec` whose item matches any of `texts`, with their scores. With `own`
    (`rec` is Engineer Records), each ref is `prices:own/<number id>`, which add_source finds
    from any project."""
    wanted = [w for w in map(_words, texts) if w]
    with rec.read() as c:
        rows = c.execute(_RATES).fetchall()
    found = []
    for item_id, code, fields, number_id, value, unit, currency, dated, at, *source in rows:
        fields = json.loads(fields)
        said = " ".join(str(fields[k]) for k in _TEXT_FIELDS if isinstance(fields.get(k), str))
        have = _words(f"{code or ''} {said}")
        score = max((len(w & have) / len(w) for w in wanted), default=0)
        if not score:
            continue
        source_id, kind, title, file_id, locator = source
        ref = (
            f"{OWN_REF}{number_id}" if own else _ref_of(source_id, kind, file_id, json.loads(locator))
        )
        age = _age(today, dated)
        candidate = {
            "ref": ref,
            "item_id": item_id,
            "number_id": number_id,
            "source_id": source_id,
            **({"code": code} if code else {}),
            "description": _cut(said),
            "value": value,
            "unit": unit,
            "currency": currency,
            "vat": fields.get("vat") if fields.get("vat") in VATS else "unknown",
            "dated": dated,
            "age_days": age,
            "old": age is not None and age > OWN_FRESH_DAYS,
            "from": kind,
        }
        if isinstance(fields.get("supplier"), str):
            candidate["supplier"] = _cut(fields["supplier"])
        line = SourceRef(ref, title, read=at[:16].replace("T", " "), dated=dated)
        found.append((score, candidate, line))
    found.sort(key=lambda f: f[1]["dated"], reverse=True)  # the newest first, then the best
    found.sort(key=lambda f: -f[0])
    return found


def _units_first(found: list, unit: str | None, unit_of) -> list:
    if not unit:
        return found
    return sorted(found, key=lambda f: not _same_unit(unit_of(f), unit))  # stable


def _size(text: str, data: dict, notes: list[str], sources: list[SourceRef], defaults: dict) -> int:
    lines = [text, f"data: {_json(data)}", *notes, "sources:", f"defaults used: {defaults}"]
    lines += [cite.source_line(s) for s in sources]
    return len("\n".join(lines).encode())


async def _lookup(ctx: ToolContext, args: LookupArgs) -> str:
    eng = _engineer(ctx)
    code, defaults = _country(ctx, args.country)
    services, notes = ctx.services, []
    qsmind: list[tuple[dict, SourceRef | None]] = []
    today = _today(ctx)
    read = ctx.services.clock().strftime("%Y-%m-%d %H:%M UTC")
    if services.prices is None:
        notes.append(copy.PRICES_NOT_SUBSCRIBED)
    elif code is None:
        raise RecordsError(copy.PRICES_COUNTRY, field="country")
    else:
        note = await cache.refresh(services, code, on_device=services.on_device(ctx.rec))
        if note is not None:
            notes.append(note)
        if note != copy.PRICES_NOT_SUBSCRIBED:  # refused: none of QS Mind's prices
            items = await asyncio.to_thread(cache.lookup, eng, code, args.item, args.also, k=20)
            items = _units_first(items, args.unit, lambda i: i.unit["ar"] or i.unit["en"])
            for i in items[: args.k]:
                found = _qsmind(i, code, today)
                link = i.sources[0]["url"] if i.sources else None
                name = i.name["ar"] or i.name["en"]
                line = (
                    None
                    if "ref" not in found
                    else SourceRef(
                        found["ref"],
                        f"QS Mind Prices: {name}",
                        read,
                        dated=found["dated"],
                        link=link,
                    )
                )
                qsmind.append((found, line))
    texts = [args.item, *args.also]
    own = await asyncio.to_thread(_ledger, eng, texts, today, own=True)
    project = await asyncio.to_thread(_ledger, ctx.rec, texts, today) if ctx.rec else []
    own = [(c, s) for _, c, s in _units_first(own, args.unit, lambda f: f[1]["unit"])]
    project = [(c, s) for _, c, s in _units_first(project, args.unit, lambda f: f[1]["unit"])]
    groups = {"qsmind": qsmind, "own": own[: args.k], "project": project[: args.k]}
    for note in notes:
        _say(ctx, note)
    return _render(args, code, groups, [n["en"] for n in notes], defaults)


def _summary(args: LookupArgs, code: str | None, groups: dict) -> str:
    counts = {name: len(found) for name, found in groups.items()}
    where = f" in {code}" if code else ""
    text = (
        f"Prices for «{args.item}»{where}: {counts['qsmind']} from QS Mind Prices, "
        f"{counts['own']} of the engineer's own, {counts['project']} from this project. "
        "Candidates only: never pick one alone or convert a unit or currency."
    )
    return text if any(counts.values()) else text + "\n" + copy.PRICES_NONE_FOUND["en"]


def _render(args: LookupArgs, code: str | None, groups: dict, notes: list[str], defaults) -> str:
    """The result, with the last candidates of the longest group left out until it fits."""
    while True:
        text = _summary(args, code, groups)
        data = {name: [c for c, _ in found] for name, found in groups.items()}
        sources = [s for found in groups.values() for _, s in found if s is not None]
        if _size(text, data, notes, sources, defaults) <= cite.LIMIT - 256:
            return cite.render(
                text, data=data, notes=notes, sources=sources, defaults_used=defaults
            )
        longest = max(groups, key=lambda name: len(groups[name]))
        groups[longest] = groups[longest][:-1]
        if FEWER not in notes:
            notes.append(FEWER)


FEWER = "fewer shown to fit: use narrower words, a unit or a smaller k"


# prices_propose ------------------------------------------------------------------------------

_DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_FROM = re.compile(r"^(chat|file:([0-9a-f]{8,64})(?:#(.+))?)$")
Supplier = str | dict[str, str]


class ProposedRow(_Args):
    description: str = Field(min_length=1, max_length=300)
    unit: str = Field(min_length=1, max_length=40)
    rate: str = Field(pattern=r"^[0-9٠-٩]+([.٫][0-9٠-٩]+)?$", max_length=40)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    dated: str = Field(pattern=_DATE)
    vat: Literal["incl", "excl", "na", "unknown"] = "unknown"
    supplier: Supplier | None = None
    note: str | None = Field(None, min_length=1, max_length=300)
    row: int | None = Field(None, ge=1)

    @field_validator("dated")
    @classmethod
    def _real_day(cls, value: str) -> str:
        date.fromisoformat(value)  # 2026-02-30 is no day
        return value


class ProposeArgs(_Args):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    rows: list[ProposedRow] = Field(min_length=1, max_length=50)
    from_: str = Field(alias="from", pattern=_FROM.pattern)
    where: Literal["engineer", "project"]


_PROPOSE_EXAMPLE = {
    "rows": [
        {
            "description": "أسمنت بورتلاندي",
            "unit": "طن",
            "rate": "3950",
            "currency": "EGP",
            "dated": "2026-11-04",
            "vat": "incl",
        }
    ],
    "from": "chat",
    "where": "engineer",
}

_PROPOSE_DOC = f"""Ask the engineer to keep prices: their own (said in the chat, or a price \
list) or a supplier's quote. One card shows the rows; only the ticked ones are kept.
- rows: description, unit, rate (exact text), currency (EGP, SAR, AED), dated, vat (incl, \
excl, na, unknown), supplier, note; row: the file's row for a quote.
- from: "chat", or a file as "file:<id>#sheet=Quote".
- where: engineer (every project) or project (a quote).
Returns the ids kept and the rows left out.
Example:
{_json(_PROPOSE_EXAMPLE)}"""


def _origin(args: ProposeArgs) -> tuple[str | None, dict]:
    """(file id, its place) for a file, or (None, {}) for the chat."""
    found = _FROM.match(args.from_)
    if found[1] == "chat":
        return None, {}
    return found[2], dict(parse_qsl(found[3] or "", keep_blank_values=False))


def _file_evidence(ctx: ToolContext, target: Records, args: ProposeArgs) -> list[dict]:
    """The quote source of each row, checked against the file. Raises `RecordsError` when a
    row points at nothing."""
    file_id, place = _origin(args)
    found = []
    for r in args.rows:
        locator = place | ({"row": r.row} if r.row is not None else {})
        source = tools_records.SourceArgs(
            kind="quote", file_id=file_id, locator=locator, dated=r.dated, where=args.where
        )
        found.append(tools_records.evidence(ctx, target, source))
    return found


def _supplier_text(supplier: Supplier | None) -> str:
    if isinstance(supplier, dict):
        return " · ".join(v for v in supplier.values() if v)
    return supplier or ""


def _language(ctx: ToolContext) -> str:
    text = ctx.store.brief(ctx.brief_id)["text"]
    return "en" if len(re.findall(r"[A-Za-z]", text)) > len(re.findall("[؀-ۿ]", text)) else "ar"


def _card(ctx: ToolContext, args: ProposeArgs) -> Card:
    lang = _language(ctx)
    rows = [
        {
            "description": r.description,
            "unit": r.unit,
            "rate": r.rate,
            "currency": r.currency,
            "vat": copy.PRICES_VAT[r.vat][lang],
            "dated": r.dated,
            "supplier": _supplier_text(r.supplier),
        }
        for r in args.rows
    ]
    detail = copy.PRICES_FOR_ALL if args.where == "engineer" else copy.PRICES_FOR_PROJECT
    return Card(
        id=uuid4().hex,
        kind="rows",
        title=copy.PRICES_ASK,
        detail=copy.fill(detail, agent=ctx.agent.name),
        options=(KEEP, "no"),
        payload={
            "columns": [{"key": k, "label": label} for k, label in copy.PRICES_COLUMNS.items()],
            "rows": rows,
            "tick": True,
        },
    )


async def _kept_fields(ctx: ToolContext, r: ProposedRow) -> tuple[dict, dict]:
    """The item's fields with a supplier's personal details kept only as the engineer said,
    and what was dropped."""
    fields: dict = {"description": r.description, "unit": r.unit, "vat": r.vat}
    dropped: dict = {}
    if isinstance(r.supplier, dict):
        supplier, dropped = await keep.apply(ctx, r.supplier)
        if supplier:
            fields["supplier"] = supplier
    checked = {k: v for k, v in (("supplier", r.supplier), ("note", r.note)) if isinstance(v, str)}
    kept, more = await keep.apply(ctx, checked)
    return fields | kept, dropped | more


def _store(
    target: Records, rows: list[tuple[int, ProposedRow, dict, dict]], actor: str
) -> list[dict]:
    """Writes each ticked row's source, item and rate, in one transaction."""
    out = []
    with target.write(actor) as c:
        at = target.clock()
        for index, r, fields, source in rows:
            source_id = ledger.write_source(c, at=at, actor=actor, **source)
            item_id = ledger.write_item(c, at=at, actor=actor, kind="price", fields=fields)
            number_id = ledger.write_number(
                c,
                at=at,
                actor=actor,
                item_id=item_id,
                name="rate",
                value=r.rate,
                source_id=source_id,
                dated=r.dated,
                unit=r.unit,
                currency=r.currency,
            )
            out.append(
                {
                    "row": index,
                    "description": r.description,
                    "item_id": item_id,
                    "number_id": number_id,
                    "source_id": source_id,
                }
            )
    return out


async def _propose(ctx: ToolContext, args: ProposeArgs) -> str:
    target = _engineer(ctx) if args.where == "engineer" else _project(ctx)
    file_id, _ = _origin(args)
    quotes = None
    if file_id is not None:  # checked before the engineer is asked
        quotes = await asyncio.to_thread(_file_evidence, ctx, target, args)
    card = _card(ctx, args)
    answer = read_answer(card, await keep.ask(ctx, card))
    ticked = [] if answer["choice"] != KEEP else answer["rows_ok"]
    ticked = sorted({i for i in ticked if isinstance(i, int) and 0 <= i < len(args.rows)})
    rows, dropped = [], {}
    for i in ticked:
        r = args.rows[i]
        fields, gone = await _kept_fields(ctx, r)
        dropped |= gone
        source = (
            quotes[i]
            if quotes is not None
            else {
                "kind": "engineer",
                "title": "The engineer's prices",
                "locator": {"card_id": card.id, "row": i},
                "dated": r.dated,
            }
        )
        rows.append((i, r, fields, source))
    kept = await asyncio.to_thread(_store, target, rows, _actor(ctx)) if rows else []
    read = ctx.services.clock().strftime("%Y-%m-%d %H:%M UTC")
    sources = [
        SourceRef(
            _ref_of(k["source_id"], src["kind"], src.get("file_id"), src["locator"]),
            src["title"],
            read,
            dated=src["dated"],
        )
        for k, (_, _, _, src) in zip(kept, rows, strict=True)
    ]
    left_out = [
        {"row": i, "description": r.description} for i, r in enumerate(args.rows) if i not in ticked
    ]
    where = "Engineer Records, for every project" if args.where == "engineer" else "this project"
    text = f"The engineer kept {len(kept)} of {len(args.rows)} prices, in {where}."
    return cite.render(
        text,
        data={"kept": kept, "left_out": left_out, "where": args.where},
        notes=keep.dropped_note(dropped),
        sources=sources,
    )


register(
    Tool(
        name="prices_lookup",
        description=_LOOKUP_DOC,
        args=LookupArgs,
        risk="read",
        run=_lookup,
        activity=lambda a: copy.fill(copy.DOING_PRICES, item=a.item),
        example=_LOOKUP_EXAMPLE,
        group="prices",
    )
)
register(
    Tool(
        name="prices_propose",
        description=_PROPOSE_DOC,
        args=ProposeArgs,
        risk="write",
        run=_propose,
        activity=lambda _: copy.TOOL_PRICES_PROPOSE,
        writes=True,
        example=_PROPOSE_EXAMPLE,
        roles=_ROLES,
        group="prices",
    )
)
