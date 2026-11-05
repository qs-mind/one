"""The Model Data Sheet: every model of every connector, with its price and the price's source.

- Prices come from genai-prices (pinned); the source is "genai-prices <version>: <pricing URL>".
- The engineer may enter a price, which wins; its source is "engineer, <the day entered>".
- A model on this computer costs 0 ("on-device").
- Otherwise the price is unknown (None), never guessed.

Money is `Decimal`, in USD per million tokens.
"""

import asyncio
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import genai_prices
import httpx2
from genai_prices import data_snapshot
from genai_prices.types import ModelPrice, TieredPrices

from qsone import settings
from qsone.engine import connectors
from qsone.engine.types import ModelCard, ModelChoice, Text

GENAI = f"genai-prices {genai_prices.__version__}"
ON_DEVICE = "on-device"
MILLION = Decimal(1_000_000)

_EXACT = re.compile(r"[0-9]+(\.[0-9]+)?")  # as the Source Ledger's, without a sign

log = logging.getLogger("qsone.engine.cards")


class PriceNotExact(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field  # "in" or "out"


def _key(choice: ModelChoice) -> str:
    return f"{choice.connector}/{choice.model}"


def _entered(choice: ModelChoice) -> dict | None:
    prices = settings.ai().get("prices")
    entry = prices.get(_key(choice)) if isinstance(prices, dict) else None
    if not isinstance(entry, dict):
        return None
    if not all(isinstance(entry.get(f), str) for f in ("in", "out", "entered")):
        return None
    if not (_EXACT.fullmatch(entry["in"]) and _EXACT.fullmatch(entry["out"])):
        return None
    return entry


def _base(price: Decimal | TieredPrices | None) -> Decimal | None:
    """A tiered price shows its first tier (prompts under the first threshold)."""
    return price.base if isinstance(price, TieredPrices) else price


def _book_name(model: str) -> str:
    """The model's name as the price book knows it: Google's OpenAI-compatible list names
    "models/gemini-…", the book "gemini-…" (audit B6)."""
    return model.removeprefix("models/")


def _genai(card: ModelCard) -> tuple[ModelPrice, str, bool] | None:
    """genai-prices' price for the card's model at its own provider, its source text, and
    whether the book marks the model deprecated."""
    try:
        provider, model = data_snapshot.get_snapshot().find_provider_model(
            _book_name(card.choice.model), None, card.provider, None
        )
    except LookupError:  # an unknown provider, or a model it does not list
        return None
    url = (provider.pricing_urls or [None])[0]
    source = f"{GENAI}: {url}" if url else GENAI
    return model.get_prices(datetime.now(UTC)), source, bool(model.deprecated)


def priced(card: ModelCard) -> ModelCard:
    """The card with its price and the price's source filled in."""
    entered = _entered(card.choice)
    if entered is not None:
        return replace(
            card,
            price_in=Decimal(entered["in"]),
            price_out=Decimal(entered["out"]),
            price_source=f"engineer, {entered['entered']}",
        )
    if card.on_device:
        return replace(card, price_in=Decimal(0), price_out=Decimal(0), price_source=ON_DEVICE)
    found = _genai(card)
    if found is None:
        return card  # unknown stays unknown; a price the connector gave itself stays
    price, source, retired = found
    price_in, price_out = _base(price.input_mtok), _base(price.output_mtok)
    if price_in is None or price_out is None:
        return replace(card, retired=retired)
    return replace(
        card, price_in=price_in, price_out=price_out, price_source=source, retired=retired
    )


def cost(
    card: ModelCard,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> Decimal | None:
    """USD for one response, or None when the price is unknown.

    `input_tokens` counts cache reads and writes too, as PydanticAI's usage does. A
    genai-prices card is costed by genai-prices (its tiers and cache prices); any other card
    counts every input token at its input price."""
    if card.price_in is None or card.price_out is None:
        return None
    if card.price_source is not None and card.price_source.startswith(GENAI):
        usage = genai_prices.Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
        )
        try:
            return genai_prices.calc_price(
                usage, _book_name(card.choice.model), provider_id=card.provider
            ).total_price
        except LookupError:
            pass  # a card a connector priced itself, under another name
    return (input_tokens * card.price_in + output_tokens * card.price_out) / MILLION


def enter_price(
    choice: ModelChoice,
    price_in: str,
    price_out: str,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> str:
    """Saves the engineer's price (USD per million tokens, exact decimal text); gives the day
    it was entered, the engineer's own day. Raises `PriceNotExact` and `OSError`."""
    for field, value in (("in", price_in), ("out", price_out)):
        if not _EXACT.fullmatch(value):
            raise PriceNotExact(field)
    entered = clock().astimezone().date().isoformat()
    prices = settings.ai().get("prices")
    prices = prices if isinstance(prices, dict) else {}
    entry = {"in": price_in, "out": price_out, "entered": entered}
    settings.save_ai("prices", prices | {_key(choice): entry})
    return entered


async def listed(
    found: Sequence[connectors.Connector],
) -> tuple[list[ModelCard], dict[str, Text]]:
    """The priced sheet of `found`, and the plain reason for each connector that did not list.

    One connector that does not answer never hides the others."""
    answers = await asyncio.gather(*(c.cards() for c in found), return_exceptions=True)
    sheet: list[ModelCard] = []
    errors: dict[str, Text] = {}
    for connector, answer in zip(found, answers, strict=True):
        if isinstance(answer, connectors.PROVIDER_ERRORS):
            log.warning("Listing the models of %s failed: %s", connector.id, answer)
            errors[connector.id] = connectors.plain_error(answer, connector.name)
        elif isinstance(answer, BaseException):
            raise answer
        else:
            sheet += [priced(card) for card in answer]
    return sheet, errors


async def sheet(*, http_client: httpx2.AsyncClient | None = None) -> list[ModelCard]:
    """Every model of every connector, priced."""
    found, _ = await listed(connectors.connectors(http_client=http_client))
    return found
