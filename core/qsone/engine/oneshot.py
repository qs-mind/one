"""One-shot model calls for tools (Plan 5): a scanned page read by the engineer's AI from its
image, and the connected AI's own web search.

Each call is one model request, on the engineer's own AI and the engineer's own tokens (nothing
here costs QS Mind money), and each passes the same checks as every agent request:
`Spending.before_request` (the AI-call checks, then the Spending Caps) before it goes, and the
cost book after it. The Native Link goes through `CostedModel`; the Subscription Link (the
engineer's Claude Code) runs one job with no MCP server, no session kept on disk, and either no
built-in tool (a page) or WebSearch alone (a search).

Only what the call needs goes out: the page image with short instructions, or the search query.
Nothing is written to disk but Claude Code's instructions file, which holds no project text.
This is the only Plan 5 module that imports PydanticAI."""

import base64
import json
import logging
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic_ai import Agent, BinaryImage, WebSearchTool
from pydantic_ai.capabilities.native_tool import NativeTool
from pydantic_ai.messages import NativeToolReturnPart
from pydantic_ai.usage import UsageLimits

from qsone import copy
from qsone.engine import cards, connectors
from qsone.engine.connectors import claude_code
from qsone.engine.costs import CostedModel, Spending, usd_text
from qsone.engine.types import ModelCard, ModelChoice, Role, TeamHost, Text

log = logging.getLogger("qsone.engine.oneshot")

# Founder defaults (question 4, pending): change each here only.
SEND_PAGE_IMAGES = True  # scanned pages go to the engineer's own AI as images
ASK_ABOVE_PAGES = 20  # more pages than this in one call: a `cost` card first (Task 8)

# A page image of 1,600 px wide is about this many tokens in, and its text about this many out:
# the expected cost on the `cost` card, before anything is read.
PAGE_TOKENS = (1_700, 1_000)

READ_PAGE = (
    "Copy all the text on this page image exactly, in its own language and direction. Keep "
    "every digit as written, Arabic-Indic or Western. Write each table row as cells separated "
    "by |. Do not summarise, translate, explain or add anything. If the page has no text, "
    "reply with nothing."
)
SEARCH = "Search the web once for the user's query, exactly as given, and list what you found."
SEARCH_ON_SUBSCRIPTION = (
    "Use WebSearch once with the user's message as the query, exactly as given. Then reply "
    'with only a JSON array of the results, each {"title", "url", "snippet", "page_age"}, '
    "page_age null when unknown. No other text."
)

# Anthropic bills each native web search on top of tokens (the Model Data Sheet has no line for
# it): USD 10 per 1,000 searches, from its pricing page as of 2026-11-05.
SEARCH_FEE = Decimal("0.01")
SEARCH_FEE_BASIS = (
    "Anthropic web search, USD 10 per 1,000 searches: "
    "https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-search-tool"
    "#usage-and-pricing, as of 2026-11-05"
)
MAX_HITS = 10

_PAGE_ROLES: tuple[Role, ...] = ("specialist", "lead")  # decision 14's order
_SEARCH_ROLES: tuple[Role, ...] = ("quick", "specialist", "lead")  # a search needs no big model


class OneShotFailed(Exception):
    """The call was made and did not work; `text` says why in both languages."""

    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


@dataclass(frozen=True)
class Models:
    """The Brief's models, for the one-shot calls of one tool run."""

    sheet: Sequence[ModelCard]  # the Model Data Sheet, priced
    roles: Mapping[Role, ModelChoice]  # the Brief's model for each role
    connectors: Mapping[str, Any]  # connector id -> connector
    spending: Spending
    host: TeamHost
    brief_id: str
    project_id: str | None
    run_id: str  # the tool's own run: its costs are booked there
    work: Path  # <data>/claude-work: the Subscription Link's run folders

    def card(self, choice: ModelChoice | None) -> ModelCard | None:
        return next((c for c in self.sheet if c.choice == choice), None)

    def link(self, card: ModelCard) -> Any:
        return self.connectors.get(card.choice.connector)


def _model_link(models: Models, card: ModelCard | None) -> bool:
    link = None if card is None else models.link(card)
    return link is not None and getattr(link, "kind", "") == "model"


def _subscription(models: Models, order: Sequence[Role]) -> tuple[ModelCard, Role] | None:
    """The Subscription Link's card: a role's own choice first, else its first model."""
    if claude_code.ID not in models.connectors:
        return None
    for role in order:
        card = models.card(models.roles.get(role))
        if card is not None and card.choice.connector == claude_code.ID:
            return card, role
    for card in models.sheet:
        if card.choice.connector == claude_code.ID:
            return card, order[0]
    return None


