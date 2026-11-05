"""The message box's model and effort: the Lead QS of the Brief a message starts runs on the model
picked there, at the effort picked there (PydanticAI's unified `thinking` setting; Claude Code's
`--effort`), and the pick is remembered for the next message. Only the levels a model accepts are
offered; each effort's cost is measured apart, for the Brief Budget.

Scripted models behind fake connectors and the fake `claude`; no test calls a real AI. Synthetic
«عينة» data only."""

from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.profiles import ModelProfile

from qsone import copy, settings
from qsone.app import create_app
from qsone.engine import costs, roles
from qsone.engine.connectors import efforts_of
from qsone.engine.connectors.claude_code import effort_levels
from qsone.engine.costs import ASSUMED_TOKENS, brief_budget
from qsone.engine.routes import card_json
from qsone.engine.store import CostBook
from qsone.engine.types import EFFORTS, ModelChoice
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import HAIKU, OPUS, SAMPLE_SHEET, FakeSleep, scripted
from tests.engine_fakes import text as said
from tests.test_engine_runner import FakeLink

OPUS_E = replace(OPUS, efforts=EFFORTS, effort_default="high")  # takes an effort, as Claude's
SHEET = [OPUS_E, HAIKU]  # Haiku here takes none


@pytest.fixture(autouse=True)
def no_budget_card():
    costs.save_caps({"budget_above": "100"})


