"""The model for each role: the engineer's choice in Settings, else the Recommended Setting.

Ranking is by `price_in + price_out`. A card with no price is never a default and never a
fallback: only the engineer can pick it. An on-device card (price 0) can be both. Nor is a model
its provider refused, one the price book marks deprecated, or a "-latest" alias (finding 12).
The engineer's selected model leads and sets the other roles to the same model. Automatic
alternatives require known prices at or below that model's known price; an unknown price keeps
all roles on it. Only explicit role choices may upgrade. Fresh defaults retain price ranking.
"""

from decimal import Decimal

from qsone import settings
from qsone.engine.connectors import allow_model, refused, standard
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


def _around(typed: ModelCard, sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """The typed model leads and does the specialists' work; no role goes to a costlier model.

    - Checking QS: the most expensive model of another provider at or under its price; else
      another model of its provider at or under it (a Same-provider check); else the typed model.
    - quick: the cheapest model of its provider under its price; else the typed model.
    A typed model of unknown price does every job: nothing can be said to cost less."""
    limit = _price(typed)
    under = [
        c
        for c in _ranked(sheet)
        if limit is not None and _eligible(c) and c.choice != typed.choice and _price(c) <= limit
    ]
    checker = next((c for c in under if c.provider != typed.provider), next(iter(under), typed))
    quick = next(
        (c for c in reversed(under) if c.provider == typed.provider and _price(c) < limit), typed
    )
    return {
        "lead": typed.choice,
        "checker": checker.choice,
        "specialist": typed.choice,
        "quick": quick.choice,
    }


def defaults(sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """The Recommended Settings; empty when no card ONE may pick has a price.

    With a typed model, use it or known-price alternatives no costlier than it. If its price
    is unknown, every role uses it. A stronger role requires the engineer's explicit choice.
    Without a typed model:
    - Lead QS: `LEAD_MODEL`, else the most expensive model.
    - Checking QS: the most expensive model of another provider; with one provider, the most
      expensive other model (a Same-provider check); with one model, that model.
    - specialist: the middle price. quick: the cheapest.
    """
    typed = typed_card(sheet)
    if typed is not None:
        return _around(typed, sheet)
    for choice in standard.typed():
        card = next(
            (
                c
                for c in sheet
                if c.choice.connector == choice.connector
                and c.choice.model.removeprefix("models/") == choice.model.removeprefix("models/")
            ),
            None,
        )
        if card is None:
            if not refused(choice):
                # An absent typed model has no sourced price either.
                return dict.fromkeys(ROLES, choice)
            return {}
        # A refused typed model may only give way to known-price, cheaper alternatives.
        alternatives = same_or_cheaper(sheet, card.choice, set())
        if not alternatives:
            return {}
        replacement = next(c for c in sheet if c.choice == alternatives[0])
        return _around(replacement, sheet)
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
    """A new Lead QS clears the other roles' saved choices: they follow the lead again
    (`chosen`), never costlier than it. Another role's choice is the engineer's own override.

    Raises `OSError` when the settings file cannot be written.
    """
    current = {r: {"connector": c.connector, "model": c.model} for r, c in saved().items()}
    if role == "lead":
        current = {}
    current[role] = {"connector": choice.connector, "model": choice.model}
    settings.save_ai("roles", current)
    allow_model(choice)


def chosen(sheet: list[ModelCard]) -> dict[Role, ModelChoice]:
    """Explicit roles override a team bounded by the engineer's lead, when selected.

    A refused choice gives way; without a selected lead, fresh defaults retain their ranking.
    """
    selected = saved()
    explicit = {r: c for r, c in selected.items() if not refused(c)}
    lead = selected.get("lead")
    if lead is None:
        return defaults(sheet) | explicit
    if refused(lead):
        alternatives = same_or_cheaper(sheet, lead, set())
        if not alternatives:
            return explicit
        lead = alternatives[0]
    card = next((c for c in sheet if c.choice == lead), None)
    team = _around(card, sheet) if card is not None else dict.fromkeys(ROLES, lead)
    return team | explicit


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
        if _eligible(c) and _price(c) <= limit and c.choice != failed and c.choice not in avoid
    ]


def costlier(
    sheet: list[ModelCard], failed: ModelChoice, avoid: set[ModelChoice]
) -> list[ModelChoice]:
    """Where a role moves only after the engineer's yes: costlier, closest first."""
    limit = _failed_price(sheet, failed)
    return [
        c.choice
        for c in reversed(_ranked(sheet))
        if _eligible(c)
        and (limit is None or _price(c) > limit)
        and c.choice != failed
        and c.choice not in avoid
    ]


def available(sheet, current):
    """Refresh stale per-request choices while retaining available explicit picks."""
    return chosen(list(sheet)) | {r: c for r, c in current.items() if not refused(c)}


async def select_lead(choice, sheet, found, on_usage=None):
    """Apply a model switch and validate the cheaper automatic quick candidate once."""
    from qsone.engine import connectors

    typed = next(
        (
            c
            for c in sheet
            if c.choice.connector == choice.connector
            and c.choice.model.removeprefix("models/") == choice.model.removeprefix("models/")
        ),
        None,
    )
    if typed is None:
        choose("lead", choice)
        return
    # Remove old explicit roles only after the new connection has been checked.
    picked = _around(typed, sheet)
    while picked["quick"] != typed.choice:
        quick = picked["quick"]
        used = []
        failed = await connectors.check(
            f"{quick.connector}/{quick.model}", among=found, on_usage=used.append
        )
        if used and on_usage is not None:
            card = next(c for c in sheet if c.choice == quick)
            on_usage(card, used[0])
        if failed is None:
            break
        # A transient failure must not select this candidate either, but only a
        # provider refusal is persisted by check(). Keep retries bounded locally.
        sheet = [c for c in sheet if c.choice != quick]
        picked = _around(typed, sheet)
    settings.save_ai(
        "roles", {r: {"connector": c.connector, "model": c.model} for r, c in picked.items()}
    )
    allow_model(typed.choice)
