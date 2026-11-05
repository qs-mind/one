"""Web search providers (Plan 5, decision 11), in this order unless the engineer changes it in
settings.json `search_provider` ("native" puts the connected AI's own search first, "none" turns
web search off):

1. the QS Mind relay, for subscribers: not built here. It needs the account session (Plan 8)
   and a paid Brave plan (founder question 3). When it comes it is a `BraveSearch` with the
   relay's base URL and `Authorization: Bearer <account token>`: the same JSON, and the same
   errors, including `{"remaining": 0}` when the month's allowance is used up;
2. the engineer's own Brave key (key store user `brave`): free for the engineer up to Brave's
   free allowance, on the engineer's own account;
3. the connected AI's own search (`engine.oneshot.NativeSearch`): only the query goes out;
4. a search Connector (Task 12 gives it);
5. none: `WEB_NO_SEARCH` says how to add one.

A provider's answer is a list of `SearchHit`; a failure raises `SearchFailed` with the `copy`
text that says what happened."""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from qsone import copy
from qsone.web.page import day

BRAVE_URL = "https://api.search.brave.com/res/v1"
KEY_USER = "brave"  # the engineer's own Brave key, in the system key store
TIMEOUT = 20.0
PROVIDERS = ("brave", "native", "none")  # what settings.json `search_provider` may say


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    dated: str | None  # YYYY-MM-DD, or None


class SearchFailed(Exception):
    def __init__(self, text: dict, *, retry_online: bool = False) -> None:
        super().__init__(text["en"])
        self.text = text
        self.retry_online = retry_online


def as_hit(found: object) -> SearchHit | None:
    """A hit from any provider (a `SearchHit`, or `{title, url, snippet, page_age}` from the
    native search), or None when it has no web address."""
    if isinstance(found, SearchHit):
        found = {
            "title": found.title,
            "url": found.url,
            "snippet": found.snippet,
            "dated": found.dated,
        }
    if not isinstance(found, dict):
        return None
    url = found.get("url")
    if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https"):
        return None

    def text(key: str) -> str:
        value = found.get(key)
        if not isinstance(value, str):
            return ""
        return " ".join(html.unescape(re.sub(r"<[^>]*>", "", value)).split())  # Brave's <strong>

    return SearchHit(
        text("title"),
        url,
        text("snippet") or text("description"),
        day(found.get("dated")) or day(found.get("page_age")),
    )


def _used_up(response: httpx.Response) -> bool:
    """The month's allowance is gone: the relay says `remaining: 0`; Brave's own key says it in
    `X-RateLimit-Remaining` ("per second, per month")."""
    try:
        if response.json().get("remaining") == 0:
            return True
    except (ValueError, AttributeError):
        pass
    left = response.headers.get("x-ratelimit-remaining", "").split(",")
    return len(left) > 1 and left[-1].strip() == "0"


class BraveSearch:
    """Brave's web search API: with the engineer's own key (`X-Subscription-Token`), or later
    through the QS Mind relay (the same answers, another base URL and header)."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        auth: Callable[[], dict[str, str]],
        base_url: str = BRAVE_URL,
        name: str = "brave",
    ) -> None:
        self.http = http
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self.name = name

    async def _get(self, params: dict) -> httpx.Response:
        try:
            return await self.http.get(
                f"{self.base_url}/web/search",
                params=params,
                headers={"Accept": "application/json", **self.auth()},
                timeout=TIMEOUT,
            )
        except httpx.ConnectError:
            raise SearchFailed(copy.WEB_OFFLINE, retry_online=True) from None
        except httpx.HTTPError:
            raise SearchFailed(copy.WEB_SEARCH_BUSY) from None

    async def search(
        self, query: str, *, country: str | None, lang: str | None, count: int
    ) -> list[SearchHit]:
        params: dict = {"q": query, "count": count}
        if lang:
            params["search_lang"] = lang
        if country:
            params["country"] = country.upper()
        r = await self._get(params)
        if r.status_code == 422 and country:  # a country Brave does not cover: search them all
            del params["country"]
            r = await self._get(params)
        if r.status_code in (401, 403):
            raise SearchFailed(copy.WEB_SEARCH_KEY_REFUSED)
        if r.status_code == 402 or (r.status_code == 429 and _used_up(r)):
            raise SearchFailed(copy.WEB_SEARCH_LIMIT)
        if not 200 <= r.status_code < 300:
            raise SearchFailed(copy.WEB_SEARCH_BUSY)
        try:
            results = r.json()["web"]["results"]
        except (ValueError, KeyError, TypeError):
            return []  # no web results at all
        hits = (as_hit(x) for x in results if isinstance(x, dict))
        return [h for h in hits if h is not None][:count]


def _order(setting: object) -> tuple[str, ...]:
    if setting == "none":
        return ()
    return (
        ("native", "brave", "connector")
        if setting == "native"
        else ("brave", "native", "connector")
    )


def choose_provider(
    http: httpx.AsyncClient,
    *,
    setting: object,
    own_key: str | None,
    native=None,
    connector=None,
):
    """The search provider to use now (the order above), or None. `setting` is settings.json
    `search_provider`; anything but "native" or "none" keeps the usual order."""
    found = {
        "brave": BraveSearch(http, auth=lambda: {"X-Subscription-Token": own_key})
        if own_key
        else None,
        "native": native,
        "connector": connector,
    }
    return next((found[n] for n in _order(setting) if found[n] is not None), None)


def provider_name(*, setting: object, own_key: bool, native: bool) -> str:
    """Which search One would use, for the Settings screen: "brave", "native" or "none"."""
    have = {"brave": own_key, "native": native, "connector": False}
    return next((n for n in _order(setting) if have[n]), "none")
