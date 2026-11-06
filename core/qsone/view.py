"""Generative UI, first step (decision 16.1): the Lead QS shows the engineer a `View` in the chat,
built only from ONE's own blocks, through the `show` tool.

The model chooses what to show and how to lay it out; the core checks it and the screen draws it
from vetted blocks (ui/src/chat/parts/view). Rules:
- blocks: heading, prose, figures (label + number) and table (columns + rows), at most 24; any
  block may name its section, and the screen shows a run of blocks with one section under its
  title, so a view is one level deep;
- a table row has one fixed shape, its label, then its texts, then its numbers: no free keys
  and no cell that may be words or a reference, since the first bake-off (5 Nov 2026) found
  both broke a small model's function calls. The label's header is the table's own
  `label_header`, and the columns head the texts, then the numbers, so a row has as many of
  them as there are columns (the second bake-off: models counted the label's header among the
  columns);
- a number is never typed: it is a reference, `{"number": <number id>}` or a Sheet's cell
  `{"deliverable", "row", "column"}`, which the core resolves to its value, source and date
  (followed through corrections, as a Document's references are). An unknown reference, or a
  cell with no sourced number, is refused naming its place;
- every text goes through the numbers guard, as the Lead's reply does: a number no tool gave is
  marked on screen, never removed;
- `sample` is the model's flag, and always true when a shown number comes from a sample source;
- no HTML, ever: text with a tag is refused, and the screen renders words only; nor an id in
  a text, which would show as hex;
- a block of a kind ONE does not have is dropped, with a note back to the model.

A refusal is one `ModelRetry` per Brief. After that, `show` answers "not shown" as an ordinary
result, so the model writes its reply in words and the Brief never fails on a view.

The view goes out as `Data("view")`, a `data-view` part. Its tool result keeps the view's id, the
moment it was resolved and its unsourced numbers, so `stored_views` rebuilds the same view from
the stored history after a reload."""

import json
import re
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from pydantic_ai import ModelRetry

from qsone import copy
from qsone.deliverables import calc, store
from qsone.engine import numbers_guard
from qsone.engine.tools import Tool, ToolContext, register
from qsone.engine.types import Data
from qsone.records.project import Records, RecordsError

TOOL = "show"
MAX_BLOCKS = 24
KINDS = ("heading", "prose", "figures", "table")

Id = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]
Key = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Words = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NumberRef(_Closed):
    """A number in this project's Source Ledger."""

    number: Id


class CellRef(_Closed):
    """A number in a Sheet: its row id (or "total" for the bill) and its column key."""

    deliverable: Id
    row: Id | Literal["total"]
    column: Key


Num = NumberRef | CellRef


class _Block(_Closed):
    section: Short | None = Field(None, description="the section this block is shown under")


class Heading(_Block):
    kind: Literal["heading"]
    text: Short


class Prose(_Block):
    """Plain words; a blank line starts a paragraph. Never HTML."""

    kind: Literal["prose"]
    text: Words


class Figure(_Closed):
    label: Short
    value: Num


class Figures(_Block):
    """A row of key figures."""

    kind: Literal["figures"]
    items: list[Figure] = Field(min_length=1, max_length=8)


class Column(_Closed):
    label: Short


class Row(_Closed):
    """Its label, then its texts, then its numbers: the same counts in every row."""

    label: Short
    texts: list[Short] = Field(default_factory=list, max_length=6)
    numbers: list[Num] = Field(default_factory=list, max_length=6)


class Table(_Block):
    """`label_header` heads the rows' labels; the columns head a row's texts, then its numbers."""

    kind: Literal["table"]
    label_header: Short
    columns: list[Column] = Field(max_length=8)  # required: with a default a model left it out
    rows: list[Row] = Field(min_length=1, max_length=50)


Block = Annotated[Heading | Prose | Figures | Table, Field(discriminator="kind")]


