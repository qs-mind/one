"""Letters: a letter's amounts, dates, terms and bid fields against the project's files."""

import json
import re
from datetime import date

from qsone.engine import numbers_guard
from qsone.engine.truth.sources import _PLACE_KEYS
from qsone.engine.truth.words import _DIGITS

# Letters ---------------------------------------------------------------------------------------

_MONTHS = {
    **{m: i for i, m in enumerate(("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"), 1)},
    **{"ابريل": 4, "اغسطس": 8, "اكتوبر": 10, "يونية": 6, "يولية": 7},
    **{m: i for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july",
                                     "august", "september", "october", "november", "december"), 1)},
}  # fmt: skip
_MONTH_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))
_D = "[0-9٠-٩]"
_DATE_WORDS = re.compile(rf"(?<!{_D})({_D}{{1,2}})\s+({_MONTH_WORDS})\s*،?\s*({_D}{{4}})", re.I)
_DATE_ISO = re.compile(rf"(?<!{_D})({_D}{{4}})-({_D}{{2}})-({_D}{{2}})(?!{_D})")
_DATE_SLASH = re.compile(rf"(?<!{_D})({_D}{{1,2}})/({_D}{{1,2}})/({_D}{{4}})(?!{_D})")


def _n(text: str) -> int:
    return int(text.translate(_DIGITS))


def dates_in(text: str) -> list[tuple[str, date]]:
    """Each date written in `text` (6 نوفمبر 2026, 2026-11-06, 06/11/2026), as written."""
    found: list[tuple[str, date]] = []
    for m in _DATE_WORDS.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[3]), _MONTHS[m[2].lower()], _n(m[1]))))
        except ValueError:
            continue
    for m in _DATE_ISO.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[1]), _n(m[2]), _n(m[3]))))
        except ValueError:
            continue
    for m in _DATE_SLASH.finditer(text or ""):
        try:
            found.append((m.group(0), date(_n(m[3]), _n(m[2]), _n(m[1]))))
        except ValueError:
            continue
    return found


# Terms a tender's files state, each found by its words and the number after them.
TERMS = {
    "validity": re.compile(
        r"(?:مد[ةه]\s+)?(?:سريان|صلاحي[ةه])(?:\s+(?:ال)?عرض)?|\bvalid(?:ity)?(?:\s+for)?\b", re.I
    ),
    "vat": re.compile(r"ضريب[ةه]\s+(?:ال)?قيم[ةه]\s+(?:ال)?مضاف[ةه]|\bvat\b", re.I),
    "retention": re.compile(r"(?:ال)?محتجزات|(?:ال)?استقطاع|\bretention\b", re.I),
}
# The unit each term's number takes: days for a validity, a percentage for VAT and retention.
_DAYS = r"(?:يوم|أيام|ايام|يوما|يوماً|days?)"
_PERCENT = r"(?:%|٪|في\s+المي[ةه]|percent)"
_TERM_UNIT = {"validity": _DAYS, "vat": _PERCENT, "retention": _PERCENT}


def _term_values(text: str, term: str) -> list[str]:
    """The numbers stated right after each mention of the term in `text`, on the same line and
    within 40 letters, with the term's unit."""
    number = re.compile(rf"({_D}+(?:[.٫]{_D}+)?)\s*{_TERM_UNIT[term]}", re.I)
    out: list[str] = []
    for m in TERMS[term].finditer(text or ""):
        window = text[m.end() : m.end() + 40].split("\n", 1)[0]
        found = number.search(window)
        if found:
            out += [v for v in numbers_guard.known_values([found.group(1)]) if v not in out]
    return out


def file_terms(conn) -> dict[str, list[tuple[str, str]]]:
    """{term: [(value, where in words)]} that the project's current files state."""
    found: dict[str, list[tuple[str, str]]] = {}
    rows = conn.execute(
        "SELECT f.name, c.locator, c.text FROM chunks c JOIN files f ON f.id = c.file_id"
        " WHERE f.valid_until IS NULL ORDER BY c.id"
    ).fetchall()
    for name, locator, text in rows:
        place = json.loads(locator)
        where = ", ".join(f"{k} {place[k]}" for k in _PLACE_KEYS if k in place)
        for term in TERMS:
            for value in _term_values(text, term):
                found.setdefault(term, []).append((value, f"{name}, {where}".rstrip(", ")))
    return found


def file_dates(conn) -> set[date]:
    """Every date the project's current files write."""
    rows = conn.execute(
        "SELECT c.text FROM chunks c JOIN files f ON f.id = c.file_id WHERE f.valid_until IS NULL"
    ).fetchall()
    return {d for (t,) in rows for _, d in dates_in(t)}


