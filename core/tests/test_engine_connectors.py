"""Plan 4 Task 3: AI Connectors, the Model Data Sheet and the model for each role.

Every provider here is a fake: an httpx2 MockTransport, or a small server on 127.0.0.1.
"""

import json
import logging
from decimal import Decimal

import anthropic
import httpx2
import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelAuthenticationError, ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel

from qsone import chat, copy, keys, settings
from qsone.app import create_app
from qsone.engine import cards, connectors, roles
from qsone.engine.connectors import standard
from qsone.engine.connectors.native_anthropic import NativeLink
from qsone.engine.connectors.standard import StandardLink
from qsone.engine.types import ModelCard, ModelChoice
from tests.conftest import AUTH, SECRET
from tests.engine_fakes import DEEPSEEK, HAIKU, OPUS, SAMPLE_SHEET, SONNET

CLAUDE_KEY = "sk-ant-api03-connector-test-key"
STANDARD_KEY = "sk-standard-connector-test-key"
DEEPSEEK_URL = "https://api.deepseek.com/v1"


def bare_card(connector: str, model: str, *, provider: str, on_device: bool = False) -> ModelCard:
    return ModelCard(
        choice=ModelChoice(connector, model),
        name=model,
        provider=provider,
        images=False,
        tools=True,
        context=None,
        price_in=None,
        price_out=None,
        price_source=None,
        on_device=on_device,
    )


def anthropic_info(model_id: str, name: str, *, images: bool = True) -> dict:
    """One model as Anthropic's models list sends it."""
    return {
        "type": "model",
        "id": model_id,
        "display_name": name,
        "created_at": "2026-09-01T00:00:00Z",
        "lifecycle": "active",
        "max_input_tokens": 1_000_000,
        "capabilities": {"image_input": {"supported": images}},
    }


ANTHROPIC_MODELS = [
    anthropic_info("claude-opus-5-5", "Claude Opus 5.5"),
    anthropic_info("claude-haiku-5-5", "Claude Haiku 5.5"),
]


