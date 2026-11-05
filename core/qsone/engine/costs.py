"""Spending Caps per Brief, per day and per month, the one list of checks every AI call passes,
and the Brief Budget.

- The caps act in code only, before every model request; no cost text is ever sent to a model.
- The day is the engineer's own day, as the cost book counts it. The day cap counts the Briefs
  of every project and the General chat.
- At 80% of a cap One pauses and asks, once per scope in a Brief; at 100% it stops hard.
- A model whose price is unknown asks before it spends, because the cap cannot protect it.
- A model on this computer costs nothing and is never held back by a cap.
- The Claude subscription's cost is "equivalent cost": always recorded and shown, and counted
  towards the caps only when the engineer turns `subscription_stops` on. Otherwise One says so
  at 80% and carries on.

Money is `Decimal`, and goes out as text.
"""

import math
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import uuid4

from pydantic_ai.models.wrapper import WrapperModel

from qsone import copy, settings
from qsone.engine import cards
from qsone.engine.store import CostBook
from qsone.engine.types import Card, CostNotice, ModelCard, ModelChoice, Role, TeamHost, Text

Scope = Literal["brief", "day", "month"]


# Caps -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Caps:
    brief: Decimal  # USD
    day: Decimal
    month: Decimal
    budget_above: Decimal  # the Brief Budget card shows above this expected cost
    subscription_stops: bool  # the Claude subscription's equivalent cost counts towards the caps


# The Recommended Settings (founder question 1 and 2; change them here only).
RECOMMENDED = Caps(Decimal("3"), Decimal("15"), Decimal("150"), Decimal("0.50"), False)

_AMOUNTS = ("brief", "day", "month", "budget_above")
_EXACT = re.compile(r"[0-9]+(\.[0-9]+)?")  # as the Source Ledger's, without a sign


