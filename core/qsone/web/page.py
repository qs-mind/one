"""A web page as Markdown, with its title and its date (Plan 5, decisions 8 and 9).

- `beautifulsoup4` on `html.parser`, then `markdownify`; tables are kept as `|` rows.
- Dropped: scripts, styles, menus, headers, footers, side bars, forms, svg and the like.
- `<main>` or `<article>` is preferred over the whole body.
- Hidden elements (`hidden`, `aria-hidden="true"`, `display:none`, `visibility:hidden`) are
  dropped. Those that held text are counted and flagged, with any line in them that looks like
  an order to an AI: a person never sees that text, but an AI would read it.
- The date is the page's own: `article:published_time` / `modified_time`, then JSON-LD
  `datePublished` / `dateModified`, then `itemprop` dates, then `<time datetime>` inside
  `<main>` or `<article>` (`dated_how` "page"). The HTTP `Last-Modified` header counts only
  when there is none of these ("server"). Otherwise there is no date, and the result says so.

The text is the site's: data, never instructions."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, date
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify

from qsone.records import hidden
from qsone.records.extract import Piece
from qsone.records.hidden import Flag

_DROP = (
    "script", "style", "noscript", "template", "nav", "header", "footer", "aside", "form",
    "svg", "iframe", "object", "embed", "canvas", "button", "select", "textarea", "input",
)  # fmt: skip
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_DAY = re.compile(r"\s*(\d{4}-\d{2}-\d{2})")
_META_DATES = ("article:published_time", "article:modified_time")
_LD_DATES = ("datePublished", "dateModified")
MAX_TAGS = 200  # tag names kept in the hidden-element flag's locator; `count` has them all


@dataclass(frozen=True)
class Page:
    title: str
    text: str  # Markdown
    dated: str | None  # YYYY-MM-DD as the page gives it
    dated_how: str | None  # "page" | "server" | None
    hidden: int  # hidden elements that held text
    flags: tuple[Flag, ...] = ()  # hidden_element, and ai_instruction for hidden text


def day(value: object) -> str | None:
    m = _DAY.match(value) if isinstance(value, str) else None
    if m is None:
        return None
    try:
        return date.fromisoformat(m.group(1)).isoformat()
    except ValueError:
        return None


def _ld_dates(value: object, key: str) -> str | None:
    if isinstance(value, dict):
        found = day(value.get(key))
        return found or next(
            (d for v in value.values() if (d := _ld_dates(v, key)) is not None), None
        )
    if isinstance(value, list):
        return next((d for v in value if (d := _ld_dates(v, key)) is not None), None)
    return None


def _page_date(soup: BeautifulSoup) -> str | None:
    for name in _META_DATES:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag is not None and (found := day(tag.get("content"))):
            return found
    blocks = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            blocks.append(json.loads(script.get_text()))
        except ValueError:
            continue
    for key in _LD_DATES:
        if (found := _ld_dates(blocks, key)) is not None:
            return found
    for key in _LD_DATES:
        for tag in soup.find_all(attrs={"itemprop": key}):
            value = tag.get("content") or tag.get("datetime") or tag.get_text()
            if found := day(value):
                return found
    for area in soup.find_all(("main", "article")):
        for tag in area.find_all("time", attrs={"datetime": True}):
            if found := day(tag["datetime"]):
                return found
    return None


def server_date(headers: dict) -> str | None:
    try:
        when = parsedate_to_datetime(headers.get("last-modified", ""))
    except (TypeError, ValueError):
        return None
    return when.astimezone(UTC).date().isoformat() if when.tzinfo else when.date().isoformat()


def _is_hidden(tag) -> bool:
    return (
        tag.has_attr("hidden")
        or str(tag.get("aria-hidden", "")).lower() == "true"
        or bool(_HIDDEN_STYLE.search(str(tag.get("style", ""))))
    )


def _tidy(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _charset(headers: dict) -> str | None:
    m = re.search(r"charset=([\w-]+)", headers.get("content-type", ""), re.IGNORECASE)
    return m.group(1) if m else None


def _plain(data: bytes, base_url: str, headers: dict) -> Page:
    try:
        text = data.decode(_charset(headers) or "utf-8")
    except (LookupError, UnicodeDecodeError):
        text = data.decode("utf-8", "replace")
    name = unquote(urlsplit(base_url).path.rsplit("/", 1)[-1]) or urlsplit(base_url).hostname
    dated = server_date(headers)
    return Page(name or "", _tidy(text), dated, "server" if dated else None, 0)


def page(html: bytes, base_url: str, headers: dict) -> Page:
    """`html` (as the site sent it) read as a page; `headers` are the answer's, names in lower
    case. A `text/plain` answer is kept as it is."""
    if headers.get("content-type", "").split(";")[0].strip().lower() == "text/plain":
        return _plain(html, base_url, headers)
    soup = BeautifulSoup(html, "html.parser", from_encoding=_charset(headers))
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        h1 = soup.find("h1")
        title = (og.get("content", "") if og else "") or (
            h1.get_text(" ", strip=True) if h1 else ""
        )
    dated = _page_date(soup)
    dated_how = "page" if dated else None
    if dated is None and (dated := server_date(headers)) is not None:
        dated_how = "server"

    root = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in root.find_all(_DROP):
        tag.decompose()
    tags, texts = [], []
    for tag in root.find_all(_is_hidden):
        if tag.decomposed:  # inside a hidden element already dropped
            continue
        text = tag.get_text(" ", strip=True)
        if text:
            tags.append(tag.name)
            texts.append(text)
        tag.decompose()
    for tag in root.find_all("img"):
        tag.decompose()
    for link in root.find_all("a"):
        href = str(link.get("href", "")).strip()
        if (
            urlsplit(href).scheme.lower() in ("", "http", "https")
            and href
            and not href.startswith("#")
        ):
            link["href"] = urljoin(base_url, href)
        else:
            link.unwrap()

    flags: list[Flag] = []
    if texts:
        flags.append(
            Flag(
                "hidden_element",
                {"elements": tags[:MAX_TAGS]},
                hidden.excerpt(texts[0]),
                len(texts),
            )
        )
        flags += hidden.ai_instruction_flags(
            [Piece({"hidden_element": n}, t) for n, t in enumerate(texts, 1)]
        )
    text = markdownify(str(root), heading_style="ATX", bullets="-")
    return Page(title, _tidy(text), dated, dated_how, len(texts), tuple(flags))
