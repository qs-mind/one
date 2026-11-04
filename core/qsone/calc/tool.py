"""The QS Calc Engine's four tools for agents: calculate, define_unit, explain_number, recalculate.

Each tool is a plain typed function `(rec, request, actor) -> dict` with its pydantic request
model, an English doc the model reads (at most 250 words, with one example that runs) and an
{en, ar} description for the engineer. `TOOLS` lists them by name, for the agent engine to
register. `call` validates a payload and runs a tool. It never raises a refusal; it returns
`{"error": {en, ar}, "key", "field", "example", ...values}`, and pydantic's own text never reaches
the agent. Replies are small, and numbers in them are always strings.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import get_args

from pydantic import BaseModel, ValidationError

from qsone import copy
from qsone.calc import engine, graph, resolve
from qsone.calc.errors import CalcError
from qsone.calc.spec import CalcRequest, ExplainRequest, InputSpec, RecalcRequest, UnitRequest
from qsone.records.project import Records, RecordsError

_RESULTS = 20  # results (and skipped codes) in a calculate reply
_LISTED = 50  # stale calculations or changes in a recalculate reply


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


# The tools.


def calculate(rec: Records, req: CalcRequest, actor: str) -> dict:
    out = engine.calculate(rec, req, actor=actor)
    reply = {
        "results": [asdict(r) for r in out.results[:_RESULTS]],
        "count": len(out.results),
        "saved": sum(r.calculation is not None and not r.unchanged for r in out.results),
        "unchanged": sum(r.unchanged for r in out.results),
        "skipped": out.skipped[:_RESULTS],
        "defaults_used": out.defaults_used,
        "notes": out.notes,
    }
    if out.steps:
        reply["steps"] = out.steps
    return reply


def define_unit(rec: Records, req: UnitRequest, actor: str) -> dict:
    number_id = resolve.define_unit(rec, req, actor=actor)
    with rec.read() as conn:
        value, unit = conn.execute(
            "SELECT value, unit FROM numbers WHERE id = ?", (number_id,)
        ).fetchone()
    return {"symbol": req.symbol, "equals": f"{value} {unit}", "number": number_id}


def explain_number(rec: Records, req: ExplainRequest, actor: str) -> dict:
    return engine.explain(rec, req.number, page=req.page)


def recalculate(rec: Records, req: RecalcRequest, actor: str) -> dict:
    if not req.apply:
        found = graph.stale(rec)
        return {"stale": [asdict(s) for s in found[:_LISTED]], "count": len(found)}
    done = graph.recalculate(rec, actor=actor, only=req.only)
    return {
        "changes": [asdict(c) for c in done.changes[:_LISTED]],
        "count": len(done.changes),
        "failed": done.failed,
        "waiting": done.waiting,
    }


# Their docs and examples. Each doc holds its example exactly, and a test runs it.

_CALCULATE_EXAMPLE = {
    "formula": "cement * cement_price * (1 + waste) + gang / output",
    "inputs": {
        "cement_price": {"item": "CEM", "name": "price"},
        "waste": {"constant": "5", "unit": "%", "why": "estimator's waste rule"},
    },
    "item": "03/02",
    "result": {"unit": "EGP/m3"},
    "save": {"name": "rate"},
}

_CALCULATE_DOC = f"""Calculate a number exactly. Never compute a number yourself: this tool does, \
and saves it in the Source Ledger with its formula, sources and steps.
- formula: names and + - * / ^ %, comparisons, sum count avg min max round abs sqrt to if, pi. \
No thousands separators.
- inputs: each name the formula uses, in one of these shapes:
  {{"number": "<id>"}} a ledger number;
  {{"item": "<id or code>", "name": "rate"}} an item's current number;
  {{"numbers": ["<id>", ...]}} a list;
  {{"each": {{"code_prefix": "03/"}}, "name": "amount"}} that number on every matching item \
(also "kind", "where"), a list;
  {{"constant": "5", "unit": "%", "why": "..."}} a plain number or %, with why.
  A name not in inputs reads that number on `item`.