class View(_Closed):
    title: Short
    sample: bool = False  # the view shows sample data, labelled as such
    blocks: list[Block] = Field(min_length=1, max_length=MAX_BLOCKS)


class ShowArgs(BaseModel):
    """The tool's arguments as they came: `call` lets them through and `_show` checks them against
    `View`, so a refusal keeps to the Brief's one retry. The model is given `View`'s schema."""

    model_config = ConfigDict(extra="allow")

    @classmethod
    def model_json_schema(cls, *args, **kwargs) -> dict:
        return View.model_json_schema(*args, **kwargs)


class _Refused(Exception):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


# Checking ---------------------------------------------------------------------------------------

_HTML = re.compile(r"<\s*/?\s*[A-Za-z!][^>]*>")
_ID = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")
# A number written in words, which the numbers guard cannot see: the words for hundreds and up,
# and for a percentage (round 3 of the bake-off: "one hundred and forty EGP", «عشرة بالمئة»). A
# count in words ("the three quotes", «أعلى خمسة بنود») is words, not a figure.
_AR_WORD = r"(?<![؀-ۿ])(?:[وب]?(?:ال)?)(?:{})(?![؀-ۿ])"
_IN_WORDS = re.compile(
    r"\b(?:hundreds?|thousands?|millions?|billions?|percent|per\s+cent)\b|"
    + _AR_WORD.format(
        "مائة|مئة|مية|مئات|ميت|مائتين|مئتين|ميتين|ألف|الف|ألفين|الفين|آلاف|الاف|مليون|"
        "مليونين|ملايين|مليار|مليارات|بالمئة|بالمائة|بالمية|في المية|في المائة"
    ),
    re.IGNORECASE,
)
_REF_HINT = (
    'A number is never typed: give {"number": "<number id>"} from the Source Ledger, or '
    '{"deliverable": "<sheet id>", "row": "<row id>" or "total", "column": "<column key>"}.'
)


def _kind(block) -> str | None:
    return block.get("kind") if isinstance(block, dict) else None


def _drop_unknown(args: dict) -> tuple[dict, list[str]]:
    """The arguments without blocks of a kind ONE does not have, and a note for each one dropped."""
    blocks = args.get("blocks")
    if not isinstance(blocks, list):
        return args, []
    notes: list[str] = []
    kept = []
    for i, block in enumerate(blocks):
        kind = _kind(block)
        if kind is None or kind in KINDS:
            kept.append(block)
        elif kind == "group":
            notes.append(f"blocks[{i}]: there is no group; give each block a section instead.")
        else:
            notes.append(
                f"blocks[{i}]: ONE has no block «{kind}» (only {', '.join(KINDS)}); "
                "it was left out."
            )
    return args | {"blocks": kept}, notes


_TAGS = {*KINDS, "str", "dict", "list", "bool", "int"}  # union tags in a pydantic error's place


