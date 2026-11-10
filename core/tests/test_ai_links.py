"""Connect an AI provider by pasting its key, and disconnect it (Phase 1, C10; contract routes 23
and 24). The provider is read from the key's form only, a key goes only to its provider's fixed
address, and a key is never echoed nor kept outside the key store.

Every provider is a fake (an httpx2 MockTransport); no key here is real. Synthetic «عينة» data."""

from types import SimpleNamespace

import httpx2
import pytest
from fastapi.testclient import TestClient

from qsone import ai_links, copy, keys, settings
from qsone import phase1_contract as c
from qsone.app import create_app
from qsone.engine.types import ModelChoice
from tests.conftest import AUTH, SECRET
from tests.test_engine_connectors import providers

CLAUDE = "sk-ant-api03-" + "s" * 90  # the forms of real keys, made of sample letters
OPENAI = "sk-proj-" + "o" * 60
GEMINI = "AIza" + "g" * 35


@pytest.fixture
def seen() -> list[httpx2.Request]:
    return []


@pytest.fixture
def client(seen):  # the AI consent is given (tests/conftest.py)
    return TestClient(create_app(SECRET, ai_http=providers(seen)))


def connect(client, key: str):
    return client.post("/settings/ai/connect", json={"key": key}, headers=AUTH)


def never_echoed(answer, key: str) -> None:
    assert key not in answer.text and key[8:40] not in answer.text


def test_each_form_names_one_provider():
    assert ai_links.recognise(CLAUDE).name == "Claude"
    assert ai_links.recognise(OPENAI).name == "OpenAI"
    assert ai_links.recognise(GEMINI).name == "Gemini"
    assert ai_links.recognise("sk-or-v1-" + "a" * 64).name == "OpenRouter"
    assert ai_links.recognise("gsk_" + "q" * 52).name == "Groq"
    # OpenAI's older form is also DeepSeek's and others': never guessed
    for key in ("sk-" + "d" * 32, "x", CLAUDE + "s" * 300, "AIza" + "g" * 36, "مفتاح - عينة"):
        assert ai_links.recognise(key) is None, key


def test_a_key_one_does_not_recognise_is_sent_to_no_one(client, seen):
    for key in ("sk-" + "d" * 32, "sample-key-" + "k" * 30, "x"):
        answer = connect(client, key)
        assert answer.status_code == 422 and answer.headers["cache-control"] == "no-store"
        assert answer.json() == {"error": copy.KEY_NOT_RECOGNISED, "field": "key"}  # no echo
    assert seen == []


def test_the_consent_comes_first(seen, no_consent):
    client = TestClient(create_app(SECRET, ai_http=providers(seen)))
    answer = connect(client, CLAUDE)
    assert answer.status_code == 409
    assert answer.json() == {"error": copy.AI_CONSENT_NEEDED, "fix": "consent"}
    assert seen == [] and keys.get_key("anthropic") is None


def test_a_claude_key_is_checked_at_anthropic_then_kept(client, seen):
    made = connect(client, CLAUDE)
    assert made.status_code == 201
    assert made.json() == {"id": "anthropic", "name": "Claude", "provider": "anthropic"}
    c.AiLink.model_validate_json(made.text, strict=True)
    never_echoed(made, CLAUDE)
    assert {r.url.host for r in seen} == {"api.anthropic.com"}  # its fixed address only
    assert keys.get_key("anthropic") == CLAUDE

    again = connect(client, CLAUDE)
    assert (again.status_code, again.json()) == (200, made.json())
    assert len(seen) == 1  # linked already: not sent again


def test_an_openai_key_makes_a_standard_link(client, seen):
    made = connect(client, OPENAI)
    assert made.status_code == 201
    link = made.json()
    assert link["id"].startswith("standard:") and link["name"] == "OpenAI"
    assert [(r.url.host, r.url.path) for r in seen] == [("api.openai.com", "/v1/models")]
    assert keys.get_key(link["id"]) == OPENAI
    listed = client.get("/settings/ai", headers=AUTH).json()["connectors"]
    assert {"id": link["id"], "key_set": True} in [
        {"id": x["id"], "key_set": x["key_set"]} for x in listed
    ]
    assert connect(client, OPENAI).status_code == 200


