"""Settings in one home (Phase 1, C10): every setting has its recommended value and its words,
the screen's PATCH checks a value and saves it at once, the Lead's `settings_set` changes the same
stored value and asks first before a change that spends more, sends more out or weakens a
Confidential rule, and a cap that is reached offers Settings, Spending caps.

Scripted fakes only: no AI model, no network. Synthetic «عينة» data only."""

import asyncio
import json
import locale

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import ModelRetry

from qsone import activity, copy, settings, settings_registry
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine import costs
from qsone.engine.tools import Denied, call
from tests.conftest import AUTH, SECRET
from tests.fakes_tools import fake_services, tool_ctx

# The contract's key table, in the registry's order (section 1, rows 21-22).
KEYS = [
    "ai.models",
    "ai.confidential_on_device",
    "caps.brief_usd",
    "caps.day_usd",
    "caps.month_usd",
    "caps.budget_above_usd",
    "caps.map_auto_usd",
    "caps.subscription_stops",
    "privacy.usage_stats",
    "look.language",
    "look.theme",
    "look.zoom",
]


@pytest.fixture
def client():
    return TestClient(create_app(SECRET))


def listed(client) -> dict[str, dict]:
    answer = client.get("/settings", headers=AUTH)
    assert answer.status_code == 200 and answer.headers["cache-control"] == "no-store"
    c.Settings.model_validate_json(answer.text, strict=True)
    return {s["key"]: s for s in answer.json()["settings"]}


def test_every_setting_has_recommended_and_texts(client, monkeypatch):
    monkeypatch.setattr(locale, "getlocale", lambda *_: ("ar_EG", "UTF-8"))  # an Arabic system
    found = listed(client)
    assert list(found) == KEYS
    for key, setting in found.items():
        assert setting["section"] == key.partition(".")[0]
        for words in (setting["title"], setting["help"]):
            assert words["en"].strip() and words["ar"].strip(), key
        for choice in setting.get("choices", ()):
            assert choice["title"]["en"].strip() and choice["title"]["ar"].strip(), key
        assert setting["at_recommended"] is True, key  # nothing chosen yet
    recommended = {key: s["recommended"] for key, s in found.items()}
    assert recommended == {
        "ai.models": "recommended",
        "ai.confidential_on_device": False,  # Q5
        "caps.brief_usd": "3",
        "caps.day_usd": "15",
        "caps.month_usd": "150",
        "caps.budget_above_usd": "0.50",
        "caps.map_auto_usd": "0.50",
        "caps.subscription_stops": False,
        "privacy.usage_stats": False,  # Q5: off until turned on
        "look.language": "ar",  # the system's
        "look.theme": "system",  # Q5
        "look.zoom": "1.0",
    }
    zoom = found["look.zoom"]
    assert (zoom["min"], zoom["max"], zoom["step"]) == ("0.8", "1.5", "0.1")
    assert {s["currency"] for s in found.values() if s["control"] == "money"} == {"USD"}


def test_patch_validates_and_saves_at_once(client):
    def patch(key: str, value):
        return client.patch(f"/settings/{key}", json={"value": value}, headers=AUTH)

    not_exact = patch("caps.month_usd", "abc")
    assert not_exact.status_code == 422
    assert not_exact.json() == {
        "error": copy.NUMBER_NOT_EXACT,
        "field": "value",
        "example": "150",
    }
    for key, value in (
        ("look.theme", "purple"),
        ("look.zoom", "1.55"),
        ("look.zoom", "2.0"),
        ("ai.confidential_on_device", "yes"),
        ("caps.month_usd", True),
    ):
        bad = patch(key, value)
        assert bad.status_code == 422, (key, value)
        refused = c.Refusal.model_validate_json(bad.text, strict=True)
        assert refused.field == "value" and refused.example, (key, value)
    unknown = patch("caps.monthly_usd", "50")
    assert unknown.status_code == 404 and unknown.json()["error"] == copy.SETTING_NOT_FOUND
    assert settings.load() == {}  # nothing refused was stored

    saved = patch("caps.month_usd", "50")
    assert saved.status_code == 200 and saved.headers["cache-control"] == "no-store"
    assert saved.json() | {"title": None, "help": None} == {
        "key": "caps.month_usd",
        "section": "caps",
        "title": None,
        "help": None,
        "at_recommended": False,
        "control": "money",
        "value": "50",
        "recommended": "150",
        "currency": "USD",
    }
    assert settings.ai()["caps"]["month"] == "50"  # in settings.json at once
    assert costs.caps().month == 50  # and what the Spending Caps read

    zoom = patch("look.zoom", "1.1")
    assert zoom.json()["value"] == "1.1" and settings.load()["zoom"] == 1.1
    assert client.get("/settings/zoom", headers=AUTH).json() == {"zoom": 1.1}  # the old route
    assert patch("look.theme", "dark").json()["value"] == "dark"
    assert patch("privacy.usage_stats", True).json()["value"] is True
    assert settings.load()["usage_stats"] is True
    put_back = patch("caps.month_usd", "150")
    assert put_back.json()["at_recommended"] is True


def test_a_setting_that_cannot_be_saved_says_so(client, monkeypatch):
    def full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(settings, "_write", full)
    answer = client.patch("/settings/look.theme", json={"value": "dark"}, headers=AUTH)
    assert answer.status_code == 503
    assert answer.json() == {"error": copy.SETTINGS_NOT_SAVED, "fix": "retry"}