def _page_model(models: Models) -> tuple[ModelCard, Role] | None:
    for role in _PAGE_ROLES:
        card = models.card(models.roles.get(role))
        if card is not None and card.images and _model_link(models, card):
            return card, role
    return _subscription(models, _PAGE_ROLES)


def _search_model(models: Models) -> tuple[ModelCard, Role] | None:
    for role in _SEARCH_ROLES:
        card = models.card(models.roles.get(role))
        if card is not None and card.choice.connector == "anthropic" and _model_link(models, card):
            return card, role
    return _subscription(models, _SEARCH_ROLES)


def image_model(models: Models) -> ModelCard | None:
    """The model that reads page images: the specialist tier's choice, then the Lead's, when it
    reads images; then the Subscription Link. None: OCR_NEEDS_MODEL."""
    found = _page_model(models)
    return None if found is None else found[0]


def _costed(models: Models, card: ModelCard, role: Role) -> CostedModel:
    try:
        model = models.link(card).model(card.choice.model)
    except connectors.NoKey:
        raise OneShotFailed(copy.NO_AI) from None
    return CostedModel(
        model,
        spending=models.spending,
        host=models.host,
        brief_id=models.brief_id,
        project_id=models.project_id,
        run_id=models.run_id,
        role=role,
        card=card,
    )


async def _once(models: Models, card: ModelCard, role: Role, agent: Agent, prompt) -> Any:
    """One request through `CostedModel`; a provider's error becomes its plain words."""
    try:
        return await agent.run(prompt, usage_limits=UsageLimits(request_limit=1))
    except connectors.PROVIDER_ERRORS as error:
        log.warning("A one-shot call through %s failed: %s", card.choice.connector, error)
        raise OneShotFailed(connectors.plain_error(error, models.link(card).name)) from None


async def _on_subscription(
    models: Models,
    card: ModelCard,
    role: Role,
    content: list[dict],
    *,
    instructions: str,
    tools: tuple[str, ...],
    failed: Text,
) -> str:
    await models.spending.before_request(models.host, brief_id=models.brief_id, card=card)
    cwd = models.work / f"oneshot-{uuid4().hex}"
    try:
        outcome = await models.link(card).oneshot(
            content, instructions=instructions, model=card.choice.model, tools=tools, cwd=cwd
        )
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    models.spending.after_response(
        brief_id=models.brief_id,
        project_id=models.project_id,
        run_id=models.run_id,
        role=role,
        card=card,
        input_tokens=sum(n for _, n, _ in outcome.usage),
        output_tokens=sum(n for _, _, n in outcome.usage),
        reported_usd=outcome.reported_usd,
    )
    if outcome.ended == "signed_out":
        raise OneShotFailed(copy.CLAUDE_CODE_SIGNED_OUT)
    if outcome.ended == "limit":
        raise OneShotFailed(copy.fill(copy.AI_BUSY, provider=claude_code.ClaudeCodeConnector.name))
    if outcome.ended not in ("done", "max_tokens"):
        raise OneShotFailed(failed)
    return outcome.text


# A page image -------------------------------------------------------------------------------------


async def transcribe(png: bytes, *, page: int, models: Models) -> tuple[str, str]:
    """The page's text, as the engineer's AI reads it from the image, and the model's id.
    Raises `OneShotFailed` (no image model, or the model failed), and `CallRefused` or
    `CapReached` from the AI-call checks and the Spending Caps."""
    found = _page_model(models) if SEND_PAGE_IMAGES else None
    if found is None:
        raise OneShotFailed(copy.OCR_NEEDS_MODEL)
    card, role = found
    if card.choice.connector == claude_code.ID:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(png).decode(),
                },
            },
            {"type": "text", "text": f"Page {page}."},
        ]
        text = await _on_subscription(
            models, card, role, content, instructions=READ_PAGE, tools=(), failed=copy.OCR_FAILED
        )
        return text.strip(), card.choice.model
    agent = Agent(_costed(models, card, role), instructions=READ_PAGE, output_type=str)
    result = await _once(
        models, card, role, agent, [f"Page {page}.", BinaryImage(png, media_type="image/png")]
    )
    return result.output.strip(), card.choice.model