def _place(loc: tuple) -> str:
    """A pydantic error's place as the model wrote it: blocks[1].items[0].value. The union tags
    pydantic adds (a block's kind, a reference's model name) are left out."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        elif part in _TAGS or not re.fullmatch(r"[a-z][a-z0-9_]*", part):
            continue
        else:
            out += f".{part}" if out else part
    return out or "the arguments"


def _validated(args: dict) -> View:
    try:
        return View.model_validate(args)
    except ValidationError as e:
        first = e.errors()[0]
        where = _place(first["loc"])
        ref = where.endswith(".value") or re.search(r"\.numbers\[\d+\]$", where)
        hint = f" {_REF_HINT}" if ref else ""
        raise _Refused(f"«{where}»: {first['msg']}.{hint}") from None


def _many(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _check(data: dict) -> None:
    """The rules a schema cannot hold: each table's rows fit its columns, and no HTML and no id
    in any text."""
    for i, block in enumerate(data["blocks"]):
        if block["kind"] != "table":
            continue
        width = len(block["columns"])
        first = block["rows"][0]
        for j, row in enumerate(block["rows"]):
            at = f"«blocks[{i}].rows[{j}]»"
            texts, numbers = len(row["texts"]), len(row["numbers"])
            if (texts, numbers) != (len(first["texts"]), len(first["numbers"])):
                raise _Refused(
                    f"{at}: every row has as many texts and as many numbers as the first; "
                    f"the table has {_many(width, 'column')}."
                )
            if texts + numbers != width:
                raise _Refused(
                    f"{at}: {_many(texts, 'text')} and {_many(numbers, 'number')} need "
                    f"{_many(texts + numbers, 'column')}, and the table has "
                    f"{_many(width, 'column')}. The rows' labels have their header in "
                    "label_header, not among the columns."
                )
    for place, text in _texts(data):
        if _HTML.search(text):
            raise _Refused(f"«{place}»: no HTML or code; write plain words.")
        if _ID.search(text):
            raise _Refused(
                f"«{place}»: never put an id in words; show a number as "
                '{"number": "<number id>"} in figures or in a row\'s numbers.'
            )
        found = _IN_WORDS.search(text)
        if found:
            raise _Refused(
                f"«{place}»: «{found.group()}» writes a number in words. Show a number as "
                '{"number": "<number id>"}; if the data has no such number, say so plainly.'
            )


def _texts(data: dict):
    """(place, text) for every text in the view."""
    yield "title", data["title"]
    for i, block in enumerate(data["blocks"]):
        here = f"blocks[{i}]"
        if block.get("section"):
            yield f"{here}.section", block["section"]
        if block["kind"] in ("heading", "prose"):
            yield f"{here}.text", block["text"]
        elif block["kind"] == "figures":
            for j, item in enumerate(block["items"]):
                yield f"{here}.items[{j}].label", item["label"]
        else:
            yield f"{here}.label_header", block["label_header"]
            for j, column in enumerate(block["columns"]):
                yield f"{here}.columns[{j}].label", column["label"]
            for j, row in enumerate(block["rows"]):
                yield f"{here}.rows[{j}].label", row["label"]
                for k, text in enumerate(row["texts"]):
                    yield f"{here}.rows[{j}].texts[{k}]", text


def _refs(data: dict):
    """(place, holder, key) for every number reference: holder[key] is the reference."""
    for i, block in enumerate(data["blocks"]):
        here = f"blocks[{i}]"
        if block["kind"] == "figures":
            for j, item in enumerate(block["items"]):
                yield f"{here}.items[{j}].value", item, "value"
        elif block["kind"] == "table":
            for j, row in enumerate(block["rows"]):
                for k in range(len(row["numbers"])):
                    yield f"{here}.rows[{j}].numbers[{k}]", row["numbers"], k


# Resolving --------------------------------------------------------------------------------------


def _resolve(rec: Records, data: dict, at: str) -> list[dict]:
    """Puts each reference's cell (value, unit, currency, number id, source id, date) in its
    place, and the sources and the sample flag on the view. Returns the cells."""
    refs = list(_refs(data))
    sources: dict[str, dict] = {}
    cells: list[dict] = []
    sample = data["sample"]
    with rec.read() as conn:
        ids = [holder[key]["number"] for _, holder, key in refs if "number" in holder[key]]
        followed = store._numbers_followed(conn, ids, at) if ids else {}
        if ids:
            sample = sample or store._sample(conn, [f[2] for f in followed.values()], {})
        sheets: dict[str, dict | None] = {}
        for place, holder, key in refs:
            ref = holder[key]
            if "number" in ref:
                found = followed.get(ref["number"])
                if found is None:
                    raise _Refused(
                        f"«{place}»: there is no number {ref['number']} in this project's Source "
                        "Ledger. Use an id that ledger_numbers or another tool gave you."
                    )
                _, _, cell, source_id, source = found
            else:
                d = ref["deliverable"]
                if d not in sheets:
                    sheets[d] = store._sheet_then(conn, d, at)
                sheet = sheets[d]
                if sheet is None:
                    raise _Refused(f"«{place}»: there is no Sheet {d} in this project.")
                cell = _sheet_cell(sheet, ref["row"], ref["column"])
                if cell is None or not cell.get("source") or cell["source"] not in sheet["sources"]:
                    raise _Refused(
                        f"«{place}»: the Sheet's cell {ref['row']}/{ref['column']} has no number "
                        "with a source."
                    )
                source_id, source = cell["source"], sheet["sources"][cell["source"]]
                sample = sample or sheet["sample"]
            holder[key] = cell
            sources[source_id] = source
            cells.append(cell)
    data["sources"] = sources
    data["sample"] = sample or any(s["kind"] == "sample" for s in sources.values())
    return cells


def _sheet_cell(sheet: dict, row: str, column: str) -> dict | None:
    if row == calc.BILL_ROW:  # the bill's total, under its calculated column (as a Document's)
        calculated = {c["key"] for c in sheet["columns"] if c["kind"] == "calc"}
        cell = sheet["total"] if column in calculated else None
    else:
        cell = next((r["cells"].get(column) for r in sheet["rows"] if r["id"] == row), None)
    return cell if isinstance(cell, dict) and "value" in cell else None


def _stored_tables(args: dict) -> dict:
    """A view stored before `label_header`: its tables' first column headed the labels."""
    blocks = args.get("blocks")
    if not isinstance(blocks, list):
        return args
    out = []
    for block in blocks:
        columns = block.get("columns") if _kind(block) == "table" else None
        if isinstance(columns, list) and columns and "label_header" not in block:
            head = columns[0].get("label") if isinstance(columns[0], dict) else None
            block = block | {"label_header": head, "columns": columns[1:]}
        out.append(block)
    return args | {"blocks": out}


