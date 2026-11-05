"""The client of QS Mind Prices' sources endpoint (Plan 5, Task 13's contract):

    GET {base}/api/prices/sources?country=egypt|saudi|uae
    Authorization: Bearer <QS Mind account token> (Plan 8), or in development the key store
    user "qsmind-prices-dev"
    -> {"country", "lastDay", "items": [{"id", "category", "name": {en, ar}, "spec": {en, ar},
        "unit": {en, ar}, "currency", "vat", "cadence",
        "check": {"day", "price", "confidence", "sourceDate", "flags", "sources":
                  [{"url", "title", "date", "quote"}]} | null}]}

Only the country goes out. Prices are read as exact text: a JSON number keeps the digits it was
written with, and a price that is not a plain non-negative decimal is "no price", never 0.

No PydanticAI here."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol

import httpx

from qsone import keys

COUNTRIES = {"EG": "egypt", "SA": "saudi", "AE": "uae"}
CODES = {name: code for code, name in COUNTRIES.items()}
VATS = ("incl", "excl", "na", "unknown")  # as QS Mind Prices states them
CADENCES = ("daily", "weekly", "monthly")
BASE_URL = "https://prices.qsmind.app"
PATH = "/api/prices/sources"
DEV_KEY_USER = "qsmind-prices-dev"  # development only, until Plan 8's account session

Country = Literal["egypt", "saudi", "uae"]

_EXACT = re.compile(r"[0-9]+(\.[0-9]+)?")
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ID = re.compile(r"[^@\s/]{1,120}")  # fits a `prices:EG/<id>@<day>` ref
_CURRENCY = re.compile(r"[A-Z]{3}")  # ISO 4217


@dataclass(frozen=True)
class PriceItem:
    """One QS Mind Prices item with its latest shown check (`day` and `price` are None when it
    has none). `sources` are [{url, title, date, quote}]; their title and quote never go to the
    model."""

    id: str
    name: dict
    spec: dict
    unit: dict
    currency: str
    vat: str
    cadence: str
    day: str | None
    price: str | None
    confidence: str | None
    source_date: str | None
    flags: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    category: str = ""


class PricesFailed(Exception):
    """QS Mind Prices could not be read: `reason` is "offline" (no connection), "down" (it
    answered with an error, or not in the contract) or "refused" (the token was refused)."""

    def __init__(self, reason: Literal["offline", "down", "refused"]) -> None:
        super().__init__(reason)
        self.reason = reason


class PricesClient(Protocol):
    async def country_list(self, country: Country) -> tuple[str | None, list[PriceItem]]:
        """(lastDay, items). Raises `PricesFailed`."""
        ...


def exact(value) -> str | None:
    """`value` as exact decimal text, or None when it is not a plain non-negative decimal."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        value = format(value, "f")
    elif isinstance(value, int):
        value = str(value)
    return value if isinstance(value, str) and _EXACT.fullmatch(value) else None


def _day(value) -> str | None:
    return value if isinstance(value, str) and _DAY.fullmatch(value) else None


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _pair(value) -> dict:
    value = value if isinstance(value, dict) else {}
    return {"en": _text(value.get("en")), "ar": _text(value.get("ar"))}


def _sources(value) -> list[dict]:
    found = []
    for s in value if isinstance(value, list) else ():
        if isinstance(s, dict) and isinstance(s.get("url"), str):
            found.append(
                {
                    "url": s["url"],
                    "title": _text(s.get("title")),
                    "date": _day(s.get("date")),
                    "quote": _text(s.get("quote")),
                }
            )
    return found


def _item(raw) -> PriceItem | None:
    """One item of the list, or None when it does not fit the contract."""
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        return None
    if not _ID.fullmatch(raw["id"]) or not _CURRENCY.fullmatch(_text(raw.get("currency"))):
        return None
    check = raw.get("check") if isinstance(raw.get("check"), dict) else {}
    day, price = _day(check.get("day")), exact(check.get("price"))
    if day is None:
        price = None
    flags = [f for f in check.get("flags") or () if isinstance(f, str)]
    vat, cadence = raw.get("vat"), raw.get("cadence")
    return PriceItem(
        id=raw["id"],
        name=_pair(raw.get("name")),
        spec=_pair(raw.get("spec")),
        unit=_pair(raw.get("unit")),
        currency=raw["currency"],
        vat=vat if vat in VATS else "unknown",
        cadence=cadence if cadence in CADENCES else "weekly",
        day=day if price is not None else None,
        price=price,
        confidence=check.get("confidence") if isinstance(check.get("confidence"), str) else None,
        source_date=_day(check.get("sourceDate")) if price is not None else None,
        flags=flags,
        sources=_sources(check.get("sources")) if price is not None else [],
        category=_text(raw.get("category")),
    )


def parse(body: bytes | str) -> tuple[str | None, list[PriceItem]]:
    """(lastDay, items) from the endpoint's answer. Raises `ValueError` for a body that is not
    the contract's."""
    found = json.loads(body, parse_float=Decimal)
    if not isinstance(found, dict) or not isinstance(found.get("items"), list):
        raise ValueError("not a QS Mind Prices list")
    items = [i for i in map(_item, found["items"]) if i is not None]
    return _day(found.get("lastDay")), items


class HttpPrices:
    """QS Mind Prices over HTTP. `auth` gives the request's headers when it is sent, so a token
    that changes is always the current one; it is never logged or returned."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str = BASE_URL,
        auth: Callable[[], dict[str, str]],
    ) -> None:
        self.http, self.base_url, self.auth = http, base_url.rstrip("/"), auth

    async def country_list(self, country: Country) -> tuple[str | None, list[PriceItem]]:
        try:
            r = await self.http.get(
                f"{self.base_url}{PATH}", params={"country": country}, headers=self.auth()
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError) as e:
            raise PricesFailed("offline") from e
        except httpx.HTTPError as e:  # a read timeout, a broken answer
            raise PricesFailed("down") from e
        if r.status_code in (401, 403):
            raise PricesFailed("refused")
        if r.status_code != 200:
            raise PricesFailed("down")
        try:
            return parse(r.content)
        except ValueError as e:
            raise PricesFailed("down") from e


def from_key_store(http: httpx.AsyncClient) -> HttpPrices | None:
    """QS Mind Prices with the development key, when the key store has one; else None (not
    subscribed). Plan 8 replaces this with the account's token."""
    if keys.get_key(DEV_KEY_USER) is None:
        return None

    def auth() -> dict[str, str]:
        key = keys.get_key(DEV_KEY_USER)
        return {"Authorization": f"Bearer {key}"} if key else {}

    return HttpPrices(http, auth=auth)
