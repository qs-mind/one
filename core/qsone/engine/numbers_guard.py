"""The numbers guard: in code, not in the prompt (decision 18).

A number in the Lead's reply or in a Deliverable counts when it has a decimal point, at least 3
digits, or a unit or currency within 2 tokens of it. It must equal a value from a tool result in
this Brief (a ledger number, a calc result, quoted file text); any other is marked "no source",
never removed. These are not counted:
- codes and dates, whose digits are joined by "/" or "-" (item 03/02, 2026-11-05);
- references: a number right after a word such as page, clause, item, صفحة or بند;
- a year (four digits from 1900 to 2099) with no unit or currency next to it.

Values match after normalising: Arabic-Indic digits become 0-9, the Arabic decimal mark a
point, thousands separators go, and trailing zeros after the point do not count. A number that
exactly one ledger number in the tool results has is named with that number's id (`sourced`), so
the screen opens it into its source card (decision 16.3)."""

import json
import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# A number as written: digits, thousands groups (, or ٬) and a decimal part (. or ٫). Not part
# of a word, and not a piece of a code or a date (digits joined by / or -).
_NUMBER = re.compile(
    r"(?<![^\W_])(?<![/\-])"
    r"\d+(?:[,٬]\d{3})*(?:[.٫]\d+)?"
    r"(?![,٬.٫]?\d)(?![/\-]\d)"
)

# Units and currencies (lower case), as engineers write them in Arabic and English.
_UNITS = {
    *("m", "m2", "m3", "m²", "m³", "lm", "ml", "mm", "cm", "km", "sqm", "cum"),
    *("kg", "t", "ton", "tons", "tonne", "tonnes", "l", "litre", "litres", "liter", "liters"),
    *("h", "hr", "hrs", "hour", "hours", "day", "days", "week", "weeks", "month", "months"),
    *("nr", "no", "nos", "pcs", "pc", "ls", "%", "‰"),
    *("egp", "le", "usd", "$", "sar", "aed", "kwd", "omr", "qar", "bhd", "eur", "€", "gbp", "£"),
    *("م", "م2", "م3", "م٢", "م٣", "م.ط", "م.م", "مم", "سم", "كم", "كجم", "كغ", "كيلو", "طن"),
    *("لتر", "ساعة", "ساعه", "يوم", "أيام", "ايام", "أسبوع", "شهر", "عدد", "مقطوعية"),
    *("ج.م", "جم", "جنيه", "جنيها", "جنيهات", "ريال", "درهم", "دينار", "دولار", "يورو"),
}

# Words after which a number is a reference, not a quantity (lower case).
_REFERENCES = {
    *("page", "pages", "p", "pp", "clause", "clauses", "item", "items", "section", "sec"),
    *("sheet", "row", "rows", "line", "note", "no", "article", "para", "paragraph", "figure"),
    *("fig", "table", "drawing", "dwg", "rev", "revision", "version", "v", "step", "round"),
    *("code", "ref", "annex", "appendix", "schedule", "bill", "part", "chapter", "#"),
    *("صفحة", "صفحه", "ص", "بند", "البند", "بنود", "مادة", "المادة", "ماده", "فقرة"),
    *("الفقرة", "جدول", "الجدول", "شيت", "الشيت", "صف", "سطر", "رقم", "لوحة", "اللوحة"),
    *("ملحق", "الملحق", "إصدار", "الإصدار", "جولة", "الجولة", "كود", "باب", "الباب"),
    *("فصل", "الفصل", "قسم", "القسم"),
}

_STRIP = "()[]{}«»\"'“”‘’,،;:؛!?؟…"


def _word(token: str) -> str:
    return token.strip(_STRIP).rstrip(".").lower() or token.strip(_STRIP).lower()


def _canonical(written: str) -> str | None:
    """The value of a number as written, in one form: 39,850.50 and ٣٩٨٥٠٫٥ give 39850.5."""
    plain = written.translate(_DIGITS).replace(",", "").replace("٬", "").replace("٫", ".")
    try:
        value = Decimal(plain)
    except InvalidOperation:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _has_unit(before: list[str], after: str) -> bool:
    if after[:1] in ("%", "‰"):
        return True
    unit_after = re.match(r"[^\W\d_]+[23²³٢٣]?", after)  # a unit written onto the number: 120m3
    if unit_after and unit_after.group().lower() in _UNITS:
        return True
    near = [_word(t) for t in after.split()[:2]] + [_word(t) for t in before[-2:]]
    return any(w in _UNITS for w in near)


