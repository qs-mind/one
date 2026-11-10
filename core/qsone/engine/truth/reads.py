"""What a Brief read: cited places, tender values and reading methods against its returns."""

import json
import re

from qsone import copy
from qsone.engine import numbers_guard
from qsone.engine.truth.cited import citations
from qsone.engine.truth.problem import Problem
from qsone.engine.truth.sources import _PLACE_KEYS


def read_passages(returns: list[tuple[str, str]]) -> list[tuple[str, dict, str]]:
    """Only text actually returned by reads or exact search hits, never files in storage.

    Parse the read tools' own locator lines. A continuation contributes only its returned
    lines; neither a requested page range nor a source footer proves the text was returned.
    """
    found = []
    decoder = json.JSONDecoder()
    for name, result in returns:
        if name == "search_records":
            try:
                payload = result.strip()
                if payload.startswith("<<data "):
                    payload = payload.split("\n", 1)[1].rsplit("\n<</data ", 1)[0]
                data = json.loads(payload)
            except (ValueError, IndexError):
                continue
            for hit in data.get("hits", []) if isinstance(data, dict) else []:
                if (
                    isinstance(hit, dict)
                    and isinstance(hit.get("locator"), dict)
                    and isinstance(hit.get("text"), str)
                    and hit.get("file_id")
                ):
                    found.append(
                        (
                            hit["file_id"],
                            hit["locator"] | {"_file_name": hit.get("file")},
                            hit["text"],
                        )
                    )
            continue
        if name not in {"files_read", "read_chunk"}:
            continue
        file, locator, lines, file_name = None, None, [], None

        def flush(file, locator, lines, file_name):
            text = "\n".join(lines).strip()
            if file and locator and text and text != "[no text on this page]":
                found.append((file, locator | {"_file_name": file_name}, text))

        for line in result.splitlines():
            if line.startswith("sources:") or line.startswith("<</data"):
                break
            if line.startswith("file_id: "):
                file = line[9:].split(" |", 1)[0]
                named = re.search(r"(?:^| \| )file: (.*?)(?: \||$)", line)
                file_name = named[1] if named else None
            if line.startswith("{"):
                try:
                    data, end = decoder.raw_decode(line)
                except ValueError:
                    data = {}
                if isinstance(data, dict) and (
                    "locator" in data or any(k in data for k in _PLACE_KEYS)
                ):
                    flush(file, locator, lines, file_name)
                    file = data.get("file_id", file)
                    file_name = data.get("file", file_name)
                    locator = data.get("locator", data)
                    lines = [line[end:].strip()]
                    continue
            if locator:
                lines.append(line)
        flush(file, locator, lines, file_name)
    return found


def unread_citations(text: str, returns: list[tuple[str, str]], *, rec=None) -> list[Problem]:
    """A cited place must occur in this Brief's returned text, including specialists' reads."""
    from qsone.records.arabic import clean

    passages = read_passages(returns)
    if rec is not None:
        from qsone.engine.map_digest import tender_facts

        passages += [
            (f["file_id"], f["locator"] | {"_file_name": f["file"]}, f["value"])
            for f in tender_facts(rec)
            if f["state"] != "blank" and f["value"]
        ]
    problems = []
    for segment, places, numbers in citations(text):
        for place in places:

            def matches(loc, coordinate, place=place):
                if place.file_name and loc.get("_file_name") != place.file_name:
                    return False
                if place.sheet == "":
                    return loc.get("line") == coordinate
                if place.sheet is not None:
                    return (
                        str(loc.get("sheet", "")).strip().casefold()
                        == place.sheet.strip().casefold()
                        and loc.get("row") == coordinate
                    )
                return loc.get("page") == coordinate

            coordinates = place.rows if place.sheet is not None else place.pages
            read_text = [
                words for _, loc, words in passages if any(matches(loc, n) for n in coordinates)
            ]
            have = numbers_guard.known_values(read_text)
            # Dates are intentionally excluded by the general quantity guard; here
            # they are tender values and must match the cited evidence too.
            dates = re.findall(r"(?<!\d)\d{1,4}/\d{1,2}/\d{1,4}(?!\d)", segment)
            dates_match = all(clean(d) in clean(" ".join(read_text)) for d in dates)
            read = all(any(matches(loc, n) for _, loc, _ in passages) for n in coordinates)
            if read and dates_match and all(value in have for _, value in numbers):
                continue
            where = place.words()
            if any(p.fix.startswith(where["en"] + " was") for p in problems):
                continue
            if read:  # read, but a value is not there: the model fixes it; the number check flags
                problems.append(
                    Problem(
                        "unread_citation",
                        where["en"]
                        + " was read, but a value or date this sentence gives is not on it. "
                        "Cite each value at the place that shows it, or remove it.",
                    )
                )
                continue
            problems.append(
                Problem(
                    "unread_citation",
                    where["en"]
                    + " was not read in this Brief. Read it with files_read or read_chunk "
                    "before citing it; if unavailable, remove that claim "
                    "and say what is missing.",
                    copy.fill(copy.TRUTH_UNREAD_PLACE, place=where),
                )
            )
    return problems


