"""Placeholders: the blanks a model left for values in a text or a Deliverable."""

import re

# Placeholders --------------------------------------------------------------------------------

# A bracketed blank a model left for a value: «[القيمة]», "[Client name]", {{total}}, <<date>>.
# Not a markdown link ("[the quote](…)"), a footnote ("[1]") or a checkbox ("[x]").
_PLACEHOLDER = re.compile(
    r"\[(?P<square>[^\[\]\n]{2,80})\](?!\()|\{\{(?P<curl"
    r"y>[^{}\n]{1,80})\}\}|<<(?P<angle>[^<>\n]{1,80})>>"
)
_LETTERS = re.compile(r"[^\W\d_]{2,}")


# A letter's field the engineer fills (bidder, tender number, signature): never invented.
FOR_ENGINEER = re.compile(r"يملأه\s+المهندس|يملاه\s+المهندس|to be filled by the engineer", re.I)
# ONE's insides are no blank: a record id, or a bit of JSON (the Brissa reply, 6 Nov 2026).
_ID = re.compile(r"\b[0-9a-f]{32}\b")
_JSONISH = re.compile(r"[{}\"]|^\s*\w+\s*:")


def placeholders(text: str) -> list[str]:
    """Each blank left for a value in `text`, as written, once."""
    found: list[str] = []
    for m in _PLACEHOLDER.finditer(text or ""):
        inside = m.group("square") or m.group("curly") or m.group("angle") or ""
        if _ID.search(inside) or (m.group("square") and _JSONISH.search(inside)):
            continue
        if FOR_ENGINEER.search(inside):  # a field marked for the engineer to fill is no blank
            continue
        if _LETTERS.search(inside) and m.group(0) not in found:
            found.append(m.group(0))
    return found


def placeholders_in(value) -> list[str]:
    """The blanks in every text of a JSON-like value (a Deliverable's blocks, rows or title)."""
    found: list[str] = []

    def walk(v) -> None:
        if isinstance(v, str):
            found.extend(p for p in placeholders(v) if p not in found)
        elif isinstance(v, dict):
            for child in v.values():
                walk(child)
        elif isinstance(v, list | tuple):
            for child in v:
                walk(child)

    walk(value)
    return found