class Seen:
    """Each request's model and `thinking` setting."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def model(self, name: str):
        def step(messages, info):
            self.calls.append((name, info.model_request_parameters.thinking))
            return said("تم - عينة").parts[0].content

        model = scripted(*[step] * 4, model_name=name)
        model._profile = ModelProfile(supports_thinking=True)  # takes `thinking`, as Claude does
        return model


@pytest.fixture
def seen():
    return Seen()


@pytest.fixture
def client(data_dir, seen):
    claude = FakeLink("anthropic", "Claude", "anthropic", sheet=SHEET)
    claude.models = {c.choice.model: seen.model(c.choice.model) for c in SHEET}
    app = create_app(SECRET, connectors=lambda: [claude], sleep=FakeSleep())
    with TestClient(app) as client:
        yield client


def send(client, text: str, **extra):
    return client.post("/chat", json=ui_message(text) | {"id": "general"} | extra, headers=AUTH)


def test_settings_say_each_models_effort_levels_and_the_last_effort(client):
    assert card_json(OPUS_E)["efforts"] == ["low", "medium", "high"]
    assert card_json(OPUS_E)["effort_default"] == "high"
    assert card_json(HAIKU)["efforts"] == [] and card_json(HAIKU)["effort_default"] is None
    assert client.get("/settings/ai", headers=AUTH).json()["effort"] is None
    settings.save_ai("effort", "max")  # not a level the box offers
    assert client.get("/settings/ai", headers=AUTH).json()["effort"] is None


def test_without_a_pick_the_lead_runs_as_today(client, seen):
    assert send(client, "سؤال - عينة").status_code == 200
    assert seen.calls == [(OPUS.choice.model, None)]  # its role's model, its provider's effort
    assert settings.ai().get("effort") is None


def test_the_picked_model_and_effort_run_the_lead_and_are_remembered(client, seen):
    pick = {"connector": "anthropic", "model": OPUS.choice.model}
    assert send(client, "سؤال - عينة", model=pick, effort="low").status_code == 200
    assert seen.calls == [(OPUS.choice.model, "low")]
    assert roles.saved()["lead"] == OPUS.choice and settings.ai()["effort"] == "low"
    assert client.get("/settings/ai", headers=AUTH).json()["effort"] == "low"
    # each cost is kept with the effort it was sent with
    book = client.app.state.engine.book
    assert book.tokens_per_request(None, "low") is not None
    assert book.tokens_per_request(None) is None


def test_another_model_is_used_and_an_effort_it_does_not_take_is_dropped(client, seen):
    pick = {"connector": "anthropic", "model": HAIKU.choice.model}
    assert send(client, "سؤال - عينة", model=pick, effort="high").status_code == 200
    assert seen.calls == [(HAIKU.choice.model, None)]
    assert roles.saved()["lead"] == HAIKU.choice


def test_a_model_no_longer_there_says_so_and_starts_nothing(client, seen):
    pick = {"connector": "anthropic", "model": "claude-gone-sample"}
    r = send(client, "سؤال - عينة", model=pick)
    assert r.status_code == 200 and copy.CHAT_MODEL_GONE["en"] in r.text
    assert seen.calls == [] and "lead" not in roles.saved()


@pytest.mark.parametrize(
    "extra",
    [{"model": "claude"}, {"model": {"connector": "anthropic"}}, {"effort": "max"}, {"effort": 2}],
)
def test_a_pick_that_does_not_read_is_refused(client, seen, extra):
    r = send(client, "سؤال - عينة", **extra)
    assert r.status_code == 422 and r.json()["error"] == copy.CHAT_MODEL_GONE
    assert seen.calls == []


# Which levels a model takes ----------------------------------------------------------------------


def test_effort_levels_come_from_the_models_profile():
    from pydantic_ai.providers.anthropic import AnthropicProvider
    from pydantic_ai.providers.openai import OpenAIProvider

    assert efforts_of(AnthropicProvider.model_profile("claude-opus-5-5")) == (EFFORTS, "high")
    assert efforts_of(AnthropicProvider.model_profile("claude-3-haiku-20240307")) == ((), None)
    assert efforts_of(OpenAIProvider.model_profile("gpt-5.5")) == (EFFORTS, None)
    assert efforts_of(OpenAIProvider.model_profile("deepseek-chat")) == ((), None)


def test_claude_codes_levels_come_from_its_help():
    help_text = (
        "  --effort <level>   Effort level for the session (low, medium, high, xhigh, max)\n"
    )
    assert effort_levels(help_text) == EFFORTS
    assert effort_levels("  --model <model>  Model for the session\n") == ()


# The Brief Budget at the Lead's effort ----------------------------------------------------------


PLAN = [{"tier": "lead", "requests": 2}, {"tier": "specialist", "requests": 3}]
ROLES = {"lead": OPUS.choice, "specialist": HAIKU.choice}


def test_the_budget_prices_the_leads_requests_at_their_own_efforts_tokens():
    plain = (1000, 100, 4)
    at_high = (1000, 4000, 2)  # thinking hard writes more
    same = brief_budget(PLAN, SAMPLE_SHEET, ROLES, plain)
    assert brief_budget(PLAN, SAMPLE_SHEET, ROLES, plain, plain) == same
    high = brief_budget(PLAN, SAMPLE_SHEET, ROLES, plain, at_high)
    assert high.usd - same.usd == 2 * Decimal(3900) * OPUS.price_out / 1_000_000
    assert high.basis == copy.fill(copy.BASIS_MEASURED, n=6)
    unmeasured = brief_budget(PLAN, SAMPLE_SHEET, ROLES, plain, None)  # this effort never ran
    assert unmeasured.basis == copy.BASIS_ASSUMED
    assert unmeasured.usd > same.usd  # the Lead's lines at the assumed tokens
    assert ASSUMED_TOKENS[1] > plain[1]


def test_tokens_per_request_counts_one_effort_at_a_time(general, fake_clock):
    book = CostBook(general)

    def add(effort, tokens_out):
        book.add(
            brief_id="b1",
            project_id="p1",
            run_id="r1",
            role="lead",
            choice=ModelChoice("anthropic", OPUS.choice.model),
            input_tokens=100,
            output_tokens=tokens_out,
            usd=Decimal("0.01"),
            equivalent=False,
            basis="sample",
            at=fake_clock(),
            effort=effort,
        )

    add(None, 10)
    add("high", 300)
    add("high", 500)
    assert book.tokens_per_request("p1") == (100, 10, 1)
    assert book.tokens_per_request("p1", "high") == (100, 400, 2)
    assert book.tokens_per_request("p1", "low") is None
