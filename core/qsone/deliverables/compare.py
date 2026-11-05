"""Comparing two views of one Deliverable: Saved versions, Revisions, or one of each.

Sheets are compared by part id and column, Documents by block id and then word by word, so the
screen only paints what the core found. Words are split on white space and the spaces are kept,
so an Arabic word is never split by letter. Nothing here reads Project Records.
"""

import re
from difflib import SequenceMatcher

from qsone.deliverables import store

_WORDS = re.compile(r"(\s+)")


def block_text(node: dict, refs: dict | None = None) -> str:
    """A block's text: its text leaves joined in order. With a view's `refs`, a number reference
    shows its value; without, it adds nothing."""
    out, stack = [], [node]
    while stack:
        current = stack.pop()
        key = store.ref_key(current) if refs is not None else None
        if key is not None:
            out.append(refs.get(key, {}).get("value", ""))
        elif "type" not in current:
            out.append(current.get("text", ""))
        else:
            stack.extend(reversed(current.get("children", [])))
    return "".join(out)


def segments(a: str, b: str) -> list[dict]:
    """Word-level difference from `a` to `b`: [{"op": "same" | "del" | "ins", "text"}], with
    neighbours of the same kind joined."""
    ta = [t for t in _WORDS.split(a) if t]
    tb = [t for t in _WORDS.split(b) if t]
    out: list[dict] = []

    def put(op: str, tokens: list[str]) -> None:
        if not tokens:
            return
        if out and out[-1]["op"] == op:
            out[-1]["text"] += "".join(tokens)
        else:
            out.append({"op": op, "text": "".join(tokens)})

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag == "equal":
            put("same", ta[i1:i2])
        else:
            put("del", ta[i1:i2])
            put("ins", tb[j1:j2])
    return out


def _order(a_ids: list[str], b_ids: list[str]) -> tuple[list[str], set[str]]:
    """The ids in `b`'s order, each removed one placed after the one it followed in `a`; and the
    ids found in both whose order changed."""
    in_a, in_b = set(a_ids), set(b_ids)
    common_a = [i for i in a_ids if i in in_b]
    common_b = [i for i in b_ids if i in in_a]
    stayed: set[str] = set()
    for block in SequenceMatcher(None, common_a, common_b, autojunk=False).get_matching_blocks():
        stayed |= set(common_a[block.a : block.a + block.size])
    order = list(b_ids)
    previous = None
    for i in a_ids:
        if i not in in_b:
            order.insert(order.index(previous) + 1 if previous else 0, i)
        previous = i
    return order, set(common_a) - stayed


def _change(id_: str, a: dict, b: dict, moved: set[str], differs: bool) -> str:
    if id_ not in a:
        return "added"
    if id_ not in b:
        return "removed"
    return "moved" if id_ in moved else "changed" if differs else "same"


def _cells(row: dict | None) -> dict:
    if row is None:
        return {}
    cells = dict(row["cells"])
    if row["kind"] == "section":
        cells["title"] = {"text": row["title"]}
    return cells


def _sheets(a: dict, b: dict) -> dict:
    rows_a = {r["id"]: r for r in a["rows"]}
    rows_b = {r["id"]: r for r in b["rows"]}
    order, moved = _order(list(rows_a), list(rows_b))
    rows = []
    for id_ in order:
        before, after = _cells(rows_a.get(id_)), _cells(rows_b.get(id_))
        cells = {
            key: {"from": before.get(key), "to": after.get(key)}
            for key in dict.fromkeys([*before, *after])
            if before.get(key) != after.get(key)
        }
        rows.append(
            {"id": id_, "change": _change(id_, rows_a, rows_b, moved, bool(cells)), "cells": cells}
        )
    return {"rows": rows, "total": {"from": a["total"], "to": b["total"]}}


def _documents(a: dict, b: dict) -> dict:
    texts_a = {x["id"]: block_text(x["node"], a["refs"]) for x in a["blocks"]}
    texts_b = {x["id"]: block_text(x["node"], b["refs"]) for x in b["blocks"]}
    order, moved = _order(list(texts_a), list(texts_b))
    blocks = []
    for id_ in order:
        found = segments(texts_a.get(id_, ""), texts_b.get(id_, ""))
        differs = any(s["op"] != "same" for s in found)
        blocks.append(
            {
                "id": id_,
                "change": _change(id_, texts_a, texts_b, moved, differs),
                "segments": found,
            }
        )
    return {"blocks": blocks}


def compare(a: dict, b: dict) -> dict:
    """What changed from view `a` to view `b` of one Deliverable.
    Sheet: {"rows": [{"id", "change", "cells": {key: {"from", "to"}}}], "total": {"from", "to"}};
    Document: {"blocks": [{"id", "change", "segments": [{"op", "text"}]}]}. `change` is added,
    removed, moved, changed or same; `cells` holds only the cells that differ (a section's title
    under "title")."""
    if a["id"] != b["id"] or a["kind"] != b["kind"]:
        raise ValueError("compare takes two views of one Deliverable")
    return _sheets(a, b) if a["kind"] == "sheet" else _documents(a, b)