def _build(
    rec: Records, args: dict, at: str, *, stored: bool = False
) -> tuple[dict, list[dict], list[str]]:
    """The view's data part (without its unsourced numbers), its cells and the notes on what
    was dropped. `stored`: arguments from the history, perhaps from before `label_header`.
    Raises `_Refused`."""
    cleaned, dropped = _drop_unknown(_stored_tables(args) if stored else args)
    data = _validated(cleaned).model_dump(mode="json")
    _check(data)
    cells = _resolve(rec, data, at)
    return data, cells, dropped


def _known(ctx: ToolContext) -> set[str]:
    """Every number the Brief's tools gave, as the reply's guard counts them."""
    from qsone.engine import agents, team

    results = [
        text
        for run in ctx.store.runs(ctx.brief_id)
        if run["history"]
        for name, text in agents.tool_returns(run["history"])
        if name not in team.TEAM_TOOLS
    ]
    return numbers_guard.known_values(results)


def _unsourced(data: dict, known: set[str]) -> list[str]:
    found: list[str] = []
    for _, text in _texts(data):
        found += [n for n in numbers_guard.unsourced(text, known) if n not in found]
    return found


# The tool ---------------------------------------------------------------------------------------

_retried: set[str] = set()  # the Briefs whose one retry on a view is used
_shown: dict[tuple[str, str], str] = {}  # (Brief, the view's arguments) -> the view shown


def _refuse(ctx: ToolContext, text: str) -> str:
    if ctx.brief_id not in _retried:
        _retried.add(ctx.brief_id)
        raise ModelRetry(f"show: {text} Fix it and call show again.")
    note = f"Not shown: {text} Answer in words; do not call show again in this Brief."
    return json.dumps({"shown": None, "note": note}, ensure_ascii=False)