class PageReader:
    """A `Transcriber` over the Brief's image model (what `services.transcriber` holds in a
    run, so a page read by a tool reaches the caps)."""

    def __init__(self, models: Models, card: ModelCard) -> None:
        self.models = models
        self.card = card
        self.model_id = card.choice.model
        self.subscription = card.subscription  # its cost is an "equivalent cost"

    async def transcribe(self, png: bytes, *, page: int) -> str:
        return (await transcribe(png, page=page, models=self.models))[0]

    def expected_cost(self, pages: int) -> str | None:
        """USD, two decimals, from the Model Data Sheet; None when the price is unknown."""
        each = cards.cost(self.card, input_tokens=PAGE_TOKENS[0], output_tokens=PAGE_TOKENS[1])
        return None if each is None else usd_text(each * pages)


def page_reader(models: Models) -> PageReader | None:
    """None when no model of this Brief reads page images (or page images are not sent)."""
    found = _page_model(models) if SEND_PAGE_IMAGES else None
    return None if found is None else PageReader(models, found[0])


# Web search ---------------------------------------------------------------------------------------


def _web(url: object) -> bool:
    return isinstance(url, str) and urlsplit(url).scheme in ("http", "https") and len(url) < 2048


def _hit(item: object) -> dict | None:
    if not isinstance(item, dict) or not _web(item.get("url")):
        return None
    title, snippet, age = item.get("title"), item.get("snippet"), item.get("page_age")
    return {
        "title": title if isinstance(title, str) else "",
        "url": item["url"],
        "snippet": snippet if isinstance(snippet, str) else "",
        "page_age": age if isinstance(age, str) and age else None,
    }


def _hits(items: object) -> list[dict]:
    found = [h for h in map(_hit, items if isinstance(items, list) else ()) if h is not None]
    return found[:MAX_HITS]


def _json_array(text: str) -> object:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except ValueError:
        return None


async def native_search(
    query: str, *, country: str | None, lang: str | None, models: Models
) -> list[dict]:
    """[{title, url, snippet, page_age}] from the connected AI's own search: Anthropic's web
    search on the Native Link, or Claude Code's WebSearch on the Subscription Link. Only the
    query goes out; `country` (two letters) localises the Native Link's search, and `lang` is
    not sent. [] when no model of this Brief can search. Raises `OneShotFailed`, `CallRefused`
    and `CapReached`."""
    found = _search_model(models)
    if found is None:
        return []
    card, role = found
    if card.choice.connector == claude_code.ID:
        text = await _on_subscription(
            models,
            card,
            role,
            [{"type": "text", "text": query}],
            instructions=SEARCH_ON_SUBSCRIPTION,
            tools=("WebSearch",),
            failed=copy.fill(copy.AI_FAILED, provider=claude_code.ClaudeCodeConnector.name),
        )
        return _hits(_json_array(text))
    location = {"country": country.upper()} if country and len(country) == 2 else None
    tool = WebSearchTool(max_uses=1, user_location=location)
    agent = Agent(
        _costed(models, card, role),
        instructions=SEARCH,
        output_type=str,
        capabilities=[NativeTool(tool)],
    )
    result = await _once(models, card, role, agent, query)
    searches = int(result.usage.details.get("web_search_requests", 0) or 0)
    if searches and not card.on_device:
        models.spending.add_fee(
            brief_id=models.brief_id,
            project_id=models.project_id,
            run_id=models.run_id,
            role=role,
            choice=card.choice,
            usd=SEARCH_FEE * searches,
            basis=SEARCH_FEE_BASIS,
        )
    hits: list[dict] = []
    for message in result.new_messages():
        for part in message.parts:
            if isinstance(part, NativeToolReturnPart) and part.tool_name == WebSearchTool.kind:
                hits += _hits(part.content)
    return hits[:MAX_HITS]


class NativeSearch:
    """A search provider over the Brief's own AI (decision 11's third place)."""

    name = "native"

    def __init__(self, models: Models) -> None:
        self.models = models

    async def search(
        self, query: str, *, country: str | None, lang: str | None, count: int
    ) -> list[dict]:
        hits = await native_search(query, country=country, lang=lang, models=self.models)
        return hits[:count]


def native_searcher(models: Models) -> NativeSearch | None:
    """None when no model of this Brief can search the web itself."""
    return None if _search_model(models) is None else NativeSearch(models)


def for_run(services: Any, models: Models) -> Any:
    """The app's `Services` for one tool run: its transcriber and native search are this
    Brief's models, unless the services already carry their own (a test's fakes)."""
    return replace(
        services,
        transcriber=services.transcriber or page_reader(models),
        native_search=services.native_search or native_searcher(models),
    )
