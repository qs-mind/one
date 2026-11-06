"""Template Data Sheets: the base template of each kind, and the checks on what the Lead QS picks.

A Sheet column says where its cells come from with one small grammar: `code`, `field:<key>`,
`number:<name>` or `number:<name>.unit`. A calculated column names a formula of the row's numbers,
which the QS Calc Engine's own parser reads; nothing here evaluates anything. A Document is a list
of block nodes of the allowed types, with `num` and `cell` inline references for its numbers.
"""

import copy as _copy
import json
import re
from functools import cache
from importlib.resources import files
from typing import Literal

from qsone import copy
from qsone.deliverables import calc
from qsone.records.project import RecordsError

KINDS = ("sheet", "document", "pack")
_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}")
_NAME = r"[^\W\d]\w{0,63}"
_FROM = re.compile(rf"code|field:(?P<field>{_NAME})|number:(?P<number>{_NAME})(?P<unit>\.unit)?")
_CURRENCY_OF = re.compile(rf"currency_of:(?P<name>{_NAME})")
_COLUMN_KEYS = {
    *("key", "label", "from", "frozen", "edit", "wrap", "width", "empty_from", "calc", "total")
}
WIDTH = 120  # a column's width when the template gives none


@cache
def _load(kind: str) -> str:
    return (files("qsone.deliverables") / "templates" / f"{kind}.json").read_text("utf-8")


def base(kind: Literal["sheet", "document", "pack"]) -> dict:
    """The base Template Data Sheet of `kind`, a fresh copy. TEMPLATE_UNKNOWN for any other."""
    if kind not in KINDS:
        raise RecordsError(copy.TEMPLATE_UNKNOWN, status=422, field="kind")
    return json.loads(_load(kind))


def source_of(column: dict) -> dict:
    """A checked column's `from`, read: {"code": True} or {"field": key} or {"number": name,
    "unit": bool}."""
    found = _FROM.fullmatch(column["from"])
    if found["field"]:
        return {"field": found["field"]}
    if found["number"]:
        return {"number": found["number"], "unit": bool(found["unit"])}
    return {"code": True}


def kind_of(column: dict) -> str:
    """`text`, `number` or `calc`."""
    if "calc" in column:
        return "calc"
    found = source_of(column)
    return "number" if "number" in found and not found["unit"] else "text"


def columns_for(spec: list[dict] | None) -> list[dict]:
    """The Sheet's columns: the defaults for None, else `spec` checked column by column.

    Each refusal is COLUMN_NOT_ALLOWED with the field that is wrong (`columns[2].from`)."""
    if spec is None:
        return base("sheet")["default_columns"]
    if not isinstance(spec, list) or not spec:
        raise _column("columns")
    columns = [_checked(column, i) for i, column in enumerate(spec)]
    keys: set[str] = set()
    for i, column in enumerate(columns):
        if column["key"] in keys:
            raise _column(f"columns[{i}].key")
        keys.add(column["key"])
    numbers = {source_of(c)["number"] for c in columns if kind_of(c) == "number"}
    for i, column in enumerate(columns):
        if "calc" in column:
            _check_calc(column, i, numbers)
    return columns


def _column(field: str) -> RecordsError:
    return RecordsError(copy.COLUMN_NOT_ALLOWED, status=422, field=field)


def _checked(column, i: int) -> dict:
    at = f"columns[{i}]"
    if not isinstance(column, dict) or set(column) - _COLUMN_KEYS:
        raise _column(at)
    if not (isinstance(column.get("key"), str) and _KEY.fullmatch(column["key"])):
        raise _column(f"{at}.key")
    if not (isinstance(column.get("from"), str) and _FROM.fullmatch(column["from"])):
        raise _column(f"{at}.from")
    label = column.get("label")
    if not (
        isinstance(label, dict)
        and set(label) == {"en", "ar"}
        and all(isinstance(t, str) and t.strip() for t in label.values())
    ):
        raise _column(f"{at}.label")
    for flag in ("frozen", "edit", "wrap"):
        if not isinstance(column.get(flag, False), bool):
            raise _column(f"{at}.{flag}")
    width = column.get("width", WIDTH)
    if not (isinstance(width, int) and not isinstance(width, bool) and 20 <= width <= 2000):
        raise _column(f"{at}.width")
    empty_from = column.get("empty_from")
    if empty_from is not None and not (isinstance(empty_from, str) and _field_only(empty_from)):
        raise _column(f"{at}.empty_from")
    if ("calc" in column or "total" in column) and not _plain_number(column):
        raise _column(f"{at}.from")
    if "calc" in column and column.get("edit"):
        raise _column(f"{at}.edit")
    if "total" in column and "calc" not in column:
        raise _column(f"{at}.total")
    return _copy.deepcopy(column)


def _field_only(text: str) -> bool:
    found = _FROM.fullmatch(text)
    return bool(found and found["field"])


def _plain_number(column: dict) -> bool:
    found = source_of(column)
    return "number" in found and not found["unit"]


def _check_calc(column: dict, i: int, numbers: set[str]) -> None:
    at = f"columns[{i}]"
    spec = column["calc"]
    if not (isinstance(spec, dict) and set(spec) == {"formula", "unit"}):
        raise _column(f"{at}.calc")
    if not isinstance(spec["formula"], str):
        raise _column(f"{at}.calc.formula")
    try:
        used = calc.formula_names(spec["formula"])
    except RecordsError:
        raise _column(f"{at}.calc.formula") from None
    if not used or not used <= numbers:
        raise _column(f"{at}.calc.formula")
    unit = _CURRENCY_OF.fullmatch(spec["unit"]) if isinstance(spec["unit"], str) else None
    if unit is None or unit["name"] not in used:
        raise _column(f"{at}.calc.unit")
    if "total" in column:
        total = column["total"]
        name = source_of(column)["number"]
        if not (
            isinstance(total, dict)
            and set(total) == {"formula", "unit"}
            and isinstance(total["formula"], str)
            and re.fullmatch(rf"\s*sum\(\s*{re.escape(name)}\s*\)\s*", total["formula"])
        ):
            raise _column(f"{at}.total.formula")
        if total["unit"] != spec["unit"]:
            raise _column(f"{at}.total.unit")


def check_node(node: dict) -> None:
    """A Document block: allowed element types, text leaves with allowed marks, `num` and `cell`
    references with their own keys and an empty text child; no other key anywhere.

    Raises NODE_NOT_ALLOWED (the caller names the field)."""
    doc = base("document")
    blocks, inlines, marks = set(doc["nodes"]), doc["inlines"], set(doc["marks"])
    stack = [(node, True)]
    while stack:
        current, top = stack.pop()
        if not isinstance(current, dict):
            raise _node()
        if "text" in current and "type" not in current:
            if top or set(current) - {"text"} - marks or not isinstance(current["text"], str):
                raise _node()
            if any(current[m] is not True for m in set(current) & marks):
                raise _node()
            continue
        kind, children = current.get("type"), current.get("children")
        if not isinstance(children, list) or not children:
            raise _node()
        if kind in inlines and not top:
            keys = set(inlines[kind])
            if set(current) != keys | {"type", "children"}:
                raise _node()
            if not all(isinstance(current[k], str) and current[k] for k in keys):
                raise _node()
            if children != [{"text": ""}]:
                raise _node()
            continue
        if kind not in blocks or set(current) - {"type", "children", "id"}:
            raise _node()
        if "id" in current and not isinstance(current["id"], str):
            raise _node()
        stack += [(child, False) for child in children]


def _node() -> RecordsError:
    return RecordsError(copy.NODE_NOT_ALLOWED, status=422)
