"""Each country's QS Mind Prices list, kept in Engineer Records (`price_cache`), downloaded at
most once a day and searched here with the word index (`price_cache_fts`, Plan 2's Arabic
normaliser), so an item's words never leave this computer. Offline, the saved list is used and
said to be from the day it was saved.

A cached row is `PriceItem` as JSON, so Engineer Records' evidence check
(`engine.tools_records.evidence`) finds `prices:EG/<item id>@<day>` by its country, id and day,
and takes the source's link from `sources`.

No PydanticAI here."""

import asyncio
import dataclasses
import json
from datetime import datetime

from qsone import copy
from qsone.engine.types import Text
from qsone.prices.client import CODES, COUNTRIES, Country, PriceItem, PricesFailed
from qsone.records import arabic, search
from qsone.records.project import Records

ACTOR = "QS Mind Prices"
POOL = 50  # word-index hits taken from each wording before they are fused


def country_name(code_or_name: str) -> Country | None:
    """"egypt" for "EG" or "egypt" (any case); None for a country Prices does not cover."""
    found = COUNTRIES.get(code_or_name.upper(), code_or_name.lower())
    return found if found in CODES else None  # type: ignore[return-value]


def local_day(moment: datetime) -> str:
    """The day of `moment` on this computer's clock, as every other date One shows."""
    return moment.astimezone().date().isoformat()


def _norm(item: PriceItem) -> str:
    words = [item.name["en"], item.name["ar"], item.spec["en"], item.spec["ar"], item.category]
    return arabic.normalise(" ".join(w for w in words if w))


def store(
    eng: Records, country: str, items: list[PriceItem], *, fetched_at: str, last_day: str | None
) -> None:
    """Replaces the country's saved list with `items`, in one transaction."""
    name = country_name(country)
    assert name is not None, country
    with eng.write(ACTOR) as c:
        old = [r[0] for r in c.execute("SELECT rowid FROM price_cache WHERE country = ?", (name,))]
        c.executemany("DELETE FROM price_cache_fts WHERE rowid = ?", ((r,) for r in old))
        c.execute("DELETE FROM price_cache WHERE country = ?", (name,))
        for item in {i.id: i for i in items}.values():  # an id appears once
            payload = json.dumps(dataclasses.asdict(item), ensure_ascii=False)
            rowid = c.execute(
                "INSERT INTO price_cache(country, item_id, day, payload) VALUES (?, ?, ?, ?)",
                (name, item.id, item.day, payload),
            ).lastrowid
            c.execute("INSERT INTO price_cache_fts(rowid, norm) VALUES (?, ?)", (rowid, _norm(item)))
        c.execute(
            "INSERT INTO price_cache_meta(country, fetched_at, last_day) VALUES (?, ?, ?)"
            " ON CONFLICT(country) DO UPDATE SET fetched_at = excluded.fetched_at,"
            " last_day = excluded.last_day",
            (name, fetched_at, last_day),
        )


def fetched_at(eng: Records, country: str) -> str | None:
    """When the country's list was last saved, or None when it never was."""
    with eng.read() as c:
        row = c.execute(
            "SELECT fetched_at FROM price_cache_meta WHERE country = ?", (country_name(country),)
        ).fetchone()
    return None if row is None else row[0]


def _useful(norm: str) -> str:
    """Without lone digits: "1" is in every list of sizes, so it finds nothing worth showing."""
    return " ".join(w for w in norm.split() if not (len(w) == 1 and w.isdigit()))


def _item(payload: str) -> PriceItem:
    return PriceItem(**json.loads(payload))


def lookup(eng: Records, country: str, text: str, also=(), *, k: int = 5) -> list[PriceItem]:
    """The saved items that best match `text` or any wording in `also`, best first."""
    name = country_name(country)
    norms = [_useful(arabic.normalise(t)) for t in (text, *also)]
    lists = []
    with eng.read() as c:
        for norm in norms:
            if not norm:
                continue
            match = " OR ".join(f'"{token}"' for token in norm.split())  # no FTS syntax gets in
            found = c.execute(
                "SELECT p.rowid FROM price_cache_fts f JOIN price_cache p ON p.rowid = f.rowid"
                " WHERE price_cache_fts MATCH ? AND p.country = ?"
                " ORDER BY bm25(price_cache_fts), p.rowid LIMIT ?",
                (match, name, POOL),
            ).fetchall()
            lists.append([r[0] for r in found])
        best = [rowid for rowid, _ in search.rrf(lists)[:k]]
        payloads = dict(
            c.execute(
                f"SELECT rowid, payload FROM price_cache WHERE rowid IN ({','.join('?' * len(best))})",
                best,
            ).fetchall()
        ) if best else {}
    return [_item(payloads[r]) for r in best if r in payloads]


async def refresh(services, country: str, *, on_device: bool = False) -> Text | None:
    """Downloads the country's list into Engineer Records unless it was saved today. Returns
    the note to show when the saved list (or none) is used instead, else None.
    `PRICES_NOT_SUBSCRIBED` means QS Mind Prices refused: show none of its prices."""
    name = country_name(country)
    assert name is not None, country
    eng = services.engineer()
    saved = await asyncio.to_thread(fetched_at, eng, name)
    now = services.clock()
    if saved is not None and local_day(datetime.fromisoformat(saved)) == local_day(now):
        return None
    saved_day = None if saved is None else local_day(datetime.fromisoformat(saved))
    if on_device:  # an On-device Project sends nothing out, not even the country
        return copy.PRICES_NONE_SAVED if saved_day is None else _on(copy.PRICES_ON_DEVICE, saved_day)
    try:
        last_day, items = await services.prices.country_list(name)
    except PricesFailed as e:
        if e.reason == "refused":
            return copy.PRICES_NOT_SUBSCRIBED
        if saved_day is None:
            return copy.PRICES_NONE_SAVED
        return _on(copy.PRICES_OFFLINE if e.reason == "offline" else copy.PRICES_DOWN, saved_day)
    stamp = now.isoformat(timespec="seconds")
    await asyncio.to_thread(store, eng, name, items, fetched_at=stamp, last_day=last_day)
    return None


def _on(text: Text, day: str) -> Text:
    return copy.fill(text, date=day)
