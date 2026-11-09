"""Citations in a reply's words: the places it cites and whether each number is there."""

import json
import re
from dataclasses import dataclass

from qsone import copy
from qsone.engine import numbers_guard
from qsone.engine.truth.problem import Problem
from qsone.engine.truth.sources import per_day, says_per_day
from qsone.engine.truth.words import _DIGITS

# Citations in a reply's words: is each number where the reply says it is? --------------------
#
# The real walk (6 Nov 2026): «السعر 12 جنيه/م3 (من شيت "تسعير"، صف 16)» for an item the BOQ does
# not have, ceramic 72 cited to row 18 (a different, empty item), the retention limit to page 59
# (it is on page 58); and the bid security «350,000 دولار … الصفحة: 26» marked "no source yet"
# although page 26 has it.

_Q = "\"'«»“”‘’"
_SHEET_ROW = re.compile(
    rf"(?:شيت|الشيت|ورق[ةه]|الورق[ةه]|sheet)\s*[:：]?\s*[{_Q}]?(?P<sheet>[^{_Q}\n،,()\[\]:]{{1,40}}?)"
    rf"[{_Q}]?\s*[،,]?\s*(?:في\s+)?(?:صف|الصف|سطر|row)\s*[:：]?\s*"
    r"(?P<rows>[0-9٠-٩]+(?:\s*(?:[/،,-]|و)\s*[0-9٠-٩]+)*)",
    re.I,
)
_ROW_SHEET = re.compile(  # "row 8 of sheet Electrical"
    rf"\brow\s*(?P<rows>[0-9]+(?:\s*[/,-]\s*[0-9]+)*)\s+(?:of|in|on)\s+(?:the\s+)?sheet\s*"
    rf"[{_Q}]?(?P<sheet>[^{_Q}\n,()\[\]:]{{1,40}}?)[{_Q}]?(?=[\s,.;)]|$)",
    re.I,
)
_PAGE = re.compile(
    r"(?<![؀-ۿ\w])(?:صفح[ةه]|الصفح[ةه]|ص\.|page|pages|pp?\.)\s*[:：]?\s*(?P<pages>[0-9٠-٩]+"
    r"(?:\s*(?:[/،,-]|و)\s*[0-9٠-٩]+)*)"
    r"|\((?:p|pp)\.?\s*(?P<pp>[0-9]+)",
    re.I,
)
_BARE_ROW = re.compile(
    r"(?<!\w)(?:row|الصف|صف|السطر|سطر)\s*[:：]?\s*(?P<rows>[0-9٠-٩]+)",
    re.I,
)
# A segment: a line, or a sentence of one; a decimal point («0.2», «17.1») never ends one.
_SEGMENT = re.compile(r"(?<=[!?؟])\s+|(?<=\.)(?![0-9])\s+|\n+")
_NUMS = re.compile(r"[0-9٠-٩]+")


@dataclass(frozen=True)
class Place:
    """A place a reply cites: a sheet's rows, or pages."""

    sheet: str | None
    rows: tuple[int, ...] = ()
    pages: tuple[int, ...] = ()
    file_name: str | None = None

    def words(self) -> dict:
        if self.sheet == "":
            rows = "/".join(map(str, self.rows))
            return {"en": f"row {rows}", "ar": f"صف {rows}"}
        if self.sheet is not None:
            rows = "/".join(map(str, self.rows))
            return {
                "en": f"sheet «{self.sheet}», row {rows}",
                "ar": f"شيت «{self.sheet}»، صف {rows}",
            }
        pages = "/".join(map(str, self.pages))
        return {"en": f"page {pages}", "ar": f"صفحة {pages}"}


def _numbers_of(text: str) -> tuple[int, ...]:
    return tuple(int(n.translate(_DIGITS)) for n in _NUMS.findall(text))


