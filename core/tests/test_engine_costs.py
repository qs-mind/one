"""Plan 4 Task 6: Spending Caps per Brief, day and month, the one list of checks every AI call
passes, and the Brief Budget.

Every price here is a sample price or genai-prices' own; no test calls a real AI.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent

from qsone import copy, settings
from qsone.app import create_app
from qsone.engine import cards, costs, general
from qsone.engine.costs import (
    RECOMMENDED,
    Budget,
    CallRefused,
    CapReached,
    CostedModel,
    Spending,
    brief_budget,
)
from qsone.engine.store import CostBook
from qsone.engine.types import CostNotice, ModelCard, ModelChoice
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import HAIKU, OPUS, SAMPLE_SHEET, SONNET, FakeHost, scripted, text

CAIRO = timezone(timedelta(hours=2), "Cairo")  # Egypt's winter time, fixed for the test
RIYADH = timezone(timedelta(hours=3), "Riyadh")

UNKNOWN = ModelCard(
    choice=ModelChoice("standard:lab", "lab-model"),
    name="lab-model",
    provider="lab",
    images=False,
    tools=True,
    context=None,
    price_in=None,
    price_out=None,
    price_source=None,
)
LOCAL = replace(
    UNKNOWN,
    choice=ModelChoice("standard:local", "qwen-local"),
    name="qwen-local",
    price_in=Decimal(0),
    price_out=Decimal(0),
    price_source=cards.ON_DEVICE,
    on_device=True,
)
CLAUDE_CODE = replace(SONNET, choice=ModelChoice("claude-code", "sonnet"), subscription=True)


@pytest.fixture
def book(general):
    return CostBook(general, local_tz=CAIRO)


@pytest.fixture
def spending(book, fake_clock):
    # these are about the Spending Caps; the Brief Budget card has its own tests
    # (test_realwalk_stops)
    costs.save_caps({"budget_above": "100"})
    return Spending(book, clock=fake_clock)  # 2026-11-05 08:00 UTC, 10:00 in Cairo


@pytest.fixture
def host():
    return FakeHost(brief_id="b1")


def book_add(
    book: CostBook,
    *,
    brief: str,
    usd: str | None,
    project: str | None = "p1",
    at: datetime = datetime(2026, 11, 5, 7, 0, tzinfo=UTC),
    equivalent: bool = False,
) -> None:
    book.add(
        brief_id=brief,
        project_id=project,
        run_id="r1",
        role="lead",
        choice=SONNET.choice,
        input_tokens=1000,
        output_tokens=100,
        usd=None if usd is None else Decimal(usd),
        equivalent=equivalent,
        basis="sample",
        at=at,
    )


def notices(host: FakeHost) -> list[CostNotice]:
    return [e for e in host.events if isinstance(e, CostNotice)]


def cost_rows(rec) -> list[tuple]:
    with rec.read() as c:
        return c.execute(
            "SELECT brief_id, project_id, run_id, role, connector, model, input_tokens,"
            " output_tokens, usd, equivalent, basis FROM ai_costs ORDER BY id"
        ).fetchall()


# Caps ------------------------------------------------------------------------------------------


def test_recommended_caps_are_the_defaults():
    assert costs.caps() == RECOMMENDED
    assert RECOMMENDED.brief == Decimal("3") and RECOMMENDED.day == Decimal("15")
    assert RECOMMENDED.month == Decimal("150") and RECOMMENDED.budget_above == Decimal("0.50")
    assert RECOMMENDED.subscription_stops is False


def test_saved_caps_win_and_a_broken_entry_falls_back():
    costs.save_caps({"brief": "2.50", "subscription_stops": True})
    assert costs.caps() == replace(RECOMMENDED, brief=Decimal("2.50"), subscription_stops=True)
    settings.save_ai("caps", {"brief": 2.5, "day": "1,000", "month": "90"})  # typed by hand
    assert costs.caps() == replace(RECOMMENDED, month=Decimal("90"))


def test_caps_must_be_exact_decimal_text():
    for value in ("1,000", "1e3", "-1", " 3", "3.", 3, 2.5):
        with pytest.raises(costs.CapNotExact) as refused:
            costs.save_caps({"day": value})
        assert refused.value.field == "day"
    assert costs.caps() == RECOMMENDED  # nothing saved


async def test_pause_at_80_percent_of_the_brief_cap(spending, host, book):
    book_add(book, brief="b1", usd="2.41")  # cap 3.00
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    card = host.cards[-1]
    assert card.kind == "cap" and card.options == ("continue", "raise", "report")
    assert "2.41" in card.detail["ar"] and "3.00" in card.detail["en"]
    assert card.detail == copy.fill(
        copy.CAP_PAUSED, scope_name=copy.SCOPE_BRIEF, spent="2.41", cap="3.00"
    )
    [notice] = notices(host)
    assert (notice.level, notice.scope, notice.spent, notice.cap) == (
        "paused",
        "brief",
        "2.41",
        "3.00",
    )
    assert notice.equivalent is False
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert len(host.cards) == 1  # asked once


async def test_below_80_percent_nothing_is_asked(spending, host, book):
    book_add(book, brief="b1", usd="2.39")
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert host.cards == [] and host.events == []


async def test_stop_at_the_cap(spending, host, book):
    book_add(book, brief="b1", usd="2.00")
    book_add(book, brief="b1", usd="1.00")
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=SONNET)
    assert (stopped.value.scope, stopped.value.spent, stopped.value.cap) == (
        "brief",
        Decimal("3.00"),
        Decimal("3"),
    )
    assert stopped.value.report is False
    assert host.cards == []  # a hard stop asks nothing
    [notice] = notices(host)
    assert (notice.level, notice.scope, notice.spent, notice.cap) == (
        "stopped",
        "brief",
        "3.00",
        "3.00",
    )
    assert notice.text == copy.fill(
        copy.CAP_STOPPED, scope_name=copy.SCOPE_BRIEF, spent="3.00", cap="3.00"
    )


async def test_report_choice_ends_with_a_report(spending, host, book):
    book_add(book, brief="b1", usd="2.50")
    host.answers["cap"] = "report"
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=SONNET)
    assert stopped.value.report is True and stopped.value.scope == "brief"
    # The one last short Lead request for the report is not asked again.
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert len(host.cards) == 1


async def test_raise_asks_again_only_against_the_new_cap(spending, host, book):
    book_add(book, brief="b1", usd="2.50")
    asking = asyncio.create_task(spending.before_request(host, brief_id="b1", card=SONNET))
    while not host.cards:
        await asyncio.sleep(0)
    costs.save_caps({"brief": "5"})  # the screen saves the new cap before it answers
    host.settle(host.cards[0].id, "raise")
    await asking
    assert len(host.cards) == 1  # 2.50 of 5.00 is under 80%
    book_add(book, brief="b1", usd="1.60")  # 4.10 of 5.00
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert len(host.cards) == 2 and "5.00" in host.cards[-1].detail["en"]


async def test_raise_without_a_new_cap_does_not_ask_twice(spending, host, book):
    book_add(book, brief="b1", usd="2.50")
    host.answers["cap"] = "raise"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert len(host.cards) == 1


async def test_day_cap_counts_every_project(spending, host, book):
    book_add(book, brief="b2", usd="6.05", project="p1")
    book_add(book, brief="b3", usd="6.05", project="p2")
    book_add(book, brief="b4", usd="1.00", project=None)  # the General chat
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    [card] = host.cards
    assert card.detail == copy.fill(
        copy.CAP_PAUSED, scope_name=copy.SCOPE_DAY, spent="13.10", cap="15.00"
    )
    assert notices(host)[0].scope == "day"


async def test_month_cap(spending, host, book):
    book_add(book, brief="b2", usd="100", at=datetime(2026, 11, 1, 9, tzinfo=CAIRO))
    book_add(book, brief="b3", usd="21", at=datetime(2026, 11, 3, 9, tzinfo=CAIRO))
    book_add(book, brief="b0", usd="500", at=datetime(2026, 10, 31, 21, tzinfo=CAIRO))  # October
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    [card] = host.cards
    assert card.detail == copy.fill(
        copy.CAP_PAUSED, scope_name=copy.SCOPE_MONTH, spent="121.00", cap="150.00"
    )
    book_add(book, brief="b3", usd="29", at=datetime(2026, 11, 4, 9, tzinfo=CAIRO))
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=SONNET)
    assert stopped.value.scope == "month" and stopped.value.spent == Decimal("150")


async def test_every_scope_is_asked_once(spending, host, book):
    book_add(book, brief="b1", usd="2.50")
    book_add(book, brief="b2", usd="10.00")  # day 12.50 of 15
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert [n.scope for n in notices(host)] == ["brief", "day"]
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert len(host.cards) == 2


async def test_stops_come_before_pauses(spending, host, book):
    book_add(book, brief="b1", usd="2.50")  # brief at 83%
    book_add(book, brief="b2", usd="12.50")  # day at 100%
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=SONNET)
    assert stopped.value.scope == "day" and host.cards == []


async def test_the_day_is_the_engineers_local_day(general, host, fake_clock):
    book = CostBook(general, local_tz=RIYADH)
    spending = Spending(book, clock=fake_clock)
    # 23:00 on 5 November in Riyadh, but already 6 November nowhere else that matters here.
    book_add(book, brief="b2", usd="15", at=datetime(2026, 11, 5, 20, 0, tzinfo=UTC))
    fake_clock.now = datetime(2026, 11, 5, 21, 30, tzinfo=UTC)  # 00:30 on 6 November in Riyadh
    await spending.before_request(host, brief_id="b1", card=SONNET)
    assert host.cards == [] and host.events == []
    fake_clock.now = datetime(2026, 11, 5, 20, 30, tzinfo=UTC)  # 23:30 on 5 November in Riyadh
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=SONNET)
    assert stopped.value.scope == "day"


async def test_unknown_price_asks_once_with_a_price_card(spending, host):
    """Audit B6: the hold «استخدمه» came back on every message. The first use of a model with no
    known price shows one card: its price, or use it without a price cap."""
    host.answers["price"] = "no"
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    assert stopped.value.scope == "brief"
    [card] = host.cards
    assert card.kind == "price" and card.options == ("price", "nocap", "no")
    assert card.payload == {
        "model": {"connector": "standard:lab", "model": "lab-model", "name": "lab-model"}
    }
    assert card.detail == copy.fill(copy.PRICE_UNKNOWN, model="lab-model")


class PricingHost(FakeHost):
    """Answers the price card as the screen does: it saves the price, then says "price"."""

    async def ask(self, card):
        self.cards.append(card)
        cards.enter_price(card_choice(card), "0.25", "1.50")
        return "price"


def card_choice(card) -> ModelChoice:
    model = card.payload["model"]
    return ModelChoice(model["connector"], model["model"])


async def test_a_price_entered_in_the_card_is_kept_and_counted(spending, book):
    host = PricingHost(brief_id="b1")
    card = await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    assert card.price_in == Decimal("0.25") and card.price_source.startswith("engineer, ")
    await spending.before_request(host, brief_id="b2", card=UNKNOWN)  # another Brief: no card
    assert len(host.cards) == 1


async def test_use_without_a_price_cap_is_remembered_per_model(spending, host):
    host.answers["price"] = "nocap"
    await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    await spending.before_request(host, brief_id="b2", card=UNKNOWN)  # remembered, not per Brief
    assert len(host.cards) == 1
    other = replace(UNKNOWN, choice=ModelChoice("standard:lab", "lab-model-2"), name="lab-model-2")
    await spending.before_request(host, brief_id="b1", card=other)
    assert len(host.cards) == 2  # an answer for one model is not one for another


def add_tokens(book: CostBook, brief: str, tokens: int) -> None:
    book.add(
        brief_id=brief,
        project_id="p1",
        run_id="r1",
        role="lead",
        choice=UNKNOWN.choice,
        input_tokens=tokens,
        output_tokens=0,
        usd=None,
        equivalent=False,
        basis=costs.PRICE_UNKNOWN_BASIS,
        at=datetime(2026, 11, 5, 7, 0, tzinfo=UTC),
    )


async def test_without_a_price_the_caps_count_tokens(spending, host, book):
    host.answers["price"] = "nocap"
    await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    # a Brief cap of 3 USD is 3,000,000 tokens of a model with no price
    add_tokens(book, "b1", 2_500_000)
    host.answers["cap"] = "continue"
    await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    [pause] = [c for c in host.cards if c.kind == "cap"]
    assert "2,500,000 of 3,000,000 tokens" in pause.detail["en"]
    add_tokens(book, "b1", 600_000)
    with pytest.raises(CapReached) as stopped:
        await spending.before_request(host, brief_id="b1", card=UNKNOWN)
    assert stopped.value.scope == "brief"
    assert "3,100,000 of 3,000,000 tokens" in notices(host)[-1].text["en"]


async def test_unknown_price_still_stops_at_the_cap(spending, host, book):
    book_add(book, brief="b1", usd="3.00")
    host.answers["price"] = "nocap"
    with pytest.raises(CapReached):
        await spending.before_request(host, brief_id="b1", card=UNKNOWN)


def test_costs_count_tokens_and_say_when_a_price_is_unknown(book):
    """Audit B6: Costs showed 0 today and this month after paid calls of a model with no price.
    The tokens are counted always; an unknown cost is said, never a false 0."""
    book_add(book, brief="b1", usd="0.50")
    add_tokens(book, "b1", 40_000)
    now = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
    found = costs.summary(book, brief_id="b1", now=now)
    assert found["today"] == "0.50" and found["unpriced"]["today"] == 1
    assert found["tokens"]["today"] == {"input": 41_000, "output": 100}
    assert found["tokens"]["brief"] == {"input": 41_000, "output": 100}
    empty = costs.summary(None, brief_id=None, now=now)
    assert empty["unpriced"]["today"] == 0 and empty["tokens"]["today"] == {"input": 0, "output": 0}


async def test_on_device_is_free_and_never_asks(spending, host, book, general):
    book_add(book, brief="b1", usd="5.00")  # over every cap but the month's
    await spending.before_request(host, brief_id="b1", card=LOCAL)
    assert host.cards == [] and host.events == []
    usd = spending.after_response(
        brief_id="b1",
        project_id="p1",
        run_id="r2",
        role="quick",
        card=LOCAL,
        input_tokens=5000,
        output_tokens=300,
    )
    assert usd == Decimal(0)
    assert cost_rows(general)[-1][-3:] == ("0", 0, cards.ON_DEVICE)


def test_after_response_records_the_cards_cost_and_its_source(spending, general):
    usd = spending.after_response(
        brief_id="b1",
        project_id="p1",
        run_id="r1",
        role="specialist",
        card=SONNET,
        input_tokens=20_000,
        output_tokens=1_500,
    )
    assert usd == Decimal("0.0825")  # 20,000 x 3 + 1,500 x 15, per million (sample prices)
    assert cost_rows(general) == [
        (
            "b1",
            "p1",
            "r1",
            "specialist",
            "anthropic",
            "claude-sonnet-5-5",
            20_000,
            1_500,
            "0.0825",
            0,
            SONNET.price_source,
        )
    ]


def test_an_unknown_cost_is_kept_unknown(spending, general):
    usd = spending.after_response(
        brief_id="b1",
        project_id="p1",
        run_id="r1",
        role="lead",
        card=UNKNOWN,
        input_tokens=100,
        output_tokens=10,
    )
    assert usd is None and cost_rows(general)[0][-3:] == (None, 0, costs.PRICE_UNKNOWN_BASIS)


# The Claude subscription ------------------------------------------------------------------------


async def test_subscription_cost_is_equivalent_and_does_not_stop_by_default(spending, host, book):
    usd = spending.after_response(
        brief_id="b1",
        project_id="p1",
        run_id="r1",
        role="lead",
        card=CLAUDE_CODE,
        input_tokens=1000,
        output_tokens=100,
        reported_usd=Decimal("2.90"),
    )
    assert usd == Decimal("2.90")
    with book.rec.read() as c:
        assert c.execute("SELECT usd, equivalent, basis FROM ai_costs").fetchall() == [
            ("2.90", 1, costs.REPORTED_BASIS)
        ]
    assert book.spent(brief_id="b1", count_equivalent=False) == Decimal(0)

    await spending.before_request(host, brief_id="b1", card=CLAUDE_CODE)
    assert host.cards == []  # warned, never paused
    [notice] = notices(host)
    assert (notice.level, notice.scope, notice.spent, notice.cap) == (
        "info",
        "brief",
        "2.90",
        "3.00",
    )
    assert notice.equivalent is True
    assert notice.text == copy.fill(
        copy.CAP_EQUIVALENT, scope_name=copy.SCOPE_BRIEF, spent="2.90", cap="3.00"
    )
    book_add(book, brief="b1", usd="1.00", equivalent=True)  # 3.90 of 3.00, equivalent
    await spending.before_request(host, brief_id="b1", card=CLAUDE_CODE)
    assert len(notices(host)) == 1  # warned once
    await spending.before_request(host, brief_id="b1", card=SONNET)  # paid work is not held back
    assert host.cards == []


async def test_the_subscription_stops_when_the_engineer_turns_it_on(spending, host, book):
    costs.save_caps({"subscription_stops": True})
    book_add(book, brief="b1", usd="3.00", equivalent=True)
    with pytest.raises(CapReached):
        await spending.before_request(host, brief_id="b1", card=CLAUDE_CODE)
    assert notices(host)[0].equivalent is True
    with pytest.raises(CapReached):  # it counts towards the caps for every model then
        await spending.before_request(host, brief_id="b1", card=SONNET)


def test_subscription_cost_without_a_report_comes_from_the_card(spending, general):
    usd = spending.after_response(
        brief_id="b1",
        project_id=None,
        run_id="r1",
        role="lead",
        card=CLAUDE_CODE,
        input_tokens=20_000,
        output_tokens=1_500,
    )
    assert usd == Decimal("0.0825") and cost_rows(general)[0][-3:] == (
        "0.0825",
        1,
        SONNET.price_source,
    )


# The one list of checks every AI call passes ----------------------------------------------------


async def test_an_ai_call_check_can_refuse(spending, host, general, monkeypatch):
    refusal = {"en": "Not allowed by the sample check.", "ar": "الفحص التجريبي مش سامح."}
    seen: list[ModelChoice] = []

    def no_lab(choice: ModelChoice):
        seen.append(choice)
        return refusal

    monkeypatch.setattr(costs, "AI_CALL_CHECKS", [lambda choice: None, no_lab])
    model = scripted(text("مرحبا"))
    agent = Agent(costed(model, spending, host, LOCAL))
    with pytest.raises(CallRefused) as refused:
        await agent.run("سعّر بند الخرسانة - عينة")
    assert refused.value.text == refusal and seen == [LOCAL.choice]
    assert model.calls == 0 and cost_rows(general) == []  # even an on-device call is checked


# CostedModel ---------------------------------------------------------------------------------


def costed(model, spending, host, card, *, role="lead") -> CostedModel:
    return CostedModel(
        model,
        spending=spending,
        host=host,
        brief_id=host.brief_id,
        project_id="p1",
        run_id="r1",
        role=role,
        card=card,
    )


async def test_costed_model_records_each_response(general, host, fake_clock):
    spending = Spending(CostBook(general, local_tz=CAIRO), clock=fake_clock)
    card = cards.priced(replace(HAIKU, price_in=None, price_out=None, price_source=None))
    assert card.price_source.startswith("genai-prices 0.2.1: ")
    agent = Agent(costed(scripted(text("مرحبا", usage=(1200, 80))), spending, host, card))
    result = await agent.run("سعّر بند الخرسانة - عينة")
    assert result.output == "مرحبا"
    usd = cards.cost(card, input_tokens=1200, output_tokens=80)
    assert usd > 0
    assert cost_rows(general) == [
        (
            "b1",
            "p1",
            "r1",
            "lead",
            "anthropic",
            "claude-haiku-5-5",
            1200,
            80,
            str(usd),
            0,
            card.price_source,
        )
    ]
    with general.read() as c:
        [(at, local_day)] = c.execute("SELECT at, local_day FROM ai_costs").fetchall()
    assert at.startswith("2026-11-05T08:00:00") and local_day == "2026-11-05"


async def test_costed_model_records_a_streamed_response(general, spending, host):
    agent = Agent(costed(scripted(text("مرحبا", usage=(900, 40))), spending, host, SONNET))
    async with agent.run_stream("سعّر بند الخرسانة - عينة") as run:
        assert await run.get_output() == "مرحبا"
    [row] = cost_rows(general)
    assert row[6:9] == (900, 40, str((900 * 3 + 40 * 15) / Decimal(1_000_000)))


async def test_costed_model_keeps_the_wrapped_models_name(spending, host):
    model = costed(scripted(text("x"), model_name="sample-model"), spending, host, SONNET)
    assert model.model_name == "sample-model"


async def test_no_model_request_after_a_stop(general, book, spending, host):
    book_add(book, brief="b1", usd="3.00")
    model = scripted(text("مرحبا"), text("مرحبا"))
    agent = Agent(costed(model, spending, host, SONNET))
    with pytest.raises(CapReached):
        await agent.run("سعّر بند الخرسانة - عينة")
    with pytest.raises(CapReached):
        async with agent.run_stream("سعّر بند الخرسانة - عينة") as run:
            await run.get_output()
    assert model.calls == 0 and len(cost_rows(general)) == 1  # only the sample row


# The Brief Budget -------------------------------------------------------------------------------


ROLES = {
    "lead": OPUS.choice,
    "specialist": SONNET.choice,
    "checker": HAIKU.choice,
    "quick": HAIKU.choice,
}
PLAN = [{"tier": "lead", "requests": 4}, {"tier": "specialist", "requests": 10}]


def test_brief_budget_says_measured_or_assumed(book):
    assumed = brief_budget(PLAN, SAMPLE_SHEET, ROLES, None)
    # Each request: 20,000 in and 1,500 out. Opus 15/75, Sonnet 3/15 USD per million (sample).
    opus = Decimal(20_000 * 15 + 1_500 * 75) / 1_000_000
    sonnet = Decimal(20_000 * 3 + 1_500 * 15) / 1_000_000
    assert assumed == Budget(usd=4 * opus + 10 * sonnet, minutes=5, basis=copy.BASIS_ASSUMED)

    book_add(book, brief="b2", usd="0.01")  # 1,000 in and 100 out
    book_add(book, brief="b3", usd="0.01")
    measured = brief_budget(PLAN, SAMPLE_SHEET, ROLES, book.tokens_per_request("p1"))
    assert measured.basis == copy.fill(copy.BASIS_MEASURED, n=2)
    assert (
        measured.usd
        == 4 * Decimal(1000 * 15 + 100 * 75) / 1_000_000
        + 10 * Decimal(1000 * 3 + 100 * 15) / 1_000_000
    )
    assert brief_budget(PLAN, SAMPLE_SHEET, ROLES, book.tokens_per_request("p9")) == assumed


def test_brief_budget_of_an_unknown_price_is_unknown():
    roles = ROLES | {"specialist": UNKNOWN.choice}
    assert brief_budget(PLAN, [*SAMPLE_SHEET, UNKNOWN], roles, None).usd is None
    assert brief_budget(PLAN, SAMPLE_SHEET, roles, None).usd is None  # not on the sheet


def test_brief_budget_minutes_round_up():
    one = brief_budget([{"tier": "quick", "requests": 1}], SAMPLE_SHEET, ROLES, None)
    assert one.minutes == 1 and brief_budget([], SAMPLE_SHEET, ROLES, None) == Budget(
        Decimal(0), 0, copy.BASIS_ASSUMED
    )


# Routes ----------------------------------------------------------------------------------------


def test_caps_routes_take_exact_numbers_only(data_dir):
    client = TestClient(create_app(SECRET, data_dir=data_dir))
    recommended = {
        "brief": "3",
        "day": "15",
        "month": "150",
        "budget_above": "0.50",
        "subscription_stops": False,
    }
    r = client.get("/settings/ai/caps", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"caps": recommended, "recommended": recommended}

    r = client.put(
        "/settings/ai/caps", json={"brief": "2.50", "subscription_stops": True}, headers=AUTH
    )
    assert r.status_code == 200
    assert r.json()["caps"] == recommended | {"brief": "2.50", "subscription_stops": True}
    assert costs.caps().brief == Decimal("2.50")

    for body in ({"day": "1,000"}, {"day": 15}, {"day": 15.5}, {"day": "-1"}):
        r = client.put("/settings/ai/caps", json=body, headers=AUTH)
        assert r.status_code == 422 and r.json() == {"error": copy.NUMBER_NOT_EXACT, "field": "day"}
    assert client.put("/settings/ai/caps", json={"weekly": "9"}, headers=AUTH).status_code == 422
    r = client.put("/settings/ai/caps", json={"subscription_stops": "yes"}, headers=AUTH)
    assert r.status_code == 422
    assert costs.caps().day == Decimal("15")
    assert client.get("/settings/ai/caps").status_code == 401


def test_costs_route_gives_spent_and_equivalent_as_text(data_dir, monkeypatch):
    with TestClient(create_app(SECRET, data_dir=data_dir)) as client:
        engine = client.app.state.engine

        def second_connection(data_dir):
            raise AssertionError("GET /costs opened the Engineer Records file again")

        # the engine holds the file open: the route reads its cost book, never a second one
        monkeypatch.setattr(general, "open_engineer_records", second_connection)
        r = client.get("/costs", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["brief"] is None and r.json()["today"] == "0" and r.json()["month"] == "0"
        costs_of_b1 = add_sample_costs(engine.book)  # the computer's own day, as the route's
        r = client.get("/costs", params={"brief_id": "b1"}, headers=AUTH)
    assert r.json() == costs_of_b1


def add_sample_costs(book: CostBook) -> dict:
    now = datetime.now(UTC)
    book_add(book, brief="b1", usd="1.25", at=now)
    book_add(book, brief="b2", usd="0.50", at=now, project="p2")
    book_add(book, brief="b1", usd="0.75", at=now, equivalent=True)
    book_add(book, brief="b1", usd=None, at=now)
    return {  # what GET /costs?brief_id=b1 answers for them
        "brief": "1.25",
        "today": "1.75",
        "month": "1.75",
        "equivalent": {"brief": "0.75", "today": "0.75", "month": "0.75"},
        # every response's tokens, and the one whose price is unknown said, never a false 0
        "tokens": {
            "brief": {"input": 3000, "output": 300},
            "today": {"input": 4000, "output": 400},
            "month": {"input": 4000, "output": 400},
        },
        "unpriced": {"brief": 1, "today": 1, "month": 1},
        "caps": {
            "brief": "3",
            "day": "15",
            "month": "150",
            "budget_above": "0.50",
            "subscription_stops": False,
        },
    }


def test_costs_route_creates_no_engineer_records(data_dir):
    """Before the engine has opened the file (or when it could not), nothing is spent yet."""
    client = TestClient(create_app(SECRET, data_dir=data_dir))  # no lifespan: no engine start
    assert client.get("/costs", headers=AUTH).json()["today"] == "0"
    assert not (data_dir / "engineer").exists()


def test_a_gemini_model_named_with_its_models_prefix_has_its_price():
    """Audit B6: Google's OpenAI-compatible list names "models/gemini-3.1-flash-lite"; the price
    book knows "gemini-3.1-flash-lite", so the price was unknown and every message held."""
    gemini = replace(
        UNKNOWN,
        choice=ModelChoice("standard:google", "models/gemini-3.1-flash-lite"),
        name="Gemini 3.1 Flash Lite",
        provider="google",
    )
    card = cards.priced(gemini)
    assert card.price_in is not None and card.price_source.startswith("genai-prices")
    assert cards.cost(card, input_tokens=1_000_000, output_tokens=0) == card.price_in