def providers(
    seen: list[httpx2.Request] | None = None,
    *,
    anthropic_status: int = 200,
    standard_models: tuple[str, ...] = ("deepseek-chat", "deepseek-reasoner"),
) -> httpx2.AsyncClient:
    """Fake Anthropic and OpenAI-compatible model lists; nothing leaves this computer."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        if request.url.host == "api.anthropic.com" and request.url.path == "/v1/models":
            if anthropic_status != 200:
                body = {"type": "error", "error": {"type": "authentication_error", "message": "x"}}
                return httpx2.Response(
                    anthropic_status, json=body, headers={"x-should-retry": "false"}
                )
            return httpx2.Response(
                200,
                json={
                    "data": ANTHROPIC_MODELS,
                    "has_more": False,
                    "first_id": ANTHROPIC_MODELS[0]["id"],
                    "last_id": ANTHROPIC_MODELS[-1]["id"],
                },
            )
        if request.url.path.endswith("/models"):
            data = [{"id": m, "object": "model", "owned_by": "sample"} for m in standard_models]
            return httpx2.Response(200, json={"object": "list", "data": data})
        return httpx2.Response(404, json={"error": {"message": "not here"}})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def client_with(http: httpx2.AsyncClient) -> TestClient:
    return TestClient(create_app(SECRET, ai_http=http))


def choice_json(card: ModelCard) -> dict:
    return {"connector": card.choice.connector, "model": card.choice.model}


# Prices and their source -----------------------------------------------------------------------


def test_prices_come_from_genai_prices_with_their_source():
    card = cards.priced(bare_card("anthropic", "claude-haiku-5-5", provider="anthropic"))
    assert card.price_in > 0 and card.price_out > 0
    assert card.price_source.startswith("genai-prices ") and "http" in card.price_source

    opus = cards.priced(bare_card("anthropic", "claude-opus-5-5", provider="anthropic"))
    # genai-prices 0.2.1, pinned in requirements.lock: exact decimals, never floats.
    assert (opus.price_in, opus.price_out) == (Decimal("4"), Decimal("20"))
    assert opus.price_source == "genai-prices 0.2.1: https://www.anthropic.com/pricing#api"


def test_unknown_model_has_no_price():
    card = cards.priced(bare_card("standard:local", "my-model", provider="my-server.example"))
    assert card.price_in is None and card.price_out is None and card.price_source is None
    # A known model name behind an unknown provider is not guessed either.
    proxied = cards.priced(bare_card("standard:proxy", "gpt-4o", provider="proxy.example"))
    assert proxied.price_in is None and proxied.price_source is None
    assert cards.cost(card, input_tokens=1000, output_tokens=10) is None


def test_engineer_price_wins_with_who_and_when(fake_clock):
    entered = cards.enter_price(
        ModelChoice("anthropic", "claude-opus-5-5"), "1.25", "6.50", clock=fake_clock
    )
    assert entered == fake_clock().astimezone().date().isoformat()
    card = cards.priced(bare_card("anthropic", "claude-opus-5-5", provider="anthropic"))
    assert (card.price_in, card.price_out) == (Decimal("1.25"), Decimal("6.50"))
    assert card.price_source == f"engineer, {entered}"
    # Unknown prices too: the engineer's price is what lets the model run under a cap.
    cards.enter_price(ModelChoice("standard:local", "my-model"), "0", "0.4", clock=fake_clock)
    local = cards.priced(bare_card("standard:local", "my-model", provider="my-server.example"))
    assert (local.price_in, local.price_out) == (Decimal("0"), Decimal("0.4"))


def test_entered_prices_must_be_exact_decimals(fake_clock):
    for bad in ["1,25", "1.2e3", "-1", "", " 1", "١٫٥"]:
        with pytest.raises(cards.PriceNotExact):
            cards.enter_price(ModelChoice("anthropic", "x"), bad, "1", clock=fake_clock)


async def test_on_device_costs_nothing(serve_app):
    app = FastAPI()

    @app.get("/v1/models")
    def listed() -> dict:
        return {"object": "list", "data": [{"id": "qwen3:8b", "object": "model"}]}

    base_url = serve_app(app) + "/v1"
    link = StandardLink("local", "Ollama", base_url, standard.provider_of(base_url))
    assert link.on_device
    assert standard.on_device("http://127.0.0.1:11434/v1") and standard.on_device(
        "http://[::1]:1/v1"
    )
    assert standard.on_device("http://localhost:8080/v1")
    assert not standard.on_device(DEEPSEEK_URL)

    [card] = [cards.priced(c) for c in await link.cards()]
    assert card.on_device and card.choice == ModelChoice("standard:local", "qwen3:8b")
    assert (card.price_in, card.price_out) == (Decimal("0"), Decimal("0"))
    assert card.price_source == "on-device"
    assert cards.cost(card, input_tokens=50_000, output_tokens=2_000) == Decimal("0")


def test_cost_is_exact():
    # A sample card: (1M × 15 + 2M × 75) / 1M USD.
    assert cards.cost(OPUS, input_tokens=1_000_000, output_tokens=2_000_000) == Decimal("165")
    assert cards.cost(HAIKU, input_tokens=1, output_tokens=0) == Decimal("0.000001")
    # A genai-prices card is costed by genai-prices, cache reads and writes included
    # (input_tokens counts them, as PydanticAI does): 300×4 + 500×0.2 + 200×5 + 100×20 per M.
    opus = cards.priced(bare_card("anthropic", "claude-opus-5-5", provider="anthropic"))
    assert cards.cost(
        opus, input_tokens=1000, output_tokens=100, cache_read=500, cache_write=200
    ) == Decimal("0.0043")


# The model for each role ---------------------------------------------------------------------


def cheapest(sheet: list[ModelCard]) -> ModelCard:
    return min(sheet, key=lambda c: c.price_in + c.price_out)


def test_default_roles_spread_over_price_and_provider():
    sheet = SAMPLE_SHEET  # opus, sonnet, haiku (anthropic) + a sample deepseek card (standard)
    r = roles.defaults(sheet)
    assert r["lead"].model == "claude-opus-5-5" and r["checker"].connector.startswith("standard:")
    assert r["quick"] == cheapest(sheet).choice
    assert r["specialist"] == SONNET.choice


def test_checker_uses_another_model_with_one_provider():
    r = roles.defaults([HAIKU, OPUS, SONNET])
    assert r["lead"] == OPUS.choice and r["checker"] == SONNET.choice


def test_lead_without_opus_5_5_is_the_most_expensive():
    assert roles.defaults([HAIKU, DEEPSEEK, SONNET])["lead"] == SONNET.choice


def test_a_card_with_no_price_is_never_a_default():
    unpriced = bare_card("standard:big", "big-model", provider="big.example")
    on_device = cards.priced(
        bare_card("standard:local", "qwen3:8b", provider="127.0.0.1", on_device=True)
    )
    r = roles.defaults([unpriced, HAIKU, on_device])
    assert unpriced.choice not in r.values()
    assert r["lead"] == HAIKU.choice and r["quick"] == on_device.choice
    assert roles.defaults([unpriced]) == {}
    # One model only: the check runs on it too, rather than not at all.
    assert roles.defaults([HAIKU]) == {role: HAIKU.choice for role in roles.ROLES}


def test_engineer_choice_wins_over_defaults(data_dir):
    roles.choose("checker", HAIKU.choice)
    r = roles.chosen(SAMPLE_SHEET)
    assert r["checker"] == HAIKU.choice and r["lead"] == OPUS.choice
    saved = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["ai"]["roles"] == {
        "checker": {"connector": "anthropic", "model": "claude-haiku-5-5"}
    }


GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def google(model: str, connector: str = "standard:g") -> ModelCard:
    """A Google card as the Standard Link lists it, priced by the price book."""
    return cards.priced(bare_card(connector, f"models/{model}", provider="google"))


def test_a_refused_retired_or_latest_alias_model_is_never_a_default():
    """Finding 12: Google's list made "Gemini Pro Latest" (an alias, $2/$12) the Lead and the
    retired gemini-2.5-flash-lite the quick role."""
    alias, pro = google("gemini-pro-latest"), google("gemini-3.1-pro-preview")
    lite, gone = google("gemini-3.1-flash-lite"), google("gemini-2.5-flash-lite")
    old = google("gemini-2.0-flash-lite")  # the price book marks it deprecated
    assert old.retired and not lite.retired and alias.price_in == pro.price_in
    connectors.note_refused(gone.choice)  # Google's 404: "no longer available"
    r = roles.defaults([alias, pro, lite, gone, old])
    assert r["lead"] == pro.choice and r["quick"] == lite.choice
    assert not {alias.choice, gone.choice, old.choice} & set(r.values())


def test_a_saved_role_on_a_refused_model_falls_back_to_the_default():
    roles.choose("quick", HAIKU.choice)
    connectors.note_refused(HAIKU.choice)
    sheet = [OPUS, SONNET, DEEPSEEK]
    assert roles.chosen(sheet)["quick"] == roles.defaults(sheet)["quick"] == DEEPSEEK.choice


def test_the_model_typed_with_the_link_leads_and_nothing_costs_more(data_dir):
    """Finding 12: the engineer typed gemini-3.1-flash-lite; no role goes to a costlier model,
    and the Checking QS is never the model it checks (decisions: a same-provider check)."""
    link = standard.add("Google", GOOGLE_URL, STANDARD_KEY, model="gemini-3.1-flash-lite")
    saved = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["ai"]["standard"][0]["model"] == "gemini-3.1-flash-lite"
    pro, flash = google("gemini-3.1-pro-preview", link.id), google("gemini-2.5-flash", link.id)
    lite, older = google("gemini-3.1-flash-lite", link.id), google("gemini-2.5-flash-lite", link.id)
    sheet = [pro, flash, lite, older, HAIKU]
    r = roles.defaults(sheet)
    assert r["lead"] == r["specialist"] == lite.choice
    # quick: the cheapest of its provider; checking: another model, never costlier than typed
    assert r["quick"] == older.choice and r["checker"] == older.choice
    # another provider at or under the typed model's price checks it
    assert roles.defaults([*sheet, DEEPSEEK])["checker"] == DEEPSEEK.choice
    connectors.note_refused(lite.choice)
    assert roles.defaults(sheet)["lead"] == pro.choice  # a typed model refused: the usual ranking


def test_a_typed_model_with_no_price_still_leads():
    """The engineer named it: that is their choice, not ONE's, so its price may be unknown."""
    link = standard.add("Office", "https://ai.example.com/v1", STANDARD_KEY, model="big-model")
    big = bare_card(link.id, "big-model", provider="ai.example.com")
    r = roles.defaults([big, HAIKU])
    assert r["lead"] == r["specialist"] == r["quick"] == big.choice


