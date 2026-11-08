from dataclasses import replace
from decimal import Decimal

from qsone.engine import roles
from tests.engine_fakes import HAIKU, OPUS


def test_cheapest_requires_tools_known_prices_and_eligible_model():
    excluded = [
        replace(HAIKU, tools=False),
        replace(HAIKU, price_in=None),
        replace(HAIKU, retired=True),
    ]
    for card in excluded:
        assert roles.cheapest([card, OPUS]) == {"anthropic": OPUS.choice}
    cheap = replace(HAIKU, price_in=Decimal("0.1"), price_out=Decimal("0.2"))
    assert roles.cheapest([OPUS, cheap]) == {"anthropic": cheap.choice}


def test_cheapest_excludes_aliases_and_refused_models():
    from qsone.engine import connectors
    from qsone.engine.types import ModelChoice

    alias = replace(HAIKU, choice=ModelChoice("anthropic", "sample-latest"))
    connectors.note_refused(HAIKU.choice)
    assert roles.cheapest([alias, HAIKU, OPUS]) == {"anthropic": OPUS.choice}


async def test_settings_exposes_cheapest_per_connection(data_dir, monkeypatch):
    from qsone.engine import cards
    from qsone.engine.routes import settings_router

    async def listed(found):
        return [HAIKU, OPUS], {}

    monkeypatch.setattr(cards, "listed", listed)
    router = settings_router()
    # Call the owning endpoint directly with scripted model cards.
    endpoint = next(
        route.endpoint for route in router.routes if getattr(route, "path", None) == "/settings/ai"
    )
    body = await endpoint()
    assert body["cheapest"] == {
        "anthropic": {"connector": HAIKU.choice.connector, "model": HAIKU.choice.model}
    }