def test_a_key_the_provider_refuses_is_not_kept(seen):
    client = TestClient(create_app(SECRET, ai_http=providers(seen, anthropic_status=401)))
    answer = connect(client, CLAUDE)
    assert answer.status_code == 409
    assert answer.json() == {"error": copy.KEY_REFUSED, "fix": "ai", "field": "key"}
    never_echoed(answer, CLAUDE)
    assert keys.get_key("anthropic") is None


def test_a_provider_that_cannot_be_reached(seen):
    def down(request):
        raise httpx2.ConnectError("no route - sample")

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(down))
    answer = connect(TestClient(create_app(SECRET, ai_http=http)), GEMINI)
    assert answer.status_code == 502
    said = copy.fill(copy.AI_NO_CONNECTION, provider="Gemini")
    assert answer.json() == {"error": said, "fix": "retry"}
    assert settings.ai().get("standard") is None


def test_the_key_store_down(client, failing_keyring):
    answer = connect(client, CLAUDE)
    assert answer.status_code == 503
    assert answer.json() == {"error": copy.KEY_STORE_DOWN, "fix": "retry"}


def test_secrets_never_in_settings(client):
    assert connect(client, CLAUDE).status_code == 201
    assert connect(client, OPENAI).status_code == 201
    answer = client.get("/settings", headers=AUTH)
    assert answer.status_code == 200
    stored = (settings.data_dir() / "settings.json").read_text(encoding="utf-8")
    for key in (CLAUDE, OPENAI):
        never_echoed(answer, key)
        assert key not in stored and key[8:40] not in stored
    # the screen reads "connected" only
    assert all(x["key_set"] for x in client.get("/settings/ai", headers=AUTH).json()["connectors"])


# Disconnecting ---------------------------------------------------------------------------------


def test_disconnect_the_claude_key_and_take_it_back(client):
    connect(client, CLAUDE)
    removed = client.delete("/settings/ai/links/anthropic", headers=AUTH)
    assert removed.status_code == 200 and removed.headers["cache-control"] == "no-store"
    undo = c.Undoable.model_validate_json(removed.text, strict=True)
    assert keys.get_key("anthropic") is None  # out of use at once
    assert CLAUDE not in (settings.data_dir() / "settings.json").read_text(encoding="utf-8")
    assert client.post(f"/undo/{undo.undo}", headers=AUTH).status_code == 204
    assert keys.get_key("anthropic") == CLAUDE


def test_a_disconnected_key_leaves_the_key_store_when_the_window_ends(client, memory_keyring):
    connect(client, CLAUDE)
    undo = client.delete("/settings/ai/links/anthropic", headers=AUTH).json()["undo"]
    client.app.state.trash.purge(undo)
    assert CLAUDE not in memory_keyring.store.values()


def test_disconnect_a_standard_link(client):
    link = connect(client, OPENAI).json()["id"]
    removed = client.delete(f"/settings/ai/links/{link}", headers=AUTH)
    assert removed.status_code == 200
    assert link not in [
        x["id"] for x in client.get("/settings/ai", headers=AUTH).json()["connectors"]
    ]
    assert client.post(f"/undo/{removed.json()['undo']}", headers=AUTH).status_code == 204
    assert keys.get_key(link) == OPENAI


def test_what_is_not_a_link(client):
    for link in ("claude-code", "anthropic", "standard:abc", "elsewhere"):  # no key pasted yet
        answer = client.delete(f"/settings/ai/links/{link}", headers=AUTH)
        assert answer.status_code == 404, link
        assert answer.json() == {"error": copy.AI_LINK_NOT_FOUND}


def test_a_link_running_work_uses_is_kept(client):
    connect(client, CLAUDE)
    team = SimpleNamespace(roles={"lead": ModelChoice("anthropic", "claude-sample")})
    brief = SimpleNamespace(brief_id="5a" + "0" * 30, finished=False, setup=team)
    client.app.state.engine._briefs[brief.brief_id] = brief
    answer = client.delete("/settings/ai/links/anthropic", headers=AUTH)
    assert answer.status_code == 409
    assert answer.json() == {"error": copy.AI_LINK_IN_USE, "brief_id": brief.brief_id}
    assert keys.get_key("anthropic") == CLAUDE
