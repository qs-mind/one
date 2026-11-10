"""Tool results that say where they came from and when (Plan 5, decision 4), in one form:

    <text>
    data: {JSON, numbers as exact decimal text}
    <notes, one a line>
    defaults used: pages=[3, 4, 5] (from "٣-٥")
    sources:
    - web:7f2c… | Rebar prices - sample | https://… | dated 2026-10-30 (page) | read 2026-11-05
    more: call files_read {"file_id": "…", "pages": "6-10"}

A result stays inside one page of Plan 4's tool layer: when it is too long, the text is cut and
everything after it (the data, the notes, the sources, `more`) is kept whole. A failure of the
world (no internet, a site down) is a result too (`not_done`), never an error, so it never uses
up the model's retries. Results are English, for the model; the engineer's words are in `copy`."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from qsone.engine.tools import MAX_RESULT

LIMIT = MAX_RESULT - 512  # bytes: the room Plan 4 leaves for the data fence and its own note
CUT = "…"


@dataclass(frozen=True)
class SourceRef:
    """One source line. `ref` is typed text: `file:<id>#page=3`, `file:<id>#sheet=BOQ&row=41`,
    `web:<log id>`, `prices:EG/<item id>@<day>`, `card:<id>`, `sandbox:<run id>`,
    `connector:<name>/<call id>`. `read` is when One read it; `dated` the day the fact is true
    for (None: "no date", said plainly)."""

    ref: str
    title: str
    read: str
    dated: str | None = None
    link: str | None = None
    # box: [x0, y0, x1, y1], PDF points, origin top-left; page is one-based.
    locator: dict | None = None


def _exact(value):
    """`value` with every Decimal as exact text. A float is refused: it is not exact."""
    if isinstance(value, bool) or value is None or isinstance(value, int | str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        raise TypeError("a number in a tool result is exact decimal text, never a float")
    if isinstance(value, dict):
        return {str(k): _exact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_exact(v) for v in value]
    raise TypeError(f"{type(value).__name__} is not plain data")


def _one_line(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "/")


def _json(value) -> str:
    return json.dumps(_exact(value), ensure_ascii=False)


def source_line(source: SourceRef) -> str:
    locator = source.locator
    if locator and "box" in locator:
        # Geometry may be fractional; money and quantities still pass _exact.
        checked = _exact({k: v for k, v in locator.items() if k != "box"})
        checked["box"] = locator["box"]
        where = source.link or json.dumps(checked, ensure_ascii=False, allow_nan=False)
    else:
        where = source.link or (_json(locator) if locator else None)
    parts = [source.ref, _one_line(source.title)]
    if where:
        parts.append(_one_line(where))
    parts.append(f"dated {_one_line(source.dated)}" if source.dated else "no date")
    parts.append(f"read {source.read}")
    return "- " + " | ".join(parts)


def _cut(text: str, room: int) -> str:
    data = text.encode()
    if len(data) <= room:
        return text
    end = max(room - len(CUT.encode()), 0)
    while end and (data[end] & 0xC0) == 0x80:  # never inside a character
        end -= 1
    return data[:end].decode() + CUT


def render(
    text: str,
    *,
    sources: Sequence[SourceRef] = (),
    data: object = None,
    notes: Sequence[str] = (),
    defaults_used: dict | None = None,
    more: str | None = None,
    last: Sequence[str] = (),
) -> str:
    """The result text: `text`, then each part given, `last` at the very end, at most `LIMIT`
    bytes in all. Raises `TypeError` for a float (or anything but plain data) in `data`."""
    tail = []
    if data is not None:
        tail.append(f"data: {_json(data)}")
    tail += [_one_line(n) for n in notes]
    if defaults_used:
        said = ", ".join(
            f"{k}={v if isinstance(v, str) else _json(v)}" for k, v in defaults_used.items()
        )
        tail.append(f"defaults used: {said}")
    if sources:
        tail += ["sources:", *(source_line(s) for s in sources)]
    if more:
        tail.append(f"more: {more}")
    tail += [_one_line(n) for n in last]
    end = "\n".join(tail)
    room = LIMIT - len(end.encode()) - 1
    body = text.rstrip("\n")
    if len(body.encode()) > room and not more:
        end += "\n[cut at 8 KB: ask for less]"
        room -= 28
    out = _cut(body, max(room, 0)) + ("\n" + end if end else "")
    return _cut(out, LIMIT)


def not_done(text: dict, *, retry_online: bool = False, instead: str | None = None) -> str:
    """A failure of the world as a normal result: `not done: <English>`, then `retry: when
    online` when that applies, and what can still be done."""
    lines = [f"not done: {text['en']}"]
    if retry_online:
        lines.append("retry: when online")
    if instead:
        lines.append(f"instead: {instead}")
    return "\n".join(lines)