def test_fallbacks_same_or_cheaper_first_and_never_the_maker():
    assert roles.same_or_cheaper(SAMPLE_SHEET, OPUS.choice, avoid={OPUS.choice})[0] == SONNET.choice
    assert OPUS.choice not in roles.same_or_cheaper(
        SAMPLE_SHEET, SONNET.choice, avoid={OPUS.choice}
    )
    assert roles.same_or_cheaper(SAMPLE_SHEET, SONNET.choice, avoid=set()) == [
        HAIKU.choice,
        DEEPSEEK.choice,
    ]
    assert roles.costlier(SAMPLE_SHEET, HAIKU.choice, avoid=set()) == [SONNET.choice, OPUS.choice]
    assert roles.costlier(SAMPLE_SHEET, SONNET.choice, avoid={OPUS.choice}) == []
    unpriced = bare_card("standard:big", "big-model", provider="big.example")
    sheet = [*SAMPLE_SHEET, unpriced]
    assert unpriced.choice not in roles.same_or_cheaper(sheet, OPUS.choice, avoid=set())
    assert unpriced.choice not in roles.costlier(sheet, DEEPSEEK.choice, avoid=set())


def test_old_lead_model_setting_moves_into_roles(data_dir):
    data_dir.mkdir(parents=True)
    (data_dir / "settings.json").write_text(
        json.dumps({"lead_model": "claude-fable-5-1", "other": 1}), encoding="utf-8"
    )
    assert roles.saved() == {"lead": ModelChoice("anthropic", "claude-fable-5-1")}
    saved = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
    assert "lead_model" not in saved and saved["other"] == 1
    assert saved["ai"]["roles"]["lead"] == {"connector": "anthropic", "model": "claude-fable-5-1"}
    assert chat.lead_model_id() == "claude-fable-5-1"


