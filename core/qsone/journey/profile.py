"""The engineer's profile (Phase 1, C1; contract routes 1-2): seven fields the first launch needs.

It is kept in Engineer Records (`<data>/engineer/`, encrypted) as the one item of kind
`engineer_profile`, written by "engineer" and audited. Before anything is saved it is filled from
what ONE already knows: the QS Mind account's name when the engineer is signed in, and the old
introduction card (`journey.engineer`: its `role` becomes `org_type`, `country` and `currency` are
kept, its city has no place here). Once saved, the saved profile is the answer.

The Lead QS's instructions get one line with four fields only (first name, position, type of
organisation, country): as little personal data as possible goes to an AI provider. A new project
takes the profile's country as its own (contract Q14), which the price and web tools read.
"""

import json
import re
from collections.abc import Callable

from fastapi import APIRouter

from qsone import copy
from qsone import phase1_contract as c
from qsone.journey import engineer
from qsone.records import ledger
from qsone.records.project import Records, RecordsError

KIND = "engineer_profile"
TEXTS = {"first_name": 80, "last_name": 80, "position": 120, "company": 120}  # longest kept
CHOICES = ("org_type", "country", "currency")
_USUAL = {"EG": "EGP", "SA": "SAR", "AE": "AED"}  # the example for a currency that is not one
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_ORGS = {
    "contractor": "works for a contractor",
    "consultant": "works for a consultant",
    "owner": "works for an owner or developer",
    "procurement": "works in procurement",
}
_COUNTRIES = {"EG": "Egypt", "SA": "Saudi Arabia", "AE": "the United Arab Emirates"}


def _found(records: Records) -> tuple[str, dict] | None:
    with records.read() as conn:
        row = conn.execute(
            "SELECT id, fields FROM items WHERE kind = ? ORDER BY created_at LIMIT 1", (KIND,)
        ).fetchone()
    return None if row is None else (row[0], json.loads(row[1]))


def _as_profile(fields: dict) -> c.Profile:
    values = {name: fields.get(name) or "" for name in TEXTS}
    values |= {name: fields.get(name) or None for name in CHOICES}
    complete = all(values[n].strip() for n in TEXTS) and all(values[n] for n in CHOICES)
    return c.Profile(**values, complete=complete)


def _known(records: Records, signed_in_name: str | None) -> dict:
    """What ONE knows before a profile is saved: the old card's fields and the account's name."""
    fields: dict = {}
    old = engineer.card(records)
    try:
        card = engineer.Card.model_validate(old) if old else None
    except ValueError:
        card = None
    if card is not None:
        fields |= {"org_type": card.role, "country": card.country, "currency": card.currency}
    first, _, last = " ".join((signed_in_name or "").split()).partition(" ")
    return fields | {
        "first_name": first[: TEXTS["first_name"]],
        "last_name": last[: TEXTS["last_name"]],
    }


def read(records: Records, signed_in_name: str | None = None) -> c.Profile:
    found = _found(records)
    return _as_profile(found[1] if found is not None else _known(records, signed_in_name))


def bad_value(new: c.ProfileIn) -> tuple[str, str] | None:
    """(field, example) of the first value that cannot be kept, else None. The example is the
    value made to fit, or the country's usual currency."""
    for name, longest in TEXTS.items():
        value = getattr(new, name)
        if _CONTROL.search(value):
            return name, " ".join(_CONTROL.sub(" ", value).split())[:longest]
        if len(value) > longest:
            return name, value[:longest].strip()
    if new.currency is not None and not re.fullmatch(r"[A-Z]{3}", new.currency):
        return "currency", _USUAL.get(new.country or "", "EGP")
    return None


def save(records: Records, new: c.ProfileIn) -> c.Profile:
    """Saves the profile as it stands, half-filled too; the same values again write nothing."""
    fields = new.model_dump()
    found = _found(records)
    if found is None:
        ledger.add_item(records, kind=KIND, actor=engineer.ENGINEER, fields=fields)
    elif found[1] != fields:
        ledger.update_item(records, found[0], fields=fields, actor=engineer.ENGINEER)
    return _as_profile(fields)


def lead_line(profile: c.Profile) -> str:
    """One line for the Lead QS's instructions, e.g. "The engineer: first name A; position
    Senior QS; works for a contractor; based in Egypt.", with only what is filled; "" when none
    of the four is. Never the last name, the company or the currency."""
    parts = [
        f"first name {' '.join(profile.first_name.split())}" if profile.first_name else "",
        f"position {' '.join(profile.position.split())}" if profile.position else "",
        _ORGS.get(profile.org_type or "", ""),
        f"based in {_COUNTRIES[profile.country]}" if profile.country in _COUNTRIES else "",
    ]
    said = [part for part in parts if part]
    return f"The engineer: {'; '.join(said)}." if said else ""


def country(engineer_records: Callable[[], Records]) -> str | None:
    """The profile's country for a new project (EG, SA or AE), or None: "other", none chosen,
    or Engineer Records that do not open (the project is still made)."""
    try:
        found = read(engineer_records()).country
    except (RecordsError, OSError):
        return None
    return found if found in _COUNTRIES else None


def router(engine, account) -> APIRouter:
    """`engine` holds Engineer Records; `account` gives the signed-in name (`Account.name`)."""
    r = APIRouter()
    refused = {409: {"model": c.Refusal}, 503: {"model": c.Refusal}}
    bad = {422: {"model": c.Refusal | c.BodyProblem}}

    @r.get("/engineer/profile", response_model=c.Profile, responses=refused)
    def get_profile():
        try:
            return read(engine.engineer_records(), account.name())
        except RecordsError as e:
            return c.refusal(e.text, e.status)

    @r.put("/engineer/profile", response_model=c.Profile, responses=refused | bad)
    def put_profile(body: c.ProfileIn):
        found = bad_value(body)
        if found is not None:
            return c.refusal(copy.PROFILE_BAD_VALUE, 422, field=found[0], example=found[1])
        try:
            return save(engine.engineer_records(), body)
        except RecordsError as e:
            return c.refusal(e.text, e.status)

    return r
