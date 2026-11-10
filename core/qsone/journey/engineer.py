"""The introduction card (decision 24): the engineer's role, country, city and currency.

It is kept in Engineer Records (`<data>/engineer/`, encrypted) as the one item of kind
`engineer_card`, written by "engineer" and audited, so the city is never readable on disk. Since
Phase 1 it only fills a profile that is not saved yet (`journey.profile`), which gives the Lead QS
its line.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from qsone.records import ledger
from qsone.records.project import Records

KIND = "engineer_card"
ENGINEER = "engineer"


class Card(BaseModel):
    """What PUT /engineer/card takes. The city is the engineer's own words, one line. The screen
    sends the currency its country uses (EGP, SAR, AED) and none for "other"."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    role: Literal["contractor", "consultant", "owner", "procurement"]
    country: Literal["EG", "SA", "AE", "other"]
    city: str = Field(default="", max_length=80, pattern=r"^[^\x00-\x1f\x7f]*$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


def _found(records: Records) -> tuple[str, dict] | None:
    with records.read() as conn:
        row = conn.execute(
            "SELECT id, fields FROM items WHERE kind = ? ORDER BY created_at LIMIT 1", (KIND,)
        ).fetchone()
    return None if row is None else (row[0], json.loads(row[1]))


def card(records: Records) -> dict:
    """The saved card, or {} before the engineer filled it."""
    found = _found(records)
    return {} if found is None else found[1]


def save_card(records: Records, new: Card) -> dict:
    """Saves the card in Engineer Records, audited; an earlier card is updated, not added to."""
    fields = new.model_dump(exclude_none=True)  # "other" has no currency
    found = _found(records)
    if found is None:
        ledger.add_item(records, kind=KIND, actor=ENGINEER, fields=fields)
    else:
        ledger.update_item(records, found[0], fields=fields, actor=ENGINEER)
    return fields
