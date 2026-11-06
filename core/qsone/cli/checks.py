"""Pure assertions over HTTP responses and exported-PDF observations.

These helpers never read a file, query the core, calculate a price, or write a record.
The runner supplies the evidence; missing evidence fails the assertion.
"""

import re

from qsone import copy
from qsone.records.arabic import clean, normalise

_PAGE_NUMBER = re.compile(
    r"\bPage\s+(?P<en_page>\d+)\s+of\s+(?P<en_total>\d+)\b"
    r"|(?<!\w)صفحة\s+(?P<ar_page>\d+)\s+من\s+(?P<ar_total>\d+)(?!\w)",
    re.IGNORECASE,
)


def changes_target(deliverable, observed, expected):
    """Exactly one pending rate operation for each matching item, and no other operation."""
    needle = normalise(str(expected.get("description_contains", "")))
    if not needle:
        return False
    targets = {
        row["id"]
        for row in deliverable.get("rows", [])
        if row.get("kind") == "item"
        and needle in normalise(row.get("cells", {}).get("description", {}).get("text", ""))
    }
    changes = observed.get("changes", [])
    if not targets or len(changes) != len(targets):
        return False
    found = []
    for change in changes:
        op = change.get("op") or {}
        if (
            change.get("status") != "pending"
            or op.get("op") != "set_number"
            or op.get("name") != "rate"
        ):
            return False
        found.append(op.get("row"))
    return len(set(found)) == len(found) and set(found) == targets


def _body(text):
    text = _PAGE_NUMBER.sub("", clean(text))
    for mark in copy.EXPORT_DRAFT_MARK.values():
        text = text.replace(clean(mark), "")
    return " ".join(text.split())


def pack_integrity(observed, expected):
    """Check actual exported pages, outlines and seal field; not a signature trust verdict.

    ``bookmarks`` accepts titles or {title, page} entries. ``duplicates`` contains pairs of
    one-based output pages whose content must match after removing the ONE footer/draft mark.
    A seal assertion checks the signature field and its contents exist. Cryptographic validity
    is covered by the core's seal tests, not inferred here from the field name.
    """
    pages = observed.get("pages")
    texts = observed.get("page_texts", [])
    if type(pages) is not int or pages <= 0 or len(texts) != pages:
        return False
    if not all(isinstance(text, str) for text in texts):
        return False
    for wanted in expected.get("bookmarks", []):
        wanted = {"title": wanted} if isinstance(wanted, str) else wanted
        if not any(
            all(bookmark.get(key) == value for key, value in wanted.items())
            for bookmark in observed.get("bookmarks", [])
        ):
            return False
    if expected.get("seal") and not any(
        field.get("name") == "ONEIntegritySeal"
        and field.get("type") == "/Sig"
        and field.get("has_contents") is True
        for field in observed.get("signature_fields", [])
    ):
        return False
    # Duplicate copies need distinct, correct numbering even if page_numbers was omitted.
    if expected.get("page_numbers") or expected.get("duplicates"):
        for index, text in enumerate(texts, 1):
            matches = list(_PAGE_NUMBER.finditer(clean(text)))
            if len(matches) != 1:
                return False
            match = matches[0]
            number = int(match["en_page"] or match["ar_page"])
            total = int(match["en_total"] or match["ar_total"])
            if number != index or total != pages:
                return False
    for pair in expected.get("duplicates", []):
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or any(type(n) is not int or not 1 <= n <= pages for n in pair)
            or pair[0] == pair[1]
        ):
            return False
        first, second = (_body(texts[n - 1]) for n in pair)
        if not first or first != second:
            return False
    return True


def calculated_numbers(deliverable, expected):
    """Every expected value is a number cell whose source is a Calc Engine calculation."""
    from qsone.cli.walk import same_number

    cells = [cell for row in deliverable.get("rows", []) for cell in row.get("cells", {}).values()]
    cells.extend(deliverable.get("refs", {}).values())
    if deliverable.get("total"):
        cells.append(deliverable["total"])
    sources = deliverable.get("sources", {})
    return bool(expected) and all(
        any(
            same_number(cell.get("value"), value)
            and sources.get(cell.get("source"), {}).get("kind") == "calculation"
            and bool((sources.get(cell.get("source"), {}).get("locator") or {}).get("calculation"))
            for cell in cells
        )
        for value in expected
    )


def max_tool_steps(events, maximum):
    """Count actual tool steps in the latest complete work log; absent evidence fails."""
    logs = [event.get("data", {}) for event in events if event.get("type") == "data-worklog"]
    return bool(logs) and sum(bool(step.get("tool")) for step in logs[-1].get("steps", [])) <= int(
        maximum
    )