_TOTAL = re.compile(r"إجمالي|اجمالي|قيم[ةه]\s+العطاء|\btotal\b|\bsum\b", re.I)


def letter_problems(conn, text: str, *, day: date, has_total: bool, said: str = "") -> list[str]:
    """What a letter says against the project's files and today's date (English, for the model).
    A date the engineer wrote (`said`, the Brief's text) is theirs to use."""
    wrong: list[str] = []
    amounts = conn.execute(
        "SELECT value FROM numbers WHERE valid_until IS NULL AND currency IS NOT NULL"
    ).fetchall()
    known_amounts = numbers_guard.known_values([v for (v,) in amounts])
    for segment in re.split(r"[\n؛;]", text):
        for match in numbers_guard._ANY_NUMBER.finditer(segment):
            tail = segment[match.end() :].lstrip()
            before = segment[: match.start()]
            # Only monetary figures: a total label immediately before the number or a
            # currency immediately beside it. Days, percentages and dates are separate facts.
            currency = r"(?:جنيه|ريال|درهم|دولار|EGP|SAR|USD|AED|[$€£])"
            money = re.match(currency, tail, re.I) or re.search(currency + r"\s*$", before, re.I)
            total = re.search(
                r"(?:إجمالي|اجمالي|قيم[ةه] العطاء|total|sum)[^0-9٠-٩،,;\n]{0,25}$", before, re.I
            )
            if not (money or total) or re.match(r"%|٪|days?\b|يوم", tail, re.I):
                continue
            written = match.group()
            if written not in numbers_guard.numbers_in(segment):
                continue
            if numbers_guard.known_values([written]) - known_amounts:
                wrong.append(
                    f"The letter amount {written} is not in the project records. "
                    "Read the BOQ total from calculate and use its number reference; "
                    "if missing, use [يملأه المهندس: إجمالي العطاء]."
                )
    known_dates = file_dates(conn) | {d for _, d in dates_in(said)}
    for written, d in dates_in(text):
        if d != day and d not in known_dates:
            wrong.append(
                f"The date «{written}» is not today ({day.isoformat()}, Cairo) and no project "
                "file states it: date the letter today."
            )
    terms = file_terms(conn)
    for term in TERMS:
        stated = terms.get(term, [])
        said = _term_values(text, term)
        if stated and said:
            values = {v for v, _ in stated}
            for v in said:
                if v not in values:
                    places = "; ".join(f"{s} ({w})" for s, w in stated[:3])
                    wrong.append(
                        f"The letter's {term} {v} is not what the project's files state: "
                        f"{places}. Cite the file's term."
                    )
        elif stated and term == "vat" and (has_total or _TOTAL.search(text or "")):
            places = "; ".join(f"{s}% ({w})" for s, w in stated[:2])
            wrong.append(
                f"The project's files state VAT ({places}); the letter quotes a price and does "
                "not say whether VAT is in it. Say it, citing the file."
            )
        if term == "vat" and stated and has_total and said:
            if not (_VAT_AMOUNT.search(text or "") and _WITH_VAT.search(text or "")):
                wrong.append(
                    "A priced letter gives the VAT amount and the total with VAT beside the "
                    "total: each worked out with calculate (the total × the file's VAT rate, "
                    'cited to it) and put in as {"type": "num"}.'
                )
    if has_total:
        missing = [name for name, words in _BID_FIELDS if not words.search(text or "")]
        if missing:
            wrong.append(
                f"A priced letter has the bid fields: {', '.join(missing)}. ONE never invents "
                "them: write each as a field the engineer fills, e.g. «مقدم العطاء: [يملأه "
                'المهندس: اسم مقدم العطاء]» or "Bidder: [to be filled by the engineer]".'
            )
    return wrong


_VAT_AMOUNT = re.compile(r"قيم[ةه]\s+(?:ال)?ضريب[ةه]|مبلغ\s+(?:ال)?ضريب[ةه]|\bvat\s+amount\b", re.I)
_WITH_VAT = re.compile(
    r"شامل(?:ا|ًا|اً)?\s+(?:ال)?ضريب[ةه]|شامل(?:ة)?\s"
    r"+ضريب[ةه]|\b(?:incl(?:uding|\.)?|with)\s+vat\b",
    re.I,
)
_BID_FIELDS = (
    (
        "bidder",
        re.compile(r"مقد[ّ]?م\s+العطاء|اسم\s+(?:الشركة|المقاول)|\b(?:bidder|tenderer)\b", re.I),
    ),
    (
        "tender number",
        re.compile(r"رقم\s+(?:المناقص[ةه]|العطاء|الممارس[ةه])|\btender\s+(?:no|number|ref)", re.I),
    ),
    ("signature", re.compile(r"التوقيع|توقيع|\bsignature\b|\bsigned\b", re.I)),
)
