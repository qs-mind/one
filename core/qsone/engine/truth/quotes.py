"""Quotes: whether a price covers labour, or supply only."""

import re

# Quotes: what they cover ----------------------------------------------------------------------

# Words that say a price covers labour or installation, in Arabic and English.
_INSTALL = re.compile(
    r"تركيب|مصنعي[ةه]|عمال[ةه]|توريد\s+و\s*تركيب|شامل(?:ة|اً)?\s+(?:ال)?(?:تركيب|مصنعي|عمال)"
    r"|\b(?:install(?:ation|ed)?|labou?r|fix(?:ing|ed)|erect(?:ion)?"
    r"|supply and (?:install|fix|lay))\b",
    re.IGNORECASE,
)
_SUPPLY_ITEM = re.compile(r"توريد(?!\s+و\s*تركيب)|\bsupply(?!\s+and)\b", re.IGNORECASE)


def covers_labour(text: str) -> bool:
    return bool(_INSTALL.search(text or ""))


def supply_only_item(description: str) -> bool:
    """A BOQ item that is supply only («توريد … فقط», "Supply of …"): a supply quote fits it."""
    return bool(_SUPPLY_ITEM.search(description or "")) and not covers_labour(description)