class CapNotExact(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def caps() -> Caps:
    """settings.json "ai.caps" over `RECOMMENDED`; an entry that is not exact is left out."""
    saved = settings.ai().get("caps")
    saved = saved if isinstance(saved, dict) else {}
    found = {
        name: Decimal(value)
        for name in _AMOUNTS
        if isinstance(value := saved.get(name), str) and _EXACT.fullmatch(value)
    }
    if isinstance(saved.get("subscription_stops"), bool):
        found["subscription_stops"] = saved["subscription_stops"]
    return replace(RECOMMENDED, **found)


def save_caps(changes: dict[str, object]) -> Caps:
    """Saves the caps given, as exact decimal text (USD), and `subscription_stops` as a bool.
    Raises `CapNotExact` naming the first field that is not, and `OSError`."""
    for name, value in changes.items():
        if name in _AMOUNTS and not (isinstance(value, str) and _EXACT.fullmatch(value)):
            raise CapNotExact(name)
        if name == "subscription_stops" and not isinstance(value, bool):
            raise CapNotExact(name)
        if name not in (*_AMOUNTS, "subscription_stops"):
            raise CapNotExact(name)
    saved = settings.ai().get("caps")
    saved = saved if isinstance(saved, dict) else {}
    settings.save_ai("caps", saved | changes)
    return caps()


def caps_json(value: Caps) -> dict:
    return {name: format(getattr(value, name), "f") for name in _AMOUNTS} | {
        "subscription_stops": value.subscription_stops
    }


def usd_text(amount: Decimal) -> str:
    """An amount as the engineer sees it in a card: USD with 2 decimals, Western digits."""
    return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


# The checks before every AI call -----------------------------------------------------------------


# Every AI call passes these first, in order; the first `Text` returned refuses the call and stops
# the Brief with that text. Plan 8 adds its consent check here.
AI_CALL_CHECKS: list[Callable[[ModelChoice], Text | None]] = []


class CallRefused(Exception):
    def __init__(self, text: Text) -> None:
        super().__init__(text["en"])
        self.text = text


class CapReached(Exception):
    """No further model request in this Brief. With `report`, the engineer asked for one last
    short Lead request that reports the work so far."""

    def __init__(self, scope: Scope, spent: Decimal, cap: Decimal, *, report: bool = False):
        super().__init__(f"Spending Cap for {scope} reached: {spent} of {cap} USD")
        self.scope = scope
        self.spent = spent
        self.cap = cap
        self.report = report


_SCOPE_NAMES: dict[Scope, Text] = {
    "brief": copy.SCOPE_BRIEF,
    "day": copy.SCOPE_DAY,
    "month": copy.SCOPE_MONTH,
}
REPORTED_BASIS = "reported by Claude Code"
PRICE_UNKNOWN_BASIS = "price unknown"


class Spending:
    """The Spending Caps over the cost book. One for the app: it remembers, for each Brief,
    which scopes it has asked about."""

    def __init__(self, book: CostBook, *, clock: Callable[[], datetime]):
        self.book = book
        self.clock = clock
        self._asked: dict[tuple[str, Scope], Decimal] = {}  # the cap each pause was asked at
        self._warned: set[tuple[str, Scope]] = set()  # equivalent cost said at 80%
        self._unpriced: set[tuple[str, ModelChoice]] = set()  # "yes" to an unknown price

    def _spent(self, brief_id: str, *, count_equivalent: bool) -> dict[Scope, Decimal]:
        today = self.clock().astimezone(self.book.local_tz).date()
        return {
            "brief": self.book.spent(brief_id=brief_id, count_equivalent=count_equivalent),
            "day": self.book.spent(day=today, count_equivalent=count_equivalent),
            "month": self.book.spent(
                month=(today.year, today.month), count_equivalent=count_equivalent
            ),
        }

    async def before_request(self, host: TeamHost, *, brief_id: str, card: ModelCard) -> None:
        """Returns when the request may go. Raises `CallRefused` or `CapReached`; awaits
        `host.ask` at 80% of a scope not yet asked in this Brief."""
        for check in AI_CALL_CHECKS:
            refusal = check(card.choice)
            if refusal is not None:
                raise CallRefused(refusal)
        if card.on_device:
            return
        limits = caps()
        if card.subscription and not limits.subscription_stops:
            self._say_equivalent(host, brief_id, limits)
            return
        if card.price_in is None or card.price_out is None:
            await self._ask_unknown_price(host, brief_id, card)
        spent = self._spent(brief_id, count_equivalent=limits.subscription_stops)
        limit = {"brief": limits.brief, "day": limits.day, "month": limits.month}
        for scope, cap in limit.items():
            if spent[scope] >= cap:
                host.emit(self._notice(brief_id, "stopped", scope, spent[scope], cap, card))
                raise CapReached(scope, spent[scope], cap)
        for scope, cap in limit.items():
            if spent[scope] < cap * Decimal("0.8") or self._asked.get((brief_id, scope)) == cap:
                continue
            self._asked[(brief_id, scope)] = cap
            notice = self._notice(brief_id, "paused", scope, spent[scope], cap, card)
            host.emit(notice)
            choice = await host.ask(
                Card(
                    uuid4().hex, "cap", copy.CAP_TITLE, notice.text, ("continue", "raise", "report")
                )
            )
            if choice == "report":
                raise CapReached(scope, spent[scope], cap, report=True)
            if choice == "raise":  # the screen saved the new caps: check against them
                return await self.before_request(host, brief_id=brief_id, card=card)

    async def _ask_unknown_price(self, host: TeamHost, brief_id: str, card: ModelCard) -> None:
        if (brief_id, card.choice) in self._unpriced:
            return
        detail = copy.fill(copy.PRICE_UNKNOWN, model=card.name)
        if await host.ask(Card(uuid4().hex, "cap", copy.CAP_TITLE, detail, ("yes", "no"))) != "yes":
            limits = caps()
            spent = self.book.spent(brief_id=brief_id, count_equivalent=limits.subscription_stops)
            raise CapReached("brief", spent, limits.brief)
        self._unpriced.add((brief_id, card.choice))

    def _say_equivalent(self, host: TeamHost, brief_id: str, limits: Caps) -> None:
        """The subscription is not held back: at 80% of a cap, One only says so, once."""
        both = self._spent(brief_id, count_equivalent=True)
        paid = self._spent(brief_id, count_equivalent=False)
        limit = {"brief": limits.brief, "day": limits.day, "month": limits.month}
        for scope, cap in limit.items():
            equivalent = both[scope] - paid[scope]
            if equivalent < cap * Decimal("0.8") or (brief_id, scope) in self._warned:
                continue
            self._warned.add((brief_id, scope))
            text = copy.fill(
                copy.CAP_EQUIVALENT,
                scope_name=_SCOPE_NAMES[scope],
                spent=usd_text(equivalent),
                cap=usd_text(cap),
            )
            host.emit(
                CostNotice(brief_id, "info", scope, usd_text(equivalent), usd_text(cap), True, text)
            )

    @staticmethod
    def _notice(
        brief_id: str,
        level: Literal["paused", "stopped"],
        scope: Scope,
        spent: Decimal,
        cap: Decimal,
        card: ModelCard,
    ) -> CostNotice:
        words = copy.CAP_PAUSED if level == "paused" else copy.CAP_STOPPED
        spent_text, cap_text = usd_text(spent), usd_text(cap)
        text = copy.fill(words, scope_name=_SCOPE_NAMES[scope], spent=spent_text, cap=cap_text)
        return CostNotice(brief_id, level, scope, spent_text, cap_text, card.subscription, text)

    def after_response(
        self,
        *,
        brief_id: str,
        project_id: str | None,
        run_id: str,
        role: Role,
        card: ModelCard,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
        reported_usd: Decimal | None = None,
        effort: str | None = None,
    ) -> Decimal | None:
        """Records one model response and gives its cost: the Model Data Sheet's price, or
        Claude Code's reported cost; None when the price is unknown (recorded as unknown).
        `effort` is the one it was sent with, recorded with it."""
        if card.on_device:
            usd, basis = Decimal(0), cards.ON_DEVICE
        elif card.subscription and reported_usd is not None:
            usd, basis = reported_usd, REPORTED_BASIS
        else:
            usd = cards.cost(
                card,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read=cache_read,
                cache_write=cache_write,
            )
            basis = PRICE_UNKNOWN_BASIS if usd is None else (card.price_source or "")
        self.book.add(
            brief_id=brief_id,
            project_id=project_id,
            run_id=run_id,
            role=role,
            choice=card.choice,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usd=usd,
            equivalent=card.subscription,
            basis=basis,
            at=self.clock(),
            effort=effort,
        )
        return usd

    def add_fee(
        self,
        *,
        brief_id: str,
        project_id: str | None,
        run_id: str,
        role: Role,
        choice: ModelChoice,
        usd: Decimal,
        basis: str,
    ) -> None:
        """Records a provider's fee beyond tokens (Anthropic's per-search fee), with its source,
        so the caps count it like any cost."""
        self.book.add(
            brief_id=brief_id,
            project_id=project_id,
            run_id=run_id,
            role=role,
            choice=choice,
            input_tokens=0,
            output_tokens=0,
            usd=usd,
            equivalent=False,
            basis=basis,
            at=self.clock(),
        )


class CostedModel(WrapperModel):
    """Calls `Spending.before_request` before each request and `after_response` after it, so
    no request goes out past a cap and every response is in the cost book."""

    def __init__(
        self,
        wrapped,
        *,
        spending: Spending,
        host: TeamHost,
        brief_id: str,
        project_id: str | None,
        run_id: str,
        role: Role,
        card: ModelCard,
        effort: str | None = None,
    ):
        super().__init__(wrapped)
        self.spending = spending
        self.host = host
        self.brief_id = brief_id
        self.project_id = project_id
        self.run_id = run_id
        self.role = role
        self.card = card
        self.effort = effort  # the run's own `thinking` setting, recorded with each cost

    async def _before(self) -> None:
        await self.spending.before_request(self.host, brief_id=self.brief_id, card=self.card)

    def _record(self, usage) -> None:
        self.spending.after_response(
            brief_id=self.brief_id,
            project_id=self.project_id,
            run_id=self.run_id,
            role=self.role,
            card=self.card,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read=usage.cache_read_tokens,
            cache_write=usage.cache_write_tokens,
            effort=self.effort,
        )

    async def request(self, messages, model_settings, model_request_parameters):
        await self._before()
        response = await super().request(messages, model_settings, model_request_parameters)
        self._record(response.usage)
        return response

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        await self._before()
        async with self.wrapped.request_stream(
            messages, model_settings, model_request_parameters, run_context
        ) as stream:
            try:
                yield stream
            finally:  # a stopped stream still cost what it used
                usage = stream.usage
                if usage.input_tokens or usage.output_tokens:
                    self._record(usage)


def summary(book: CostBook | None, *, brief_id: str | None, now: datetime) -> dict:
    """What `GET /costs` answers: the money spent in the Brief (when given), today and this
    month, the equivalent cost on the Claude subscription apart, and the caps. Exact text.
    `book` is None while there is no cost book yet."""

    def amounts(count_equivalent: bool) -> dict[str, Decimal | None]:
        if book is None:
            return {"brief": None if brief_id is None else Decimal(0)} | dict.fromkeys(
                ("today", "month"), Decimal(0)
            )
        today = now.astimezone(book.local_tz).date()
        return {
            "brief": None
            if brief_id is None
            else book.spent(brief_id=brief_id, count_equivalent=count_equivalent),
            "today": book.spent(day=today, count_equivalent=count_equivalent),
            "month": book.spent(month=(today.year, today.month), count_equivalent=count_equivalent),
        }

    def text(values: dict[str, Decimal | None]) -> dict[str, str | None]:
        return {k: None if v is None else format(v, "f") for k, v in values.items()}

    paid, both = amounts(False), amounts(True)
    equivalent = {k: None if v is None else both[k] - v for k, v in paid.items()}
    return text(paid) | {"equivalent": text(equivalent), "caps": caps_json(caps())}


# The Brief Budget --------------------------------------------------------------------------------


ASSUMED_TOKENS = (20_000, 1_500)  # in and out per request, until this project has measured runs
SECONDS_PER_REQUEST = 20


@dataclass(frozen=True)
class Budget:
    usd: Decimal | None  # None when a model in the plan has no known price
    minutes: int
    basis: Text  # BASIS_MEASURED or BASIS_ASSUMED


def brief_budget(
    plan: list[dict],
    sheet: list[ModelCard],
    roles: dict[Role, ModelChoice],
    measured: tuple[int, int, int] | None,
    lead_measured: tuple[int, int, int] | None | Literal["same"] = "same",
) -> Budget:
    """The expected cost and time of a Brief's plan. Plan items are {"tier": Role, "requests":
    int}; `measured` is `CostBook.tokens_per_request` for this project, and `lead_measured` the
    same at the Lead QS's effort in this Brief ("same": `measured`), since each effort thinks
    for its own length. Each request costs the tier's model price for the measured (or assumed)
    tokens per request, and takes 20 s. The basis is measured only when every tier's is."""
    lead_measured = measured if lead_measured == "same" else lead_measured
    by_choice = {card.choice: card for card in sheet}
    usd: Decimal | None = Decimal(0)
    requests = 0
    for item in plan:
        requests += item["requests"]
        found = lead_measured if item["tier"] == "lead" else measured
        tokens_in, tokens_out = ASSUMED_TOKENS if found is None else found[:2]
        card = by_choice.get(roles.get(item["tier"]))
        each = (
            None
            if card is None
            else cards.cost(card, input_tokens=tokens_in, output_tokens=tokens_out)
        )
        usd = None if usd is None or each is None else usd + item["requests"] * each
    if measured is None or lead_measured is None:
        basis = copy.BASIS_ASSUMED
    else:
        n = measured[2] + (0 if lead_measured is measured else lead_measured[2])
        basis = copy.fill(copy.BASIS_MEASURED, n=n)
    return Budget(usd, math.ceil(requests * SECONDS_PER_REQUEST / 60), basis)