def citations(text: str) -> list[tuple[str, list[Place], list[tuple[str, str]]]]:
    """Citations beside values, above a list, or in an explicit trailing Source line.

    A new citation ends the previous scope. A trailing Source line applies only to the
    preceding uncited lines, never across another citation. Markdown emphasis is presentation.
    """
    from qsone.records.arabic import clean

    text = clean(text or "")
    segments = _SEGMENT.split(re.sub(r"[*`]+", "", text or ""))
    parsed = []
    last_file = None
    for segment in segments:
        places: list[Place] = []
        blank = segment
        for pattern in (_SHEET_ROW, _ROW_SHEET):
            for m in pattern.finditer(segment):
                places.append(Place(m["sheet"].strip(), rows=_numbers_of(m["rows"])))
                blank = blank.replace(m[0], " " * len(m[0]))
        for m in _PAGE.finditer(blank):
            places.append(Place(None, pages=_numbers_of(m["pages"] or m["pp"])))
            blank = blank.replace(m[0], " " * len(m[0]))
        for m in _BARE_ROW.finditer(blank):
            places.append(Place("", rows=_numbers_of(m["rows"])))
            blank = blank.replace(m[0], " " * len(m[0]))
        filenames = list(
            re.finditer(
                r"(?:^|[:،,(]|\band\s+)(?:\s*)[«\"']?([\w-]+(?:[ \t]+[\w-]+)*"
                r"\.(?:pdf|xlsx?|docx?|csv|txt|dwg|dxf))\b",
                segment,
                re.I,
            )
        )
        page_matches = list(_PAGE.finditer(segment))
        assigned = []
        page_index = 0
        for place in places:
            position = len(segment)
            if place.sheet is None:
                position = page_matches[page_index].start()
                page_index += 1
            preceding = [m for m in filenames if m.start() < position]
            filename = re.sub(r"^and\s+", "", preceding[-1][1], flags=re.I) if preceding else None
            if filename is None and re.search(r"\bsame\b|نفس الملف|نفس المصدر", segment, re.I):
                filename = last_file
            assigned.append(Place(place.sheet, place.rows, place.pages, filename))
        places = assigned
        if filenames:
            last_file = re.sub(r"^and\s+", "", filenames[-1][1], flags=re.I)
        blank = re.sub(r"(?:article|clause|المادة|مادة)\s+\d+", "", blank, flags=re.I)
        parsed.append([segment, places, list(numbers_guard._counted(blank))])
    active = []
    pending = []
    for entry in parsed:
        segment, places, numbers = entry
        if places:
            if re.match(r"\s*(?:source|المصدر)\s*[:：]", segment, re.I):
                for prior in pending:
                    prior[1] = places
            active = places
            pending = []
        elif active:
            entry[1] = active
            pending.append(entry)
        else:
            pending.append(entry)
    return [(segment, places, numbers) for segment, places, numbers in parsed if places]


def _sheet_names(conn) -> dict[str, list[str]]:
    """{normalised name: [names as written]} of the current files' sheets."""
    from qsone.records.arabic import normalise

    rows = conn.execute(
        "SELECT DISTINCT json_extract(c.locator, '$.sheet') FROM chunks c JOIN files f"
        " ON f.id = c.file_id WHERE f.valid_until IS NULL"
        " AND json_extract(c.locator, '$.sheet') IS NOT NULL"
    ).fetchall()
    out: dict[str, list[str]] = {}
    for (name,) in rows:
        out.setdefault(normalise(str(name)), []).append(str(name))
    return out


def _sheet_of(conn, cited: str) -> list[str]:
    """The sheets a cited name names: the same name, trimmed and folded; else the one sheet whose
    name holds it, or that it holds."""
    from qsone.records.arabic import normalise

    names = _sheet_names(conn)
    key = normalise(cited)
    if key in names:
        return names[key]
    near = [n for k, ns in names.items() if key and (key in k or k in key) for n in ns]
    return near if len(near) == 1 else []


def place_text(conn, place: Place) -> list[str] | None:
    """The current files' text at `place`; None when no file has that place."""
    if place.sheet == "":
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.line') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(list(place.rows)),),
        ).fetchall()
        return [t for (t,) in rows] or None
    if place.sheet is not None:
        sheets = _sheet_of(conn, place.sheet)
        if not sheets:
            return None
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.sheet') IN"
            " (SELECT value FROM json_each(?)) AND json_extract(c.locator, '$.row') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(sheets), json.dumps(list(place.rows))),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id"
            " WHERE f.valid_until IS NULL AND json_extract(c.locator, '$.page') IN"
            " (SELECT value FROM json_each(?))",
            (json.dumps(list(place.pages)),),
        ).fetchall()
    return [t for (t,) in rows] or None