def _counted(text: str):
    """(written, value) for each number in `text` that the guard counts."""
    for match in _NUMBER.finditer(text):
        written = match.group()
        value = _canonical(written)
        if value is None:
            continue
        before = text[: match.start()].split()
        after = text[match.end() :]
        if before and not text[match.start() - 1].isspace() and before[-1][-1:] in "$€£":
            before = [*before[:-1], before[-1][-1]]  # $12: the sign is a token of its own
        if before and _word(before[-1]) in _REFERENCES:
            continue
        unit = _has_unit(before, after)
        plain = written.translate(_DIGITS)
        if not unit and re.fullmatch(r"(19|20)\d\d", plain):
            continue  # a year
        digits = sum(ch.isdigit() for ch in plain)
        if unit or "." in plain or "٫" in written or digits >= 3:
            yield written, value


def numbers_in(text: str) -> list[str]:
    """The numbers the guard counts, as written in `text` (so the screen can mark them there),
    in order. Arabic-Indic digits are read as digits; separators are kept as written."""
    return [written for written, _ in _counted(text)]


_ANY_NUMBER = re.compile(r"\d+(?:[,٬]\d{3})*(?:[.٫]\d+)?")


def known_values(tool_results: Iterable[str]) -> set[str]:
    """Every number in the Brief's tool results, normalised: these have a source."""
    found: set[str] = set()
    for result in tool_results:
        for match in _ANY_NUMBER.finditer(result):
            value = _canonical(match.group())
            if value is not None:
                found.add(value)
    return found


_DATA = re.compile(r"^data: (.+)$", re.M)  # a tool result's data line (qsone.tools.cite)
_LEDGER_ID = re.compile(r"[0-9a-f]{32}")
# The keys naming the ledger number a `value` is: a price found, a calculation's output, an input.
_ID_KEYS = ("number_id", "output", "number")


def _ledger_numbers(data: object, out: dict[str, set[tuple[str, str]]]) -> None:
    """Each ledger number in `data` as {canonical value: {(number id, exact value)}}: an object
    with a `value` and the id of the number it is (or `number: {id, value}`, as explain has it)."""
    if isinstance(data, list):
        for item in data:
            _ledger_numbers(item, out)
        return
    if not isinstance(data, dict):
        return
    value = data.get("value")
    ids = [data.get(k) for k in _ID_KEYS]
    nested = data.get("number")
    if isinstance(nested, dict):
        value, ids = nested.get("value"), [nested.get("id")]
    number_id = next((i for i in ids if isinstance(i, str) and _LEDGER_ID.fullmatch(i)), None)
    canonical = _canonical(value) if isinstance(value, str) else None
    if number_id and canonical is not None:
        out.setdefault(canonical, set()).add((number_id, value))
    for child in data.values():
        _ledger_numbers(child, out)


def sourced(text: str, tool_results: Iterable[str]) -> dict[str, dict]:
    """The counted numbers in `text` whose value exactly one ledger number in `tool_results` has,
    as written, each with that number's id and exact value: the screen opens each into its source
    card (decision 16.3). A value two ledger numbers share is left out (which one the reply meant
    is not known), as is any number no ledger number gave."""
    found: dict[str, set[tuple[str, str]]] = {}
    for result in tool_results:
        lines = _DATA.findall(result) or [result]
        for line in lines:
            try:
                _ledger_numbers(json.loads(line), found)
            except ValueError:
                continue
    out: dict[str, dict] = {}
    for written, value in _counted(text):
        ids = found.get(value, set())
        if written not in out and len({i for i, _ in ids}) == 1:
            number_id, exact = next(iter(ids))
            out[written] = {"id": number_id, "value": exact}
    return out


def unsourced(text: str, known: set[str]) -> list[str]:
    """The counted numbers in `text` whose value is not in `known`, as written, each once."""
    have = {v for k in known if (v := _canonical(k)) is not None}
    out: list[str] = []
    for written, value in _counted(text):
        if value not in have and written not in out:
            out.append(written)
    return out