async def test_a_change_tells_the_screens():
    events = activity.subscribe(settings_registry.CHANNEL)
    waiting = asyncio.ensure_future(anext(events))
    await asyncio.sleep(0)
    settings_registry.change("look.theme", "light")
    event = await asyncio.wait_for(waiting, 1)
    await events.aclose()
    parsed = c.SettingEvent.model_validate(event)
    assert parsed.setting.key == "look.theme" and parsed.setting.value == "light"


def test_models_back_to_recommended_lets_one_pick_each_role_again():
    settings.save_ai("roles", {"quick": {"connector": "anthropic", "model": "sample-model"}})
    assert settings_registry.shown(settings_registry.entry("ai.models")).value == "own"
    settings_registry.change("ai.models", "recommended")
    assert settings.ai()["roles"] == {}
    assert settings_registry.shown(settings_registry.entry("ai.models")).value == "recommended"


# The Lead's settings_set ------------------------------------------------------------------------


async def test_lead_changes_same_value(rec, client):
    lowered = tool_ctx(rec)  # a cap downward spends less: made at once
    said = json.loads(await call("settings_set", {"key": "caps.month_usd", "value": "50"}, lowered))
    assert said == {"key": "caps.month_usd", "value": "50"}
    assert lowered.host.cards == []
    assert listed(client)["caps.month_usd"]["value"] == "50"  # what the screen reads

    raised = tool_ctx(rec, answers={"setting": "yes"})
    await call("settings_set", {"key": "caps.month_usd", "value": "200"}, raised)
    [card] = raised.host.cards
    assert (card.kind, card.title, card.options) == ("setting", copy.SET_CAP_MONTH, ("yes", "no"))
    assert "50 USD" in card.detail["en"] and "200 USD" in card.detail["en"]
    assert "50 دولار" in card.detail["ar"] and "200 دولار" in card.detail["ar"]
    assert settings.ai()["caps"]["month"] == "200"

    refused = tool_ctx(rec, answers={"setting": "no"})
    with pytest.raises(Denied):
        await call("settings_set", {"key": "caps.month_usd", "value": "900"}, refused)
    assert (
        client.patch("/settings/caps.month_usd", json={"value": "75"}, headers=AUTH).json()["value"]
        == "75"
    )  # the screen changes it without asking
    assert settings.ai()["caps"]["month"] == "75"

    with pytest.raises(ModelRetry, match="ONE has no setting"):
        await call("settings_set", {"key": "caps.monthly_usd", "value": "50"}, tool_ctx(rec))
    with pytest.raises(ModelRetry, match="Send the number as text"):
        await call("settings_set", {"key": "caps.day_usd", "value": "lots"}, tool_ctx(rec))


@pytest.mark.parametrize(
    ("key", "before", "after", "asks"),
    [
        ("caps.brief_usd", "3", "4", True),
        ("caps.day_usd", "15", "10", False),
        ("caps.budget_above_usd", "0.50", "1", True),
        ("caps.map_auto_usd", "0.50", "0.25", False),
        ("caps.subscription_stops", True, False, True),
        ("caps.subscription_stops", False, True, False),
        ("ai.confidential_on_device", True, False, True),
        ("ai.confidential_on_device", False, True, False),
        ("privacy.usage_stats", False, True, True),
        ("privacy.usage_stats", True, False, False),
        ("ai.models", "recommended", "own", True),
        ("ai.models", "own", "recommended", True),
        ("look.language", "ar", "en", False),
        ("look.zoom", "1.0", "1.5", False),
        ("caps.month_usd", "150", "150.00", False),  # the same amount
    ],
)
def test_what_the_lead_asks_first(key, before, after, asks):
    entry = settings_registry.entry(key)
    assert settings_registry.asks_first(entry, before, after) is asks


async def test_a_toggle_the_lead_writes_as_text(rec):
    ctx = tool_ctx(rec, answers={"setting": "yes"})
    await call("settings_set", {"key": "privacy.usage_stats", "value": "true"}, ctx)
    assert settings.load()["usage_stats"] is True and len(ctx.host.cards) == 1


def test_the_lead_has_the_tool_in_a_tender_and_on_home():
    from qsone.engine import agents, general

    assert "settings_set" in agents.lead_spec().tools
    assert "settings_set" in general.lead_spec().tools


# The rest -------------------------------------------------------------------------------------


def test_a_cap_that_is_reached_offers_the_spending_caps():
    stopped = copy.fill(copy.CAP_STOPPED, scope_name=copy.SCOPE_MONTH, spent="150", cap="150")
    tokens = copy.fill(copy.CAP_TOKENS_STOPPED, scope_name=copy.SCOPE_DAY, spent="9", cap="9")
    for text in (stopped, tokens):
        assert copy.error(text) == {"error": text, "fix": "caps"}
    paused = copy.fill(copy.CAP_PAUSED, scope_name=copy.SCOPE_DAY, spent="12", cap="15")
    assert copy.fix_of(paused) is None  # its card has its own Raise


def test_a_confidential_project_stays_on_this_computer_while_the_setting_is_on(rec):
    services = fake_services()
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "1")
    assert services.on_device(rec) is False
    settings_registry.change("ai.confidential_on_device", True)
    assert services.on_device(rec) is True
    with rec.write("engineer") as conn:
        rec.set_meta(conn, "confidential", "0")
    assert services.on_device(rec) is False