- item: bare names read its numbers; the result is saved on it.
- result.unit: the unit the result must have (EGP, EGP/m3, m3); it is checked. result.round: \
{{"places", "mode"}}, default half_up to 2 places.
- for_each: a selector instead of item: one call prices a whole section.
- save: {{"name"}}; omit it to preview. Replacing a current number needs save.reason. \
The same call on unchanged inputs writes nothing.
Example, the rate for 1 m3 of concrete (cement, gang and output are 03/02's own numbers):
{_json(_CALCULATE_EXAMPLE)}"""

_DEFINE_UNIT_EXAMPLE = {
    "symbol": "bag",
    "equals": "50 kg",
    "source_id": "<source id>",
    "dated": "2026-11-02",
}

_DEFINE_UNIT_DOC = f"""Define a unit for this project, such as a bag, a trip or a day, with the \
source that sets its size. SI units (m, m2, m3, kg, t, L, h...) are built in; a currency is never \
a unit (an exchange rate is a ledger number with a unit like EGP/USD).
- symbol: the unit as written in numbers and formulas.
- equals: a positive exact number and a unit, e.g. "50 kg" or "2 bag".
- source_id, dated: the Source Ledger source and its date.
- reason: needed to change a unit already defined; the old size is kept.
Example:
{_json(_DEFINE_UNIT_EXAMPLE)}"""

_EXPLAIN_EXAMPLE = {"number": "<number id>"}

_EXPLAIN_DOC = f"""Explain where a ledger number comes from: its item, its source and date, and, \
when it was calculated, the formula, each input with its own source and date, the constants and \
the steps. An input that was itself calculated can be explained in turn. stale says whether a \
correction made it out of date.
- number: the number id.
- page: inputs and steps come 50 to a page; default 1.
Example:
{_json(_EXPLAIN_EXAMPLE)}"""

_RECALCULATE_EXAMPLE = {"apply": False}

_RECALCULATE_DOC = f"""List the calculated numbers that are out of date because an input was \
corrected or the matching items changed, with why, in the order they will be recalculated. \
Then send apply true to recalculate them in that order: each is a correction with a reason, and \
the old values are kept. A number the engineer corrected by hand is never recalculated over.
- apply: false lists, true recalculates.
- only: with apply, these calculation ids (and what they need first).
Example:
{_json(_RECALCULATE_EXAMPLE)}"""


@dataclass(frozen=True)
class Tool:
    name: str
    doc: str  # English, for the model: at most 250 words, holding `example`
    description: dict[str, str]  # {en, ar}, for the engineer
    request: type[BaseModel]
    example: dict  # the doc's example as data; "<…>" placeholders are filled in tests
    run: Callable[[Records, BaseModel, str], dict]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "calculate",
            _CALCULATE_DOC,
            copy.CALC_TOOL_CALCULATE,
            CalcRequest,
            _CALCULATE_EXAMPLE,
            calculate,
        ),
        Tool(
            "define_unit",
            _DEFINE_UNIT_DOC,
            copy.CALC_TOOL_DEFINE_UNIT,
            UnitRequest,
            _DEFINE_UNIT_EXAMPLE,
            define_unit,
        ),
        Tool(
            "explain_number",
            _EXPLAIN_DOC,
            copy.CALC_TOOL_EXPLAIN,
            ExplainRequest,
            _EXPLAIN_EXAMPLE,
            explain_number,
        ),
        Tool(
            "recalculate",
            _RECALCULATE_DOC,
            copy.CALC_TOOL_RECALCULATE,
            RecalcRequest,
            _RECALCULATE_EXAMPLE,
            recalculate,
        ),
    )
}


# What to send, by the first part of a refusal's field. Anything else gets the tool's example.

_INPUT_SHAPES = {
    "number": {"number": "<number id>"},
    "item": {"item": "03/02", "name": "rate"},
    "numbers": {"numbers": ["<number id>", "<number id>"]},
    "each": {"each": {"code_prefix": "03/"}, "name": "amount"},
    "constant": {"constant": "5", "unit": "%", "why": "estimator's waste rule"},
}

EXAMPLES: dict[str, dict[str, object]] = {
    "calculate": {
        "inputs": list(_INPUT_SHAPES.values()),
        "item": "03/02",
        "for_each": {"code_prefix": "03/"},
        "result": {"unit": "EGP", "round": {"places": 2, "mode": "half_up"}},
        "save": {"name": "amount", "reason": "priced from the new quote"},
        "skip_missing": True,
    },
    "define_unit": {
        "reason": _DEFINE_UNIT_EXAMPLE | {"equals": "25 kg", "reason": "the new datasheet"},
    },
    "recalculate": {"only": {"apply": True, "only": ["<calculation id>"]}},
}


def _example(tool: Tool, field: str | None, payload) -> str:
    parts = (field or "").split(".")
    if tool.name == "calculate" and parts[0] == "inputs" and len(parts) > 1:
        sent = payload.get("inputs", {}).get(parts[1]) if isinstance(payload, dict) else None
        if isinstance(sent, dict):
            for key, shape in _INPUT_SHAPES.items():
                if key in sent:
                    return _json(shape)
    return _json(EXAMPLES.get(tool.name, {}).get(parts[0], tool.example))


_UNION_TAGS = {member.__name__ for member in get_args(InputSpec)}


def _field(loc: tuple) -> str:
    """A pydantic error's place as the request field, without union member tags or `[key]`."""
    parts: list[str] = []
    for part in loc:
        if part == "[key]" or (len(parts) == 2 and parts[0] == "inputs" and part in _UNION_TAGS):
            break
        if part in ("str", "int", "bool") and len(parts) >= 2 and parts[-2] == "where":
            break
        parts.append(str(part))
    return ".".join(parts)


def _key(text: dict) -> str | None:
    """The copy.py name of an unfilled text."""
    return next((k for k, v in vars(copy).items() if v is text), None)


def _refusal(tool: Tool, e: RecordsError, payload) -> dict:
    values = e.values if isinstance(e, CalcError) else {}
    reply = {
        "error": e.text,
        "key": e.key if isinstance(e, CalcError) else _key(e.text),
        "field": e.field,
        "example": values.get("example") or _example(tool, e.field, payload),
    }
    for k, v in values.items():
        reply.setdefault(k, v if isinstance(v, str | int | bool | None) else str(v))
    return reply


def call(rec: Records, tool: str, payload: dict, *, actor: str) -> dict:
    """Runs `tool` on `payload`. A refusal comes back as data, never as an exception."""
    found = TOOLS[tool]
    try:
        try:
            req = found.request.model_validate(payload)
        except ValidationError as e:
            field = _field(e.errors()[0]["loc"])
            raise CalcError(
                "CALC_REQUEST_SHAPE",
                field=field or tool,
                example=_example(found, field, payload),
            ) from None
        return found.run(rec, req, actor)
    except RecordsError as e:
        return _refusal(found, e, payload)
