"""Sources: whether a number is where its source says it is, and its unit there."""

import json
import re

from qsone.engine import numbers_guard
from qsone.records import boq

# Sources: is the number where its source says? ------------------------------------------------

_PLACE_KEYS = ("page", "sheet", "row", "line", "paragraph", "table", "layer")


def texts_at(conn, file_id: str, locator: dict) -> list[str] | None:
    """The file's text at `locator` (its passages there), or None when the locator names no
    place this check reads (a column only, a log id)."""
    place = {k: v for k, v in locator.items() if k in _PLACE_KEYS}
    if not place:
        return None
    if "sheet" in place:
        matched = boq.source_sheet(conn, file_id, place["sheet"])
        if matched is None:
            return []
        place["sheet"] = matched
    where = " AND ".join(f"json_extract(locator, '$.{k}') = ?" for k in place)
    rows = conn.execute(
        f"SELECT text FROM chunks WHERE file_id = ? AND {where} ORDER BY id",
        (file_id, *place.values()),
    ).fetchall()
    return [t for (t,) in rows]


def file_text(conn, file_id: str) -> str:
    return "\n".join(
        t for (t,) in conn.execute("SELECT text FROM chunks WHERE file_id = ?", (file_id,))
    )


def value_at(conn, source_id: str, value: str) -> tuple[bool, str, list[str]] | None:
    """Whether `value` is in the text its file source points at: (found, where in words, the
    numbers that place has). None when the source is not a place in a file, or the place has no
    text to read (a scanned page): nothing to check against."""
    row = conn.execute("SELECT file_id, locator, kind FROM sources WHERE id = ?", (source_id,))
    row = row.fetchone()
    if row is None or row[0] is None:
        return None
    file_id, locator, kind = row
    if kind in ("calculation", "sandbox", "web", "prices", "engineer", "connector"):
        return None
    return value_in(conn, file_id, json.loads(locator), value)


def value_in(conn, file_id: str, place: dict, value: str) -> tuple[bool, str, list[str]] | None:
    """`value_at` for a file and a place in it."""
    texts = texts_at(conn, file_id, place)
    if not texts:
        return None
    (name,) = conn.execute("SELECT name FROM files WHERE id = ?", (file_id,)).fetchone() or ("",)
    wanted = numbers_guard.known_values([value])
    have = numbers_guard.known_values(texts)
    where = ", ".join(f"{k} {place[k]}" for k in _PLACE_KEYS if k in place)
    shown = sorted(have, key=lambda v: (len(v), v))[:12]
    return bool(wanted) and wanted <= have, f"{name}, {where}", shown


# A number's unit: «0.2 %» lost "per day" (the delay damages, Brissa, 6 Nov 2026).
_PER_DAY = re.compile(
    r"\bper\s+(?:calendar\s+)?day\b|\bdaily\b|\ba\s+day\b|يومي[اًا]?|يوميا|عن\s+كل\s+يوم"
    r"|في\s+اليوم|لكل\s+يوم|كل\s+يوم|/\s*(?:day|يوم)",
    re.I,
)
_NEAR = 60  # characters after a number where its "per day" is written


def per_day(texts: list[str], value: str) -> bool:
    """Whether the texts write `value` as so much per day («0.2% of the price per day»)."""
    wanted = numbers_guard.known_values([value])
    for text in texts:
        for m in numbers_guard._ANY_NUMBER.finditer(text):
            if numbers_guard.known_values([m.group()]) != wanted:
                continue
            after = text[m.end() : m.end() + _NEAR]
            stop = re.search(r"[0-9٠-٩]", after)  # up to the next number
            if _PER_DAY.search(after[: stop.start()] if stop else after):
                return True
    return False


def says_per_day(text: str) -> bool:
    return bool(_PER_DAY.search(text or ""))


def per_day_at(conn, source_id: str, value: str) -> bool:
    """Whether the place a file source cites writes `value` as so much per day."""
    row = conn.execute("SELECT file_id, locator FROM sources WHERE id = ?", (source_id,))
    row = row.fetchone()
    if row is None or row[0] is None:
        return False
    return per_day(texts_at(conn, row[0], json.loads(row[1])) or [], value)