# The Native Link -----------------------------------------------------------------------------


async def test_native_link_lists_models_with_their_capabilities():
    seen: list[httpx2.Request] = []
    link = NativeLink(http_client=providers(seen))
    assert await link.cards() == []  # no key: nothing listed, nothing asked
    assert seen == []

    keys.set_key("anthropic", CLAUDE_KEY)
    opus, haiku = await link.cards()
    assert opus.choice == ModelChoice("anthropic", "claude-opus-5-5")
    assert opus.name == "Claude Opus 5.5" and opus.provider == "anthropic"
    assert opus.images and opus.tools and opus.context == 1_000_000
    assert not opus.on_device and not opus.subscription
    assert opus.price_in is None  # the sheet prices it
    assert CLAUDE_KEY in " ".join(seen[0].headers.values())


def test_native_link_builds_a_cached_anthropic_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-the-environment")
    link = NativeLink()
    with pytest.raises(connectors.NoKey):
        link.model("claude-opus-5-5")  # never the environment's key

    keys.set_key("anthropic", CLAUDE_KEY)
    model = link.model("claude-opus-5-5")
    assert isinstance(model, AnthropicModel) and model.model_name == "claude-opus-5-5"
    assert model.client.api_key == CLAUDE_KEY
    assert model.settings["anthropic_cache_instructions"] is True
    assert model.settings["anthropic_cache_tool_definitions"] is True
    assert model.settings["anthropic_cache"] is True  # the conversation so far, each request


# The Standard Link ---------------------------------------------------------------------------


