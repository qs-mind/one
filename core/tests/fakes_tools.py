"""Test doubles for the tools (Plan 5). Not product code: no test reaches the web, a search
engine, QS Mind Prices, an AI model or a real MCP server.

- `web(routes)`: an `httpx.MockTransport` that answers from `{url: (status, headers, body)}`
  and records every request in `.calls`; a value may be an exception to raise instead.
- `resolver(names)`: a fake DNS, `await resolve(host) -> [addresses]`, recording `.calls`.
- `FakeSearch(hits)`: a search provider that returns `hits` and records `.calls`.
- `FakeTranscriber(text_by_page)`: reads a page image as the text given for that page.
- `prices_transport(country_lists)`: QS Mind Prices' `GET /api/prices/sources` (Task 13).
- `fake_services(...)`: `Services` of these fakes.
- `tool_ctx(rec, ...)`: a Brief in `rec` with the Lead QS's run, a `FakeHost`, a fence and
  `fake_services()`.
"""

import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

import httpx

from qsone.engine.agents import lead_spec
from qsone.engine.data_text import new_fence
from qsone.engine.store import Store
from qsone.engine.tools import ToolContext
from qsone.engine.types import AgentSpec
from qsone.tools.services import Services
from tests.engine_fakes import OPUS, FakeClock, FakeHost

Route = tuple[int, Mapping[str, str], bytes | str] | BaseException


class RecordingTransport(httpx.MockTransport):
    """A `MockTransport` that keeps every request it was given, in order."""

    def __init__(self, handler) -> None:
        self.calls: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            return handler(request)

        super().__init__(record)


def web(routes: Mapping[str, Route]) -> RecordingTransport:
    """Answers each URL from `routes` (matched on the full URL, query included). An unknown
    URL is a 404. A route that is an exception is raised, so `httpx.ConnectError(...)` stands
    for no internet."""

    def answer(request: httpx.Request) -> httpx.Response:
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404, text="not found - sample")
        if isinstance(route, BaseException):
            raise route
        status, headers, body = route
        content = body.encode() if isinstance(body, str) else body
        return httpx.Response(status, headers=dict(headers), content=content)

    return RecordingTransport(answer)


class FakeResolver:
    """`await resolve(host)` gives the addresses mapped for `host`; an unmapped name fails
    as a real lookup does (`socket.gaierror`)."""

    def __init__(self, names: Mapping[str, Sequence[str]]) -> None:
        self.names = {host.lower(): list(addresses) for host, addresses in names.items()}
        self.calls: list[str] = []

    async def __call__(self, host: str) -> list[str]:
        self.calls.append(host)
        if host.lower() not in self.names:
            raise socket.gaierror(socket.EAI_NONAME, f"no such name - sample: {host}")
        return self.names[host.lower()]


def resolver(names: Mapping[str, Sequence[str]]) -> FakeResolver:
    return FakeResolver(names)


@dataclass
class FakeSearch:
    """A search provider: returns up to `count` of `hits` and records each call."""

    hits: list = field(default_factory=list)
    name: str = "fake"
    calls: list[dict] = field(default_factory=list)

    async def search(
        self, query: str, *, country: str | None, lang: str | None, count: int
    ) -> list:
        self.calls.append({"query": query, "country": country, "lang": lang, "count": count})
        return list(self.hits[:count])


@dataclass
class FakeTranscriber:
    """Reads page `n` of an image as `text_by_page[n]`; a page it has no text for fails as a
    model that could not read it."""

    text_by_page: dict[int, str] = field(default_factory=dict)
    model_id: str = "fake-vision"
    cost: str | None = "0.01"  # USD per page, sample
    calls: list[int] = field(default_factory=list)

    async def transcribe(self, png: bytes, *, page: int) -> str:
        assert png.startswith(b"\x89PNG"), "the transcriber is given a PNG"
        self.calls.append(page)
        if page not in self.text_by_page:
            raise RuntimeError(f"fake transcriber has no text for page {page}")
        return self.text_by_page[page]

    def expected_cost(self, pages: int) -> str | None:
        return None if self.cost is None else str(Decimal(self.cost) * pages)


COUNTRIES = {"EG": "egypt", "SA": "saudi", "AE": "uae"}


def prices_transport(
    country_lists: Mapping[str, list[dict]], *, token: str | None = None
) -> RecordingTransport:
    """QS Mind Prices' sources endpoint (Task 13's contract):
    `GET /api/prices/sources?country=egypt|EG` -> `{"country", "lastDay", "items"}`.

    `country_lists` maps `egypt`, `saudi` or `uae` to its items, each in the contract's shape.
    An unknown country is a 400; with `token` set, a request without `Bearer <token>` is a 401.
    `lastDay` is the latest `check.day` in the list, or null."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/prices/sources":
            return httpx.Response(404, json={"error": "not found"})
        if token is not None and request.headers.get("authorization") != f"Bearer {token}":
            return httpx.Response(401, json={"error": "unauthorised"})
        asked = request.url.params.get("country", "")
        country = COUNTRIES.get(asked.upper(), asked.lower())
        if country not in COUNTRIES.values():
            return httpx.Response(400, json={"error": "unknown country"})
        items = list(country_lists.get(country, []))
        days = [i["check"]["day"] for i in items if i.get("check")]
        body = {"country": country, "lastDay": max(days, default=None), "items": items}
        return httpx.Response(
            200,
            content=json.dumps(body, ensure_ascii=False).encode(),
            headers={"content-type": "application/json", "cache-control": "no-store"},
        )

    return RecordingTransport(answer)


def _no_engineer_records():
    raise AssertionError("this test gave no Engineer Records: fake_services(engineer=…)")


def fake_services(
    *,
    routes: Mapping[str, Route] | None = None,
    names: Mapping[str, Sequence[str]] | None = None,
    engineer=None,
    **others,
) -> Services:
    """`Services` of fakes: the web answers from `routes` (`web`, so nothing leaves the
    computer), DNS from `names` (`resolver`), the clock is `FakeClock`'s start, and
    `engineer` gives the Engineer Records file (a test that needs one passes it). `others` set
    the remaining services (`search`, `prices`, `transcriber`, …); unset ones are None."""
    clock = FakeClock()
    return Services(
        http=httpx.AsyncClient(transport=web(routes or {}), follow_redirects=False),
        resolve=resolver(names or {}),
        clock=clock,
        engineer=engineer or _no_engineer_records,
        **others,
    )


def tool_ctx(
    rec,
    *,
    untrusted: bool = False,
    answers: Mapping[str, str] | None = None,
    on_device: bool = False,
    agent: AgentSpec | None = None,
    services: Services | None = None,
) -> ToolContext:
    """A new Brief in `rec` with one run of `agent` (the Lead QS by default), a `FakeHost`
    that answers cards from `answers` (by card id or kind), a new fence, and `services`
    (default: `fake_services()`).

    `untrusted` marks the Brief as having read file text; `on_device` sets the project's meta
    `on_device` to "1"."""
    store = Store(rec, project_id=rec.id)
    brief = store.new_brief(rec.id, "سعّر البنود - عينة")
    host = FakeHost(brief_id=brief, answers=dict(answers or {}))
    spec = agent or lead_spec()
    run = store.new_run(brief, spec, OPUS.choice, None)
    if untrusted:
        store.mark_untrusted(brief)
    if on_device:
        with rec.write("engineer") as conn:
            rec.set_meta(conn, "on_device", "1")
    return ToolContext(
        brief_id=brief,
        run_id=run,
        agent=spec,
        rec=rec,
        store=store,
        host=host,
        fence=new_fence(),
        services=services if services is not None else fake_services(),
    )
