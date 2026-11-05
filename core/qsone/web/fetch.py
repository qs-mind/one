"""Fetching one web address for an agent (Plan 5, decision 8), safely:

- http and https only, a full address with a host and no user name or password in it;
- every hop is checked after DNS: each address the host has must be public, so no loopback,
  private, link-local, CGNAT, multicast or reserved address (this keeps agents away from the
  core's own port, the office network and cloud metadata);
- redirects are followed by hand, each one checked again, at most 5;
- at most 10 MB, read in a stream and stopped past the limit; 20 s for the whole read;
- robots.txt is honoured for the token `QSMindOne`, kept in memory for a day;
- only the kinds One reads: web pages, plain text, PDF, Excel and CSV.

The world failing is never an error: `fetch` returns the `copy` text that says what happened."""

import asyncio
import ipaddress
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from qsone import copy

MAX_BYTES = 10 * 2**20
TIMEOUT = 20.0  # seconds, for the whole read with its redirects
MAX_REDIRECTS = 5
MAX_URL = 2048
ROBOTS_BYTES = 512 * 1024
ROBOTS_SECONDS = 24 * 3600
TOKEN = "QSMindOne"  # the user-agent token robots.txt names


def _version() -> str:
    try:
        return version("qsone")
    except PackageNotFoundError:
        return "0"


USER_AGENT = f"QS Mind One/{_version()} (+https://qsmind.app) {TOKEN}"
_REDIRECTS = {301, 302, 303, 307, 308}

# What One reads, by the media type a site sends, else by the address's extension.
_TYPES = {
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "text",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "text/csv": "csv",
    "application/csv": "csv",
}
_EXTENSIONS = {
    "html": "html",
    "htm": "html",
    "txt": "text",
    "pdf": "pdf",
    "xlsx": "xlsx",
    "xls": "xls",
    "csv": "csv",
}
_UNTYPED = {"", "application/octet-stream", "binary/octet-stream", "application/download"}


@dataclass(frozen=True)
class Fetched:
    url: str  # as asked
    final_url: str  # after redirects
    status: int
    content_type: str
    kind: str  # html, text, pdf, xlsx, xls, csv
    body: bytes
    fetched_at: str  # ISO, UTC
    headers: dict[str, str]  # the answer's headers, names in lower case


def kind_of(content_type: str, url: str) -> str | None:
    """The kind One reads this as, or None for a kind it does not read."""
    media = content_type.split(";")[0].strip().lower()
    if media in _TYPES:
        return _TYPES[media]
    if media in _UNTYPED:
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        return _EXTENSIONS.get(name.rsplit(".", 1)[-1].lower()) if "." in name else None
    return None


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        inner = [ip.ipv4_mapped, ip.sixtofour, *(ip.teredo or ())]
        if any(a is not None and not _public(str(a)) for a in inner):
            return False
    return ip.is_global and not ip.is_multicast


def _parts(url: str):
    """The address split, or WEB_BAD_URL."""
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError for a port that is not a number
    except ValueError:
        return copy.WEB_BAD_URL
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or len(url) > MAX_URL
    ):
        return copy.WEB_BAD_URL
    return parts


async def _refused(services, host: str) -> dict | None:
    """None when every address of `host` is public; else the text that says why not."""
    host = host.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return copy.WEB_PRIVATE_ADDRESS
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses = await services.resolve(host)
        except OSError:
            return copy.WEB_OFFLINE  # no answer from DNS: offline, or no such site
    try:
        public = bool(addresses) and all(_public(a) for a in addresses)
    except ValueError:
        public = False
    return None if public else copy.WEB_PRIVATE_ADDRESS


async def _robots_allow(services, url: str) -> bool | dict:
    """True when robots.txt lets `TOKEN` read `url`; a failure text when the site's robots.txt
    could not be reached at all. A missing robots.txt allows everything."""
    parts = urlsplit(url)
    site = f"{parts.scheme}://{parts.netloc}"
    now = services.clock().timestamp()
    kept = services.robots.get(site)
    if kept is None or now - kept[0] > ROBOTS_SECONDS:
        got = await _follow(
            services, f"{site}/robots.txt", ROBOTS_BYTES, robots=False, any_kind=True
        )
        if isinstance(got, Fetched):
            rules = RobotFileParser()
            rules.parse(got.body.decode("utf-8", "replace").splitlines())
        elif got in (copy.WEB_PAGE_REFUSED, copy.WEB_TOO_BIG):
            rules = None  # no robots.txt (or an unusable one): nothing is disallowed
        else:
            return got
        kept = services.robots[site] = (now, rules)
    rules = kept[1]
    return rules is None or rules.can_fetch(TOKEN, url)


async def _follow(
    services, url: str, max_bytes: int, *, robots: bool, any_kind: bool = False
) -> Fetched | dict:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        parts = _parts(current)
        if isinstance(parts, dict):
            return parts
        refused = await _refused(services, parts.hostname)
        if refused is not None:
            return refused
        if robots:
            allowed = await _robots_allow(services, current)
            if allowed is not True:
                return copy.WEB_ROBOTS if allowed is False else allowed
        try:
            async with services.http.stream(
                "GET", current, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            ) as r:
                if r.status_code in _REDIRECTS and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code >= 500:
                    return copy.WEB_SITE_DOWN
                if not 200 <= r.status_code < 300:
                    return copy.WEB_PAGE_REFUSED
                content_type = r.headers.get("content-type", "")
                kind = kind_of(content_type, current) or ("text" if any_kind else None)
                if kind is None:
                    return copy.WEB_KIND_NOT_READ
                said = r.headers.get("content-length", "")
                if said.isdigit() and int(said) > max_bytes:
                    return copy.WEB_TOO_BIG
                body = bytearray()
                async for part in r.aiter_bytes():
                    body += part
                    if len(body) > max_bytes:
                        return copy.WEB_TOO_BIG
                return Fetched(
                    url=url,
                    final_url=current,
                    status=r.status_code,
                    content_type=content_type,
                    kind=kind,
                    body=bytes(body),
                    fetched_at=services.clock().isoformat(timespec="seconds"),
                    headers={k.lower(): v for k, v in r.headers.items()},
                )
        except httpx.TimeoutException:
            return copy.WEB_SITE_DOWN
        except httpx.ConnectError:
            return copy.WEB_OFFLINE
        except httpx.HTTPError:  # the site broke off or answered in a way HTTP does not allow
            return copy.WEB_SITE_DOWN
    return copy.WEB_PAGE_REFUSED  # too many redirects


async def fetch(
    services, url: str, *, max_bytes: int = MAX_BYTES, timeout: float = TIMEOUT
) -> Fetched | dict:
    """The page at `url`, or the `copy` text saying why not: WEB_BAD_URL, WEB_PRIVATE_ADDRESS,
    WEB_ROBOTS, WEB_OFFLINE, WEB_SITE_DOWN, WEB_PAGE_REFUSED, WEB_TOO_BIG, WEB_KIND_NOT_READ."""
    try:
        async with asyncio.timeout(timeout):
            return await _follow(services, url.strip(), max_bytes, robots=True)
    except TimeoutError:
        return copy.WEB_SITE_DOWN
