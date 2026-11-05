"""Prices (Plan 5, Task 10): QS Mind Prices from a daily local cache, the engineer's own prices
and this project's rates, each with its source and date; prices the engineer gives are kept
only after the engineer ticks them.

QS Mind Prices is the fake sources endpoint (`prices_transport`, Task 13's contract): no test
reaches prices.qsmind.app. Synthetic «عينة» data only."""

import json
import re
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic_ai import ModelRetry

from qsone import copy
from qsone.engine.general import open_engineer_records
from qsone.engine.tools import REGISTRY, call
from qsone.prices import cache, client
from qsone.prices.client import HttpPrices, PriceItem
from qsone.records import ledger
from qsone.records.files import add_file
from qsone.tools import prices as prices_tools  # noqa: F401 - registers the prices tools
from tests.fakes_tools import fake_services, prices_transport, tool_ctx
from tests.samples import sample_xlsx

BASE = "https://prices-sample.example"
TOKEN = "dev-sample-token"


def item(
    item_id: str,
    ar: str,
    en: str,
    price: str | None,
    day: str = "2026-11-03",
    *,
    cadence: str = "daily",
    source_date: str | None = "2026-11-02",
    unit: tuple[str, str] = ("ton", "طن"),
    vat: str = "incl",
) -> dict:
    """One item in the sources endpoint's shape."""
    check = None
    if price is not None:
        check = {
            "day": day,
            "price": price,
            "confidence": "high",
            "sourceDate": source_date,
            "flags": [],
            "sources": [
                {
                    "url": f"https://supplier-sample.example/{item_id}",
                    "title": f"Supplier page title - sample {item_id}",
                    "date": source_date,
                    "quote": f"quoted words - sample {item_id}",
                }
            ],
        }
    return {
        "id": item_id,
        "category": "steel",
        "name": {"en": en, "ar": ar},
        "spec": {"en": "", "ar": ""},
        "unit": {"en": unit[0], "ar": unit[1]},
        "currency": "EGP",
        "vat": vat,
        "cadence": cadence,
        "check": check,
    }


EGYPT = [
    item("rebar-16", "حديد تسليح 16 مم - عينة", "Rebar 16 mm - sample", "39850.00"),
    item("cement-opc", "أسمنت بورتلاندي - عينة", "Portland cement - sample", "3900"),
    item("sand", "رمل - عينة", "Sand - sample", None, unit=("m3", "م3")),
]