async def _show(ctx: ToolContext, parsed: BaseModel) -> str:
    if ctx.rec is None:
        raise RecordsError(copy.PROJECT_NOT_OPEN)
    args = dict(parsed.model_extra or {})
    key = (ctx.brief_id, json.dumps(args, sort_keys=True, ensure_ascii=False))
    if key in _shown:  # the breakdown showed twice in one reply (6 Nov 2026)
        note = "This view is already on the engineer's screen; it is not shown again."
        return json.dumps({"shown": _shown[key], "note": note}, ensure_ascii=False)
    at = ctx.rec.clock()
    try:
        data, cells, dropped = _build(ctx.rec, args, at)
    except _Refused as refused:
        return _refuse(ctx, refused.text)
    known = _known(ctx) | numbers_guard.known_values(c["value"] for c in cells)
    data["unsourced"] = _unsourced(data, known)
    view_id = uuid4().hex
    ctx.host.emit(Data(ctx.brief_id, "view", view_id, data))
    _shown[key] = view_id
    out = {
        "shown": view_id,
        "at": at,
        "numbers": len(cells),
        "sample": data["sample"],
        "unsourced": data["unsourced"],
        "dropped": dropped,
        "note": "The engineer sees this view; do not write it again, as a table or as JSON.",
    }
    return json.dumps(out, ensure_ascii=False)


def stored_views(rec: Records | None, brief_id: str, history: bytes) -> list[Data]:
    """The Brief's views again, from a run's stored history: each `show` that was shown, its
    arguments resolved as of the moment it was shown, with the unsourced numbers it had then."""
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        ModelResponse,
        ToolCallPart,
        ToolReturnPart,
    )

    if rec is None:
        return []
    messages = ModelMessagesTypeAdapter.validate_json(history)
    asked = {
        p.tool_call_id: p.args_as_dict()
        for m in messages
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart) and p.tool_name == TOOL
    }
    found = []
    for m in messages:
        if not isinstance(m, ModelRequest):
            continue
        for p in m.parts:
            if not (isinstance(p, ToolReturnPart) and p.tool_name == TOOL):
                continue
            try:
                out = json.loads(p.content) if isinstance(p.content, str) else p.content
                data, _, _ = _build(rec, asked[p.tool_call_id], out["at"], stored=True)
            except (ValueError, KeyError, TypeError, _Refused):
                continue  # not shown, or not readable
            data["unsourced"] = list(out.get("unsourced") or [])
            found.append(Data(brief_id, "view", out["shown"], data))
    return found


# In no language: "…" stands for the engineer's words (round 2: an example in one language
# pulled requests in the other into it).
_EXAMPLE = {
    "title": "…",
    "blocks": [
        {
            "kind": "figures",
            "items": [{"label": "…", "value": {"number": "6f1c0d2e9a4b4c7e8f3a2b1c0d9e8f7a"}}],
        },
        {
            "kind": "table",
            "label_header": "…",
            "columns": [{"label": "…"}, {"label": "…"}],
            "rows": [
                {
                    "label": "03/02",
                    "texts": ["…"],
                    "numbers": [{"number": "0b7e4c2a9d1f4e8a8c3b2a1d0e9f8c7b"}],
                }
            ],
        },
    ],
}

_DOC = f"""Show a view when figures or a table say it better than words. \
Blocks: heading, prose, figures, table; at most 24; any may take a section. A table's \
label_header heads its rows' labels; columns head each row's texts, then its numbers. A number \
is never typed, never written in words; never put an id in a text: \
{{"number": "<number id>"}} or a Sheet's cell \
{{"deliverable": "<sheet id>", "row": "<row id>" or "total", "column": "<key>"}}; ONE adds \
value, source, date. Words in the engineer's language. No HTML. sample: true for sample data.
Example:
{json.dumps(_EXAMPLE, ensure_ascii=False)}"""

register(
    Tool(
        name=TOOL,
        description=_DOC,
        args=ShowArgs,
        risk="read",
        run=_show,
        activity=lambda _: copy.tool_step(TOOL),
        lead_only=True,
        example=_EXAMPLE,
        roles=frozenset({"lead"}),
        group="records",  # it reads Project Records: not in the General chat
    )
)
