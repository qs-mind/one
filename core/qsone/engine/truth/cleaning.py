"""JSON and ONE's insides in a reply: finding them, and the reply as the engineer reads it."""

import json
import re

from qsone import copy
from qsone.engine import numbers_guard
from qsone.engine.truth.blanks import _ID
from qsone.engine.truth.words import _ASK_ENGINEER, _TABLE_ROW, arabic

# JSON a model wrote into its reply: a fenced block, or an object or array on its own lines.
_JSON_FENCE = re.compile(r"```(?:json)?\s*\n?[\[{].*?```", re.S)
_JSON_START = re.compile(r'^\s*(?:\{\s*"|\[\s*[{"])')


def _json_lines(text: str) -> list[tuple[int, int]]:
    """The (start, end) line ranges of the JSON objects and arrays standing on their own lines."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        if not _JSON_START.match(lines[i]):
            i += 1
            continue
        for j in range(i, min(len(lines), i + 200)):
            try:
                json.loads("\n".join(lines[i : j + 1]))
            except ValueError:
                continue
            out.append((i, j + 1))
            i = j
            break
        i += 1
    return out


def has_json(text: str) -> bool:
    return bool(_JSON_FENCE.search(text or "") or _json_lines(text or "") or _ID.search(text or ""))


def clean_reply(text: str, *, shown: bool) -> str:
    """The reply as the engineer reads it: no JSON, no record ids; and, when the Brief showed a
    view, no typed table of numbers beside it (the breakdown showed twice, 6 Nov 2026)."""
    out = _JSON_FENCE.sub("", text or "")
    lines = out.split("\n")
    for start, end in reversed(_json_lines(out)):
        del lines[start:end]
    if shown:
        table = [k for k, line in enumerate(lines) if _TABLE_ROW.fullmatch(line)]
        if len(table) >= 3 and numbers_guard.numbers_in("\n".join(lines[k] for k in table)):
            lines = [line for k, line in enumerate(lines) if k not in set(table)]
    out = _ID.sub("", "\n".join(lines))
    lang = "ar" if arabic(text) else "en"
    from qsone.engine.tools import REGISTRY

    for name in REGISTRY:
        if "_" in name:
            out = re.sub(rf"`?\b{re.escape(name)}\b`?", copy.REPLY_RECORDS[lang], out)
    out = re.sub(r"\bfile\s*(?:id|number)\s*[:：]?\s*(?:`\s*`|[)）])", "", out, flags=re.I)
    out = re.sub(r"ملف\s+رقم\s*[:：]?\s*(?:`\s*`|[)）])", "", out)
    out = re.sub(
        r"(?:The reply left blanks for values:\s*)?\[show\]",
        copy.REPLY_MISSING_VALUE[lang],
        out,
        flags=re.I,
    )
    out = re.sub(r"\b(?:source\s+)?ledger\b|سجل النظام", copy.REPLY_RECORDS[lang], out, flags=re.I)
    out = re.sub(r"أداة العرض\s*\(show\)|\(show\)", copy.REPLY_TABLE[lang], out, flags=re.I)
    out = _ASK_ENGINEER.sub(copy.REPLY_YOUR_QUOTES[lang], out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()
