"""The model for each role: the engineer's choice in Settings, else the Recommended Setting.

Ranking is by `price_in + price_out`. A card with no price is never a default and never a
fallback: only the engineer can pick it. An on-device card (price 0) can be both. Nor is a model
its provider refused, one the price book marks deprecated, or a "-latest" alias (finding 12).
The model the engineer typed with a Standard Link is their own pick: it does every job, priced or
not.
"""

from decimal import Decimal

from qsone import settings
from qsone.engine.connectors import refused, standard
from qsone.engine.types import ModelCard, ModelChoice, Role

ROLES: tuple[Role, ...] = ("lead", "checker", "specialist", "quick")
LEAD_MODEL = "claude-opus-5-5"  # the Lead QS's default, when it is on the sheet


def _price(card: ModelCard) -> Decimal | None:
    if card.price_in is None or card.price_out is None:
        return None
    return card.price_in + card.price_out


def _ranked(sheet: list[ModelCard]) -> list[ModelCard]:
    """The priced cards, most expensive first (ties keep the sheet's order)."""
    return sorted((c for c in sheet if _price(c) is not None), key=_price, reverse=True)


def _eligible(card: ModelCard) -> bool:
    """ONE may pick it by itself: its provider serves it, the price book has not retired it, and
    it is no alias (the model behind "-latest", and so its price, changes unannounced)."""
    return not (card.retired or refused(card.choice) or card.choice.model.endswith("-latest"))


def typed_card(sheet: list[ModelCard]) -> ModelCard | None:
    """The first model the engineer typed with a link that is on the sheet and not refused."""

    def bare(model: str) -> str:
        return model.removeprefix("models/")

    for choice in standard.typed():
        for card in sheet:
            same = card.choice.connector == choice.connector
            if same and bare(card.choice.model) == bare(choice.model) and not refused(card.choice):
                return card
    return None


def defaults(sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """The Recommended Settings; empty when no card ONE may pick has a price.

    With a model the engineer typed: it does every job (the real walk: a Checking QS on another
    model surprised the engineer, and its check met a retired one). Otherwise:
    - Lead QS: `LEAD_MODEL`, else the most expensive model.
    - Checking QS: the most expensive model of another provider; with one provider, the most
      expensive other model (a Same-provider check); with one model, that model.
    - specialist: the middle price. quick: the cheapest.
    """
    typed = typed_card(sheet)
    if typed is not None:
        return dict.fromkeys(ROLES, typed.choice)
    ranked = _ranked([c for c in sheet if _eligible(c)])
    if not ranked:
        return {}
    lead = next((c for c in ranked if c.choice.model == LEAD_MODEL), ranked[0])
    checker = next(
        (c for c in ranked if c.provider != lead.provider),
        next((c for c in ranked if c.choice != lead.choice), lead),
    )
    return {
        "lead": lead.choice,
        "checker": checker.choice,
        "specialist": ranked[(len(ranked) - 1) // 2].choice,
        "quick": ranked[-1].choice,
    }


def saved() -> dict[Role, ModelChoice]:
    """The engineer's own choices. Plan 1's `lead_model` moves into the Lead QS's role here."""
    ai = settings.ai()
    found = ai.get("roles") if isinstance(ai.get("roles"), dict) else {}
    old = settings.load().get("lead_model")
    if old is not None:
        if "lead" not in found and isinstance(old, str) and old:
            found = found | {"lead": {"connector": "anthropic", "model": old}}
        try:
            settings.save_ai("roles", found)
            settings.remove("lead_model")
        except OSError:
            pass  # moved next time; the choice is the same either way
    return {
        role: ModelChoice(c["connector"], c["model"])
        for role, c in found.items()
        if role in ROLES
        and isinstance(c, dict)
        and isinstance(c.get("connector"), str)
        and isinstance(c.get("model"), str)
    }


def choose(role: Role, choice: ModelChoice) -> None:
    """Raises `OSError` when the settings file cannot be written."""
    current = {r: {"connector": c.connector, "model": c.model} for r, c in saved().items()}
    current[role] = {"connector": choice.connector, "model": choice.model}
    settings.save_ai("roles", current)


def chosen(sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """The engineer's choices over the defaults; a choice its provider refused gives way."""
    return defaults(sheet) | {r: c for r, c in saved().items() if not refused(c)}


def _failed_price(sheet: list[ModelCard], failed: ModelChoice) -> Decimal | None:
    return next((_price(c) for c in sheet if c.choice == failed), None)


def same_or_cheaper(
    sheet: list[ModelCard], failed: ModelChoice, avoid: set[ModelChoice]
) -> list[ModelChoice]:
    """Where a role moves without asking: the same price or cheaper, closest first.

    A failed model of unknown price has none: every move then needs the engineer's yes."""
    limit = _failed_price(sheet, failed)
    if limit is None:
        return []
    return [
        c.choice
        for c in _ranked(sheet)
        if _price(c) <= limit and c.choice != failed and c.choice not in avoid
    ]


def costlier(
    sheet: list[ModelCard], failed: ModelChoice, avoid: set[ModelChoice]
) -> list[ModelChoice]:
    """Where a role moves only after the engineer's yes: costlier, closest first."""
    limit = _failed_price(sheet, failed)
    return [
        c.choice
        for c in reversed(_ranked(sheet))
        if (limit is None or _price(c) > limit) and c.choice != failed and c.choice not in avoid
    ]