def test_standard_link_builds_an_openai_compatible_model(memory_keyring):
    link = standard.add("DeepSeek", DEEPSEEK_URL, STANDARD_KEY)
    assert link.id.startswith("standard:") and link.provider == "deepseek"
    assert memory_keyring.store[(keys.SERVICE, link.id)] == STANDARD_KEY
    model = link.model("deepseek-chat")
    assert isinstance(model, OpenAIChatModel) and model.model_name == "deepseek-chat"
    assert str(model.client.base_url).rstrip("/") == DEEPSEEK_URL
    assert model.client.api_key == STANDARD_KEY

    local = standard.add("llama.cpp", "http://127.0.0.1:8080/v1", None)
    assert local.on_device and local.model("any").client.api_key == "none"
    assert [c.id for c in connectors.connectors()] == ["anthropic", link.id, local.id]


async def test_standard_link_lists_models_from_its_server():
    seen: list[httpx2.Request] = []
    link = StandardLink("ds", "DeepSeek", DEEPSEEK_URL, "deepseek", http_client=providers(seen))
    keys.set_key(link.id, STANDARD_KEY)
    found = await link.cards()
    assert [c.choice for c in found] == [
        ModelChoice("standard:ds", "deepseek-chat"),
        ModelChoice("standard:ds", "deepseek-reasoner"),
    ]
    assert seen[0].url == "https://api.deepseek.com/v1/models"
    assert seen[0].headers["authorization"] == f"Bearer {STANDARD_KEY}"
    card = cards.priced(found[0])
    assert card.provider == "deepseek" and card.price_in is not None
    assert card.price_source.startswith("genai-prices 0.2.1: https://")