_ITEM_CODE = re.compile(
    r"(?:(?<![؀-ۿ])(?:بند|البند)\s*(?:رقم\s*)?|\bitem\s+(?:no\.?\s*)?)"
    r"(?P<code>[0-9٠-٩A-Za-z][0-9٠-٩A-Za-z./-]*[0-9٠-٩A-Za-z]|[0-9٠-٩])",
    re.I,
)


def _tokens(text: str) -> set[str]:
    return set(re.split(r"[\s|،,:;()«»\"']+", text.translate(_DIGITS)))


def _item_codes(conn, segment: str) -> list[str]:
    """The client BOQ codes a segment names as items («بند 17», "item 03/02")."""
    named = [m["code"].translate(_DIGITS) for m in _ITEM_CODE.finditer(segment)]
    if not named:
        return []
    found = conn.execute(
        "SELECT code FROM items WHERE kind = 'boq_item' AND code IN"
        " (SELECT value FROM json_each(?))",
        (json.dumps(named),),
    ).fetchall()
    return sorted({c for (c,) in found})


def miscited(conn, text: str) -> list[Problem]:
    """Each number a reply gives at a cited place (a sheet's row, a page) that the place does not
    have, and each cited place no project file has. One Problem for the model, with a flag for
    the engineer for each of the first three."""
    wrong: list[tuple[str, dict]] = []  # (the model's line, the engineer's flag)
    for segment, places, numbers in citations(text):
        if not numbers:
            continue
        texts: list[str] = []
        missing = []
        for place in places:
            found = place_text(conn, place)
            if found is None:
                missing.append(place)
            else:
                texts += found
        if missing and not texts:
            for place in missing:
                where = place.words()
                line = f"«{segment[:100]}» cites {where['en']}, which no project file has."
                wrong.append((line, copy.fill(copy.TRUTH_NO_PLACE, place=where)))
            continue
        rows = [p for p in places if p.sheet is not None]
        for code in _item_codes(conn, segment) if rows else ():
            if not any(code in _tokens(t) for t in texts):  # the row of another item
                where = rows[0].words()
                line = (
                    f"«{segment[:100]}» prices item {code} from {where['en']}, which is not "
                    f"item {code}'s row."
                )
                wrong.append((line, copy.fill(copy.TRUTH_OTHER_ROW, code=code, place=where)))
        have = numbers_guard.known_values(texts)
        for written, value in numbers:
            if value in have and per_day(texts, value) and not says_per_day(segment):
                where = places[0].words()
                line = (
                    f"«{segment[:100]}» gives {written} without its unit: {where['en']} has it "
                    "per day. Keep the unit with the number."
                )
                wrong.append((line, copy.fill(copy.TRUTH_PER_DAY, value=written, place=where)))
                continue
            if value in have:
                continue
            where = (
                places[0].words()
                if len(places) == 1
                else copy.listed([p.words()["en"] for p in places])
            )
            shown = sorted(have, key=lambda v: (len(v), v))[:8]
            has = copy.listed(shown) if shown else copy.NO_NUMBERS
            line = f"«{segment[:100]}» gives {written} at {where['en']}, which has {has['en']}."
            flag = copy.fill(copy.TRUTH_MISCITED, value=written, place=where, have=has)
            wrong.append((line, flag))
    guide = (
        " Cite the row or page that has the number (search_records, read_chunk), or say plainly "
        "that ONE has no source for it. An item that is not in the BOQ is not priced as one."
    )
    return [
        Problem("cited", line + (guide if i == 0 else ""), flag)
        for i, (line, flag) in enumerate(wrong[:5])
    ]


def cited_values(conn, text: str) -> set[str]:
    """Every number at the places a reply cites (normalised): a number read from a cited page
    carries that source."""
    found: set[str] = set()
    for _, places, _ in citations(text):
        for place in places:
            found |= numbers_guard.known_values(place_text(conn, place) or [])
    return found