class Switch(httpx.MockTransport):
    """The sources endpoint, which can be made to fail: `fail` is an exception to raise or a
    status to answer. Records every request in `calls`."""

    def __init__(self, lists: dict) -> None:
        self.inner = prices_transport(lists, token=TOKEN)
        self.fail: BaseException | int | None = None
        self.calls: list[httpx.Request] = []

        def answer(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            if isinstance(self.fail, BaseException):
                raise self.fail
            if isinstance(self.fail, int):
                return httpx.Response(self.fail, json={"error": "sample"})
            return self.inner.handle_request(request)

        super().__init__(answer)


@pytest.fixture
def eng(data_dir):
    records = open_engineer_records(data_dir)
    yield records
    records.close()


@pytest.fixture
def transport():
    return Switch({"egypt": EGYPT})


def prices_client(transport: httpx.MockTransport, token: str = TOKEN) -> HttpPrices:
    http = httpx.AsyncClient(transport=transport, follow_redirects=False)
    return HttpPrices(http, base_url=BASE, auth=lambda: {"Authorization": f"Bearer {token}"})


@pytest.fixture
def ctx(rec, eng, transport):
    services = fake_services(engineer=lambda: eng, prices=prices_client(transport))
    return tool_ctx(rec, services=services)


@pytest.fixture
def unsubscribed(rec, eng):
    return tool_ctx(rec, services=fake_services(engineer=lambda: eng))


def data_of(out: str) -> dict:
    return json.loads(re.search(r"^data: (.*)$", out, re.M)[1])


def set_country(rec, code: str) -> None:
    with rec.write("engineer") as c:
        rec.set_meta(c, "country", code)


def own_price(eng, description: str, unit: str, rate: str, currency: str, dated: str) -> str:
    with eng.write("engineer") as c:
        at = eng.clock()
        source = ledger.write_source(
            c, at=at, actor="engineer", kind="engineer", title="sample", dated=dated
        )
        item_id = ledger.write_item(
            c,
            at=at,
            actor="engineer",
            kind="price",
            fields={"description": description, "unit": unit, "vat": "excl"},
        )
        ledger.write_number(
            c,
            at=at,
            actor="engineer",
            item_id=item_id,
            name="rate",
            value=rate,
            source_id=source,
            dated=dated,
            unit=unit,
            currency=currency,
        )
    return item_id


def project_rate(rec, code: str, description: str, rate: str, dated: str) -> str:
    with rec.write("Lead QS") as c:
        at = rec.clock()
        source = ledger.write_source(
            c, at=at, actor="Lead QS", kind="boq", title="مقايسة - عينة.xlsx", dated=dated
        )
        item_id = ledger.write_item(
            c,
            at=at,
            actor="Lead QS",
            kind="boq_item",
            code=code,
            fields={"description": description, "unit": "م3"},
        )
        ledger.write_number(
            c,
            at=at,
            actor="Lead QS",
            item_id=item_id,
            name="rate",
            value=rate,
            source_id=source,
            dated=dated,
            unit="م3",
            currency="EGP",
        )
    return item_id


def row(description: str, unit: str, rate: str, currency: str, **more) -> dict:
    return {
        "description": description,
        "unit": unit,
        "rate": rate,
        "currency": currency,
        "dated": "2026-11-04",
        "vat": "excl",
    } | more


def kept(records, kind: str = "price") -> list[dict]:
    with records.read() as c:
        found = c.execute(
            "SELECT i.fields, n.value, n.unit, n.currency, n.dated, s.kind, s.file_id, s.locator"
            " FROM items i JOIN numbers n ON n.item_id = i.id JOIN sources s ON s.id = n.source_id"
            " WHERE i.kind = ? ORDER BY i.rowid",
            (kind,),
        ).fetchall()
    return [
        {
            "fields": json.loads(f),
            "value": v,
            "unit": u,
            "currency": cur,
            "dated": d,
            "source": {"kind": k, "file_id": fid, "locator": json.loads(lc)},
        }
        for f, v, u, cur, d, k, fid, lc in found
    ]


# The tools ------------------------------------------------------------------------------------


def test_the_tools_are_registered_as_decided():
    lookup, propose = REGISTRY["prices_lookup"], REGISTRY["prices_propose"]
    assert (lookup.risk, lookup.untrusted, lookup.writes) == ("read", False, False)
    assert (propose.risk, propose.writes) == ("write", True)
    assert "checker" not in propose.roles
    for tool in (lookup, propose):
        assert len(tool.description.split()) <= 120 and "Example:" in tool.description


async def test_lookup_is_local_and_keeps_sources(ctx, transport):
    out = await call(
        "prices_lookup", {"item": "حديد تسليح 16 مم", "also": ["rebar 16 mm"], "country": "EG"}, ctx
    )
    assert "39850.00" in out and "prices:EG/rebar-16@2026-11-03" in out
    assert "https://supplier-sample.example/rebar-16" in out
    assert "quote" not in out and "Supplier page title" not in out  # off the model
    first = data_of(out)["qsmind"][0]
    assert first["value"] == "39850.00" and first["currency"] == "EGP" and first["vat"] == "incl"
    assert (first["dated"], first["age_days"], first["old"]) == ("2026-11-02", 3, False)
    (asked,) = transport.calls  # only the country went out, never the item's words
    assert asked.url.params == httpx.QueryParams({"country": "egypt"})
    assert asked.headers["authorization"] == f"Bearer {TOKEN}"

    set_country(ctx.rec, "EG")
    out = await call("prices_lookup", {"item": "أسمنت"}, ctx)
    assert "3900" in out and "defaults used: country=EG" in out
    assert len(transport.calls) == 1  # at most once a day


async def test_the_cache_is_downloaded_again_the_next_day(ctx, transport):
    await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    ctx.services.clock.advance(timedelta(days=1).total_seconds())
    await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    assert len(transport.calls) == 2


async def test_no_price_is_said_plainly_never_zero(ctx):
    out = await call("prices_lookup", {"item": "رمل", "country": "EG"}, ctx)
    sand = data_of(out)["qsmind"][0]
    assert sand["value"] is None and "ref" not in sand and "no_price" in sand["flags"]


async def test_nothing_found_says_so(ctx):
    out = await call("prices_lookup", {"item": "بلاط سيراميك", "country": "EG"}, ctx)
    assert copy.PRICES_NONE_FOUND["en"] in out


async def test_offline_uses_the_cache_with_its_date(ctx, transport):
    await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    ctx.services.clock.advance(timedelta(days=2).total_seconds())
    transport.fail = httpx.ConnectError("no internet - sample")
    out = await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    saved = cache.local_day(ctx.services.clock() - timedelta(days=2))
    assert copy.fill(copy.PRICES_OFFLINE, date=saved)["en"] in out and "3900" in out
    progress = [e.text for e in ctx.host.events if hasattr(e, "text") and isinstance(e.text, dict)]
    assert copy.fill(copy.PRICES_OFFLINE, date=saved) in progress  # the engineer sees it too


async def test_down_uses_the_cache(ctx, transport):
    await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    ctx.services.clock.advance(timedelta(days=1).total_seconds())
    transport.fail = 500
    out = await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    assert "QS Mind Prices did not answer" in out and "3900" in out


async def test_down_with_nothing_saved_shows_own_and_project(ctx, transport, eng):
    transport.fail = 503
    own_price(eng, "أسمنت - عينة", "طن", "3950", "EGP", "2026-11-01")
    out = await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    found = data_of(out)
    assert copy.PRICES_NONE_SAVED["en"] in out and found["qsmind"] == []
    assert found["own"][0]["value"] == "3950"


async def test_not_subscribed_shows_own_and_project(unsubscribed, eng):
    own_price(eng, "أسمنت بورتلاندي - عينة", "طن", "3950", "EGP", "2026-11-01")
    project_rate(
        unsubscribed.rec, "03/02", "خرسانة مسلحة بأسمنت بورتلاندي - عينة", "4100", "2026-10-01"
    )
    out = await call("prices_lookup", {"item": "أسمنت بورتلاندي"}, unsubscribed)
    found = data_of(out)
    assert copy.PRICES_NOT_SUBSCRIBED["en"] in out and found["qsmind"] == []
    own, project = found["own"][0], found["project"][0]
    assert (own["value"], own["unit"], own["currency"], own["vat"]) == ("3950", "طن", "EGP", "excl")
    assert (project["value"], project["code"], project["dated"]) == ("4100", "03/02", "2026-10-01")
    assert own["item_id"] and project["number_id"]  # ids, so the engineer is never asked


async def test_a_refused_token_is_not_subscribed(rec, eng, transport):
    services = fake_services(engineer=lambda: eng, prices=prices_client(transport, "wrong-token"))
    ctx = tool_ctx(rec, services=services)
    out = await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    assert copy.PRICES_NOT_SUBSCRIBED["en"] in out and data_of(out)["qsmind"] == []


async def test_old_price_is_marked(rec, eng):
    lists = {
        "egypt": [
            item(
                "rebar-old",
                "حديد قديم - عينة",
                "Old rebar - sample",
                "38000",
                "2026-10-06",
                source_date="2026-10-06",
            ),
            item(
                "paint",
                "دهان حديد - عينة",
                "Steel paint - sample",
                "120",
                "2026-10-06",
                cadence="monthly",
                source_date="2026-10-06",
            ),
        ]
    }
    services = fake_services(engineer=lambda: eng, prices=prices_client(Switch(lists)))
    ctx = tool_ctx(rec, services=services)
    found = data_of(await call("prices_lookup", {"item": "حديد", "country": "EG"}, ctx))["qsmind"]
    by_id = {c["ref"].split("/")[1].split("@")[0]: c for c in found}
    assert (by_id["rebar-old"]["age_days"], by_id["rebar-old"]["old"]) == (30, True)  # daily: 21
    assert by_id["paint"]["old"] is False  # monthly: 45


async def test_a_long_answer_fits_in_one_result(unsubscribed, eng):
    long = "خرسانة مسلحة للأسقف بأسمنت بورتلاندي عادي ورمل وزلط مغسول - عينة " * 4
    for n in range(10):
        own_price(eng, f"{long} {n}", "م3", f"41{n}0", "EGP", "2026-11-01")
        project_rate(unsubscribed.rec, f"03/{n:02}", f"{long} {n}", f"42{n}0", "2026-10-01")
    out = await call("prices_lookup", {"item": "خرسانة مسلحة", "k": 10}, unsubscribed)
    found = data_of(out)  # the data line is whole
    assert len(out.encode()) <= 8 * 1024 and "fewer shown to fit" in out
    assert found["own"] and found["project"]
    assert all(len(c["description"]) <= 120 for c in found["own"])
    assert f"{len(found['own'])} of the engineer's own" in out  # the count of what is shown


async def test_country_must_be_one_prices_covers(ctx):
    with pytest.raises(ModelRetry, match="EG, SA or AE"):
        await call("prices_lookup", {"item": "أسمنت", "country": "FR"}, ctx)
    with pytest.raises(ModelRetry, match="EG, SA or AE"):  # subscribed, and no country known
        await call("prices_lookup", {"item": "أسمنت"}, ctx)


async def test_on_device_project_sends_nothing(rec, eng, transport):
    services = fake_services(engineer=lambda: eng, prices=prices_client(transport))
    ctx = tool_ctx(rec, services=services, on_device=True)
    out = await call("prices_lookup", {"item": "أسمنت", "country": "EG"}, ctx)
    assert transport.calls == [] and copy.PRICES_NONE_SAVED["en"] in out


def test_json_numbers_become_exact_text():
    raw = (
        '{"id": "a", "currency": "EGP", "name": {"en": "A - sample", "ar": "أ - عينة"},'
        ' "check": {"day": "2026-11-03", "price": %s}}'
    )
    prices = ("39850.5", "39850.50", "39850", "-1")  # JSON numbers, as written
    items = ", ".join(raw % p for p in prices)  # noqa: UP031 - the digits as written
    text = '{"country": "egypt", "lastDay": "2026-11-03", "items": [' + items + "]}"
    last_day, items = client.parse(text.encode())
    assert last_day == "2026-11-03"
    assert [i.price for i in items] == ["39850.5", "39850.50", "39850", None]
    assert all(isinstance(i, PriceItem) for i in items)


def test_the_cache_is_replaced_per_country(eng):
    one = client.parse(json.dumps({"country": "egypt", "lastDay": None, "items": EGYPT}))[1]
    cache.store(eng, "egypt", one, fetched_at="2026-11-05T08:00:00+00:00", last_day="2026-11-03")
    cache.store(
        eng, "egypt", one[:1], fetched_at="2026-11-06T08:00:00+00:00", last_day="2026-11-03"
    )
    assert [i.id for i in cache.lookup(eng, "egypt", "أسمنت")] == []
    assert [i.id for i in cache.lookup(eng, "EG", "حديد تسليح")] == ["rebar-16"]
    assert cache.lookup(eng, "saudi", "حديد") == []


async def test_qsmind_ref_is_evidence(ctx):
    out = await call("prices_lookup", {"item": "حديد تسليح 16 مم", "country": "EG"}, ctx)
    ref = data_of(out)["qsmind"][0]["ref"]
    added = json.loads(await call("add_source", {"kind": "prices", "ref": ref}, ctx))
    assert added["dated"] == "2026-11-03"


# prices_propose -------------------------------------------------------------------------------


async def test_propose_stores_only_ticked_rows(ctx, eng):
    ctx.host.answers = {"rows": json.dumps({"choice": "keep", "rows_ok": [0]})}
    out = await call(
        "prices_propose",
        {
            "rows": [
                row("أسمنت - عينة", "طن", "3950", "EGP"),
                row("رمل - عينة", "م3", "250", "EGP"),
            ],
            "from": "chat",
            "where": "engineer",
        },
        ctx,
    )
    (card,) = ctx.host.cards
    assert card.kind == "rows" and card.title == copy.PRICES_ASK and card.payload["tick"]
    assert [r["description"] for r in card.payload["rows"]] == ["أسمنت - عينة", "رمل - عينة"]
    (price,) = kept(eng)
    assert price["fields"]["description"] == "أسمنت - عينة" and price["fields"]["vat"] == "excl"
    assert (price["value"], price["unit"], price["currency"], price["dated"]) == (
        "3950",
        "طن",
        "EGP",
        "2026-11-04",
    )
    assert price["source"]["kind"] == "engineer"
    assert price["source"]["locator"] == {"card_id": card.id, "row": 0}
    found = data_of(out)
    assert [k["row"] for k in found["kept"]] == [0] and found["kept"][0]["item_id"]
    assert [r["row"] for r in found["left_out"]] == [1]
    assert kept(ctx.rec) == []  # nothing in the project


async def test_an_own_price_is_found_from_another_project(ctx, eng, tmp_path):
    ctx.host.answers = {"rows": json.dumps({"choice": "keep", "rows_ok": [0]})}
    await call(
        "prices_propose",
        {"rows": [row("أسمنت - عينة", "طن", "3950", "EGP")], "from": "chat", "where": "engineer"},
        ctx,
    )
    from qsone.records.project import Records  # a second project, same Engineer Records

    other = Records.create(tmp_path / "other", name="مشروع آخر - عينة", actor="engineer")
    try:
        later = tool_ctx(other, services=fake_services(engineer=lambda: eng))
        out = await call("prices_lookup", {"item": "أسمنت"}, later)
        assert data_of(out)["own"][0]["value"] == "3950"
    finally:
        other.close()


async def test_propose_refused_stores_nothing(ctx, eng):
    ctx.host.answers = {"rows": json.dumps({"choice": "no", "rows_ok": []})}
    out = await call(
        "prices_propose",
        {"rows": [row("أسمنت - عينة", "طن", "3950", "EGP")], "from": "chat", "where": "engineer"},
        ctx,
    )
    assert kept(eng) == [] and data_of(out)["kept"] == []


async def test_quote_rows_point_at_the_file(ctx):
    quote = sample_xlsx(
        {
            "Quote": [
                ["البند", "الوحدة", "السعر"],
                ["أسمنت - عينة", "طن", 3950],
                ["رمل - عينة", "م3", 250],
            ]
        }
    )
    f = add_file(ctx.rec, "عرض سعر - عينة.xlsx", quote, actor="engineer").id
    ctx.host.answers = {"rows": json.dumps({"choice": "keep", "rows_ok": [0, 1]})}
    await call(
        "prices_propose",
        {
            "rows": [
                row("أسمنت - عينة", "طن", "3950", "EGP", row=2, supplier="مصنع - عينة"),
                row("رمل - عينة", "م3", "250", "EGP", row=3),
            ],
            "from": f"file:{f}#sheet=Quote",
            "where": "project",
        },
        ctx,
    )
    first, second = kept(ctx.rec)
    assert first["source"] == {
        "kind": "quote",
        "file_id": f,
        "locator": {"sheet": "Quote", "row": 2, "dated_how": "document"},
    }
    assert second["source"]["locator"]["row"] == 3 and first["fields"]["supplier"] == "مصنع - عينة"


async def test_a_quote_row_must_exist_in_the_file(ctx):
    quote = sample_xlsx({"Quote": [["أسمنت - عينة", "طن", 3950]]})
    f = add_file(ctx.rec, "عرض سعر - عينة.xlsx", quote, actor="engineer").id
    with pytest.raises(ModelRetry, match="real evidence"):
        await call(
            "prices_propose",
            {
                "rows": [row("أسمنت - عينة", "طن", "3950", "EGP", row=99)],
                "from": f"file:{f}#sheet=Quote",
                "where": "project",
            },
            ctx,
        )
    assert ctx.host.cards == []  # refused before the engineer is asked


async def test_supplier_phone_is_kept_only_if_the_engineer_says_so(ctx, eng):
    ctx.host.answers = {
        "rows": json.dumps({"choice": "keep", "rows_ok": [0]}),
        "question": json.dumps({"choice": "sent", "answers": {"keep": "never"}}),
    }
    out = await call(
        "prices_propose",
        {
            "rows": [
                row(
                    "أسمنت - عينة",
                    "طن",
                    "3950",
                    "EGP",
                    supplier={"name": "مصنع - عينة", "phone": "01001234567"},
                )
            ],
            "from": "chat",
            "where": "engineer",
        },
        ctx,
    )
    (price,) = kept(eng)
    assert price["fields"]["supplier"] == {"name": "مصنع - عينة"}
    assert "01001234567" not in out and "Not kept" in out


@pytest.mark.parametrize(
    "bad",
    [
        {"rate": 3950.0},
        {"rate": "about 4000"},
        {"currency": "egp"},
        {"dated": "4/11/2026"},
    ],
)
async def test_a_bad_row_is_a_model_retry(ctx, bad):
    with pytest.raises(ModelRetry):
        await call(
            "prices_propose",
            {
                "rows": [row("أسمنت - عينة", "طن", "3950", "EGP") | bad],
                "from": "chat",
                "where": "engineer",
            },
            ctx,
        )


async def test_a_replayed_proposal_asks_once(ctx, eng):
    ctx.host.answers = {"rows": json.dumps({"choice": "keep", "rows_ok": [0]})}
    args = {"rows": [row("أسمنت - عينة", "طن", "3950", "EGP")], "from": "chat", "where": "engineer"}
    first = await call("prices_propose", args, ctx)
    assert await call("prices_propose", args, ctx) == first
    assert len(ctx.host.cards) == 1 and len(kept(eng)) == 1


async def test_without_a_key_one_is_not_subscribed(transport):
    from qsone import keys

    http = httpx.AsyncClient(transport=transport)
    assert client.from_key_store(http) is None  # no account session yet (Plan 8)
    keys.set_key(client.DEV_KEY_USER, TOKEN)
    found = client.from_key_store(http)
    assert found.base_url == "https://prices.qsmind.app"
    assert found.auth() == {"Authorization": f"Bearer {TOKEN}"}


def test_exact_values_stay_text():
    assert Decimal(client.exact("39850.50")) == Decimal("39850.5")
    assert client.exact(True) is None and client.exact(float("nan")) is None
