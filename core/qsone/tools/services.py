"""The one place a tool reaches the outside world (Plan 5): the HTTP client, the DNS resolver,
the clock, the Engineer Records file, and the search, prices, page-reading, Sandbox and
Connector services. Tests give fakes for each (`tests/fakes_tools.py`).

`services_for` builds the app's services once, in the lifespan; `close` ends them. In a Brief,
`engine.oneshot.for_run` binds the page reader and the native search to that Brief's models,
so what they spend reaches the Spending Caps.

No PydanticAI here."""

import asyncio
import socket
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any, Protocol

import httpx
import truststore

from qsone.records.project import Records
from qsone.sandbox import runtime
from qsone.sandbox.runner import SandboxRunner

TIMEOUT = 20  # seconds, for any one web request (decision 8)


class Transcriber(Protocol):
    """Reads a page image as text (Task 8). In a Brief: `engine.oneshot.PageReader`."""

    model_id: str

    async def transcribe(self, png: bytes, *, page: int) -> str: ...

    def expected_cost(self, pages: int) -> str | None: ...


class SearchProvider(Protocol):
    """A web search (Task 6): [{title, url, snippet, page_age}]."""

    name: str

    async def search(
        self, query: str, *, country: str | None, lang: str | None, count: int
    ) -> list: ...


@dataclass
class Services:
    http: httpx.AsyncClient  # no redirects followed by itself: the web tools follow them by hand
    resolve: Callable[[str], Awaitable[list[str]]]  # a host's addresses, checked before connecting
    clock: Callable[[], datetime]  # aware UTC
    engineer: Callable[[], Records]  # the open Engineer Records file (Plan 4's), on first use
    search: SearchProvider | None = None  # the search key's or the relay's (Task 6)
    native_search: SearchProvider | None = None  # the connected AI's own search, in a Brief
    prices: Any = None  # Task 10's `PricesClient`
    transcriber: Transcriber | None = None  # in a Brief, the engineer's image model
    sandbox: Any = None  # the app's one `SandboxRunner`, shared by every Brief (one run at a
    # time); its runtime is downloaded the first time a script runs
    connectors: Any = None  # Task 12's `ConnectorHub`
    robots: dict = field(default_factory=dict, repr=False)  # robots.txt by site, for a day
    # (Task 6); shared by every run's copy of these services

    def on_device(self, rec: Records | None) -> bool:
        """True for an On-device Project (its meta "on_device" is "1"): nothing may leave this
        computer, so no web, no cloud model reading pages, no remote Connector."""
        return rec is not None and rec.meta().get("on_device") == "1"

    async def close(self) -> None:
        await self.http.aclose()


async def resolve(host: str) -> list[str]:
    """Every address `host` has, by the system's own resolver. Raises `OSError`
    (`socket.gaierror`) when it has none."""
    found = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in found))


def utc_now() -> datetime:
    return datetime.now(UTC)


def services_for(app_state: Any) -> Services:
    """The app's services, built once in the lifespan (Task 15); `close` them on shutdown.
    `app_state.engine` holds the Engineer Records file. The Sandbox runner is made here once,
    so every Brief shares it."""
    http = httpx.AsyncClient(
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),  # office networks work too
        follow_redirects=False,
        timeout=TIMEOUT,
        headers={"User-Agent": "QS Mind One (qsmind.app)"},
    )
    base = runtime.root()
    return Services(
        http=http,
        resolve=resolve,
        clock=utc_now,
        engineer=app_state.engine.engineer_records,
        sandbox=SandboxRunner(runtime.folder(base), install=partial(runtime.ensure, base)),
        connectors=getattr(app_state, "connectors", None),
    )