_TENDER_ABSENCE = re.compile(
    r"missing|still missing|ناقص|not found|could(?:n't| not) find|"
    r"not (?:specified|stated|provided)|لم "
    r"(?:أجد|اجد|يتم العثور)|غير (?:موجود|مذكور|محدد)|مش (?:موجود|مذكور)|ملقيتش|مفيش",
    re.I,
)
_TENDER_QUESTION = re.compile(
    r"tender|opening offers|duration|مناقص|كراسة|فتح العروض|مدة (?:التنفيذ|المشروع)", re.I
)


def tender_search_problem(output, question, searched, *, rec=None):
    from qsone.engine.map_digest import tender_facts
    from qsone.records.arabic import normalise

    found = []
    # Match the absent item's clause, not other answered items in the reply.
    aliases = ("bid security", "tender security", "الضمان الابتدائي", "التامين الابتدائي")

    def words(text):
        text = normalise(text)
        for alias in aliases:
            text = text.replace(normalise(alias), " bidsecurity ")
        return set(re.findall(r"\w+", text)) - {
            "the",
            "of",
            "a",
            "is",
            "not",
            "found",
            "missing",
            "amount",
            "or",
            "percentage",
        }

    absent = [line for line in re.split(r"[\n.;؛]", output) if _TENDER_ABSENCE.search(line)]
    for fact in tender_facts(rec) if rec is not None and absent else []:
        if fact["state"] == "blank" or not str(fact["value"] or "").strip():
            continue
        labels = list(fact["name"].values()) + [fact.get("source_label") or ""]

        def matches(label, line):
            named, missing = words(label), words(line)
            overlap = named & missing
            return bool(named) and (
                named <= missing or "bidsecurity" in overlap or len(overlap) >= 2
            )

        if not any(matches(label, line) for label in labels for line in absent):
            continue
        page = fact["locator"].get("page")
        if page is None:
            continue
        name = fact["name"].get("en") or fact["name"].get("ar")
        found.append(
            Problem(
                "tender_summary",
                f"The Tender summary has {name} = {fact['value']} at {fact['file']}, page {page}. "
                "Read that page with files_read and answer from it, citing it; "
                "if the page says otherwise, say so.",
            )
        )
    if found:
        return found
    if not searched and _TENDER_QUESTION.search(question) and _TENDER_ABSENCE.search(output):
        return [Problem("tender_search", copy.TENDER_SEARCH_NUDGE["en"], None)]
    return []


def reading_problems(text: str, returns: list[tuple[str, str]]) -> list[Problem]:
    """Reading method is metadata, never something inferred from legibility."""
    sentences = re.split(r"(?<!\d)\.(?!\d)|[\n؛]", text)
    claims = [
        line
        for line in sentences
        if re.search(r"\bOCR\b|التعرف الضوئي", line, re.I)
        and not re.search(r"\b(?:no|not|never|without)\b|مش|ليس|بدون|مفيش", line, re.I)
    ]
    if not claims:
        return []
    passages = read_passages(returns)
    # Only ONE's local readers identify OCR. Model picture reading is vision,
    # and absent read_by denotes the original text layer.
    from qsone.records.ocr import is_local

    ocr = bool(passages) and all(is_local(loc) for _, loc, _ in passages)
    confidence = any(re.search(r"confidence|ثقة", line, re.I) for line in claims)
    recorded = {str(loc["confidence"]) for _, loc, _ in passages if "confidence" in loc}
    claimed = re.findall(r"[0-9٠-٩]+(?:[.,][0-9٠-٩]+)?", " ".join(claims))
    from decimal import Decimal, InvalidOperation

    def exact(value):
        try:
            return Decimal(value.replace(",", "."))
        except InvalidOperation:
            return None

    supported = bool(claimed) and all(exact(v) in {exact(r) for r in recorded} for v in claimed)
    if ocr and (not confidence or supported):
        return []
    return [
        Problem(
            "reading_method",
            "Unsupported OCR method or confidence claim. Use only each reading record's read_by; "
            "missing read_by means original text layer, not OCR. Do not invent confidence. "
            "For mixed readings identify the exact file/page and method separately.",
            copy.TRUTH_READING_METHOD,
        )
    ]