# Part of what Google's OpenAI-compatible list gave on 5 Nov 2026 (audit C4): 60 models, most of
# them not for a chat that uses tools.
GOOGLE_MODELS = [
    ("models/gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
    ("models/gemini-3.5-pro", "Gemini 3.5 Pro"),
    ("models/gemini-2.5-flash-preview-tts", "Gemini 2.5 Flash Preview TTS"),
    ("models/gemini-2.5-flash-image", "Nano Banana"),
    ("models/gemini-embedding-001", "Gemini Embedding 001"),
    ("models/imagen-4.0-generate-001", "Imagen 4"),
    ("models/veo-3.0-generate-001", "Veo 3"),
    ("models/lyria-realtime-exp", "Lyria Realtime"),
    ("models/gemini-robotics-er-1.5-preview", "Gemini Robotics-ER 1.5 Preview"),
    ("models/gemini-2.5-flash-native-audio-latest", "Gemini 2.5 Flash Native Audio"),
    ("models/gemini-2.5-computer-use-preview-10-2025", "Gemini 2.5 Computer Use Preview"),
    ("models/aqa", "Model that performs Attributed Question-Answering."),
    ("models/gemma-3-27b-it", None),
]


def google_list() -> httpx2.AsyncClient:
    def handle(request: httpx2.Request) -> httpx2.Response:
        data = [
            {"id": m, "object": "model", "owned_by": "google"} | ({"display_name": n} if n else {})
            for m, n in GOOGLE_MODELS
        ]
        return httpx2.Response(200, json={"object": "list", "data": data})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


async def test_only_chat_models_are_listed_by_their_names():
    link = StandardLink(
        "g",
        "Google",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "google",
        http_client=google_list(),
    )
    keys.set_key(link.id, STANDARD_KEY)
    found = await link.cards()
    assert [(c.choice.model, c.name) for c in found] == [
        ("models/gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"),
        ("models/gemini-3.5-pro", "Gemini 3.5 Pro"),
        ("models/gemma-3-27b-it", "gemma-3-27b-it"),  # no name given: its id, without models/
    ]


async def test_a_model_the_provider_refused_is_no_longer_listed():
    link = StandardLink(
        "g",
        "Google",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "google",
        http_client=google_list(),
    )
    keys.set_key(link.id, STANDARD_KEY)
    connectors.note_refused(ModelChoice("standard:g", "models/gemini-3.5-pro"))
    found = await link.cards()
    assert "models/gemini-3.5-pro" not in [c.choice.model for c in found]


def test_a_key_over_plain_http_to_another_computer_is_refused():
    with pytest.raises(standard.KeyInTheClear):
        standard.add("Office server", "http://192.168.1.10:8080/v1", STANDARD_KEY)
    assert standard.add("Office server", "http://192.168.1.10:8080/v1", None).provider


def test_an_unknown_provider_is_its_host_and_port():
    # the port tells local servers apart (Ollama 11434, LM Studio 1234): the UI's logo and a
    # Same-provider check both read it; a name and password before the host never show
    assert standard.provider_of("http://localhost:11434/v1") == "localhost:11434"
    assert standard.provider_of("http://127.0.0.1:1234/v1") == "127.0.0.1:1234"
    assert standard.provider_of("http://[::1]:11434/v1") == "[::1]:11434"
    assert standard.provider_of("https://me:pw@Example.com/v1") == "example.com"
    assert standard.provider_of("https://dashscope.aliyuncs.com/compatible-mode/v1") == (
        "dashscope.aliyuncs.com"
    )
    assert standard.provider_of("https://openrouter.ai/api/v1") == "openrouter"


def test_a_saved_link_reads_its_provider_from_its_address(data_dir):
    # a link saved before the port counted (provider "localhost") shows as the server it is
    entry = {"id": "old", "name": "Ollama", "base_url": "http://localhost:11434/v1"}
    settings.save_ai("standard", [entry | {"provider": "localhost"}])
    [link] = standard.links()
    assert link.provider == "localhost:11434"


# The settings routes -------------------------------------------------------------------------


def test_settings_routes(data_dir):
    keys.set_key("anthropic", CLAUDE_KEY)
    client = client_with(providers())

    r = client.get("/settings/ai", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["connectors"] == [
        {
            "id": "anthropic",
            "kind": "model",
            "name": "Claude",
            "provider": "anthropic",
            "on_device": False,
            "key_set": True,
            "error": None,
        }
    ]
    opus = next(c for c in body["sheet"] if c["model"] == "claude-opus-5-5")
    assert (
        opus["connector"] == "anthropic" and opus["price_in"] == "4" and opus["price_out"] == "20"
    )
    assert opus["price_source"].startswith("genai-prices 0.2.1: ")
    assert body["defaults"]["lead"] == {"connector": "anthropic", "model": "claude-opus-5-5"}
    assert body["roles"] == body["defaults"]
    # One provider: the checker is another model, the cheaper one here.
    assert body["roles"]["checker"]["model"] == "claude-haiku-5-5"

    r = client.post(
        "/settings/ai/standard",
        json={"name": "DeepSeek", "base_url": DEEPSEEK_URL, "key": STANDARD_KEY},
        headers=AUTH,
    )
    assert r.status_code == 201
    added = r.json()
    assert added["name"] == "DeepSeek" and added["provider"] == "deepseek"
    assert added["kind"] == "model" and added["key_set"] and not added["on_device"]

    body = client.get("/settings/ai", headers=AUTH).json()
    assert [c["id"] for c in body["connectors"]] == ["anthropic", added["id"]]
    ds = {"connector": added["id"], "model": "deepseek-chat"}
    assert ds in [{"connector": c["connector"], "model": c["model"]} for c in body["sheet"]]
    assert body["defaults"]["checker"]["connector"] == added["id"]  # another provider now

    r = client.put("/settings/ai/roles", json={"specialist": ds}, headers=AUTH)
    assert r.status_code == 200 and r.json()["specialist"] == ds
    assert r.json()["lead"] == body["defaults"]["lead"]

    r = client.put(
        "/settings/ai/roles",
        json={"quick": {"connector": "anthropic", "model": "claude-not-listed"}},
        headers=AUTH,
    )
    assert r.status_code == 422
    assert r.json()["role"] == "quick" and ds in r.json()["allowed"]
    assert client.put("/settings/ai/roles", json={"boss": ds}, headers=AUTH).status_code == 422

    price = {"connector": added["id"], "model": "deepseek-reasoner", "in": "0.55", "out": "2.19"}
    r = client.put("/settings/ai/prices", json=price, headers=AUTH)
    assert r.status_code == 200
    card = r.json()
    assert card["model"] == "deepseek-reasoner" and card["price_in"] == "0.55"
    assert card["price_out"] == "2.19" and card["price_source"].startswith("engineer, ")

    r = client.put("/settings/ai/prices", json=price | {"in": "0,55"}, headers=AUTH)
    assert r.status_code == 422
    assert r.json() == {"error": copy.NUMBER_NOT_EXACT, "field": "in"}
    r = client.put("/settings/ai/prices", json=price | {"model": "not-listed"}, headers=AUTH)
    assert r.status_code == 404

    removed = client.delete(f"/settings/ai/standard/{added['id']}", headers=AUTH)
    assert removed.status_code == 200  # with its Undo; the key goes when the window ends
    client.app.state.trash.purge_all()
    assert keys.get_key(added["id"]) is None
    body = client.get("/settings/ai", headers=AUTH).json()
    assert [c["id"] for c in body["connectors"]] == ["anthropic"]
    assert body["roles"]["specialist"]["connector"] == "anthropic"  # its role choice went too
    assert added["id"] not in json.dumps(settings.ai())
    assert client.delete(f"/settings/ai/standard/{added['id']}", headers=AUTH).status_code == 404


def test_a_failed_list_is_plain_and_the_rest_still_shows():
    keys.set_key("anthropic", CLAUDE_KEY)
    client = client_with(providers(anthropic_status=401))
    client.post(
        "/settings/ai/standard", json={"name": "DeepSeek", "base_url": DEEPSEEK_URL}, headers=AUTH
    )
    body = client.get("/settings/ai", headers=AUTH).json()
    claude, ds = body["connectors"]
    assert claude["error"] == copy.KEY_REFUSED  # the Claude key: Anthropic's own words
    assert ds["error"] is None and not ds["key_set"]
    assert {c["connector"] for c in body["sheet"]} == {ds["id"]}


def test_the_model_typed_when_adding_a_link_is_the_leads_default():
    client = client_with(providers())
    link = {"name": "DeepSeek", "base_url": DEEPSEEK_URL, "model": "deepseek-reasoner"}
    added = client.post("/settings/ai/standard", json=link, headers=AUTH).json()
    body = client.get("/settings/ai", headers=AUTH).json()
    assert body["defaults"]["lead"] == {"connector": added["id"], "model": "deepseek-reasoner"}


def test_ai_settings_need_the_secret():
    client = client_with(providers())
    assert client.get("/settings/ai").status_code == 401
    assert client.put("/settings/ai/roles", json={}).status_code == 401
    assert client.post("/settings/ai/standard", json={}).status_code == 401
    assert client.delete("/settings/ai/standard/x").status_code == 401
    assert client.put("/settings/ai/prices", json={}).status_code == 401


def test_keys_never_in_settings_json_or_answers(data_dir, caplog):
    caplog.set_level(logging.DEBUG)
    keys.set_key("anthropic", CLAUDE_KEY)
    client = client_with(providers())
    answers = [
        client.post(
            "/settings/ai/standard",
            json={"name": "DeepSeek", "base_url": DEEPSEEK_URL, "key": STANDARD_KEY},
            headers=AUTH,
        ),
        client.post(
            "/settings/ai/standard",
            json={"name": "Office", "base_url": "http://192.168.1.10/v1", "key": STANDARD_KEY},
            headers=AUTH,
        ),
        client.get("/settings/ai", headers=AUTH),
    ]
    assert answers[0].status_code == 201 and answers[1].status_code == 422
    saved = (data_dir / "settings.json").read_text(encoding="utf-8")
    for key in (CLAUDE_KEY, STANDARD_KEY):
        assert key not in saved and key not in caplog.text
        assert all(key not in a.text for a in answers)


def test_plan_1_model_route_sets_the_lead():
    client = client_with(providers())
    r = client.put("/settings/model", json={"id": "claude-fable-5-1"}, headers=AUTH)
    assert r.status_code == 200 and r.json() == {"id": "claude-fable-5-1"}
    assert roles.saved()["lead"] == ModelChoice("anthropic", "claude-fable-5-1")
    assert client.get("/settings/model", headers=AUTH).json() == {"id": "claude-fable-5-1"}

    keys.set_key("anthropic", CLAUDE_KEY)
    lead = {"connector": "anthropic", "model": "claude-haiku-5-5"}
    assert client.put("/settings/ai/roles", json={"lead": lead}, headers=AUTH).status_code == 200
    assert client.get("/settings/model", headers=AUTH).json() == {"id": "claude-haiku-5-5"}


# The check (Plan 8) --------------------------------------------------------------------------


class StubConnector:
    """A model connector whose model is a PydanticAI `FunctionModel`."""

    kind = "model"
    provider = "sample"
    on_device = False

    def __init__(self, model) -> None:
        self.id = "standard:stub"
        self.name = "Stub AI"
        self._model = model

    async def cards(self) -> list[ModelCard]:
        return []

    def model(self, model_id: str):
        return self._model


async def test_check_says_ok_or_why_in_plain_words():
    asked: list[AgentInfo] = []

    def reply(messages, info: AgentInfo) -> ModelResponse:
        asked.append(info)
        return ModelResponse(parts=[TextPart("OK")])

    ok = StubConnector(FunctionModel(reply))
    assert await connectors.check("standard:stub/any-model", among=[ok]) is None
    assert asked[0].model_settings["max_tokens"] == 1

    keys.set_key("anthropic", CLAUDE_KEY)
    refused = NativeLink(http_client=providers_refusing_messages())
    said = await connectors.check("anthropic/claude-haiku-5-5", among=[refused])
    assert said == copy.KEY_REFUSED  # the Claude key: Anthropic's own words
    assert await connectors.check("standard:gone/x", among=[ok]) == copy.NO_AI

    def broken(messages, info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(400, "any-model")

    # a check has no work to save: never AI_FAILED's "the work so far is saved"
    failing = StubConnector(FunctionModel(broken))
    assert await connectors.check("standard:stub/any-model", among=[failing]) == copy.fill(
        copy.AI_CHECK_FAILED, provider=failing.name
    )


def providers_refusing_messages() -> httpx2.AsyncClient:
    def handle(request: httpx2.Request) -> httpx2.Response:
        body = {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}}
        return httpx2.Response(401, json=body, headers={"x-should-retry": "false"})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def _status(cls, status: int):
    request = httpx2.Request("GET", "https://api.example.com/v1/models")
    return cls("x", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize(
    "error, plain",
    [
        (ModelAuthenticationError("m", "bad key"), copy.AI_KEY_REFUSED),
        (ModelHTTPError(529, "m"), copy.AI_BUSY),
        (ModelHTTPError(400, "m"), copy.AI_FAILED),
        (_status(anthropic.AuthenticationError, 401), copy.AI_KEY_REFUSED),
        (_status(openai.AuthenticationError, 401), copy.AI_KEY_REFUSED),
        (_status(openai.RateLimitError, 429), copy.AI_BUSY),
        (_status(openai.InternalServerError, 503), copy.AI_BUSY),
        (
            openai.APIConnectionError(request=httpx2.Request("GET", "https://x.example")),
            copy.AI_NO_CONNECTION,
        ),
        (
            anthropic.APITimeoutError(request=httpx2.Request("GET", "https://x.example")),
            copy.AI_NO_CONNECTION,
        ),
    ],
)
def test_provider_errors_are_plain_words(error, plain):
    assert connectors.plain_error(error, "DeepSeek") == copy.fill(plain, provider="DeepSeek")


def test_a_refused_claude_key_says_where_to_make_one():
    refused = _status(anthropic.AuthenticationError, 401)
    assert connectors.plain_error(refused, NativeLink.name) == copy.KEY_REFUSED
    assert "console.anthropic.com" in copy.KEY_REFUSED["en"] + copy.KEY_REFUSED["ar"]
