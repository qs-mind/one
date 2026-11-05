import json
import logging

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.anthropic import AnthropicModel

from qsone import chat, copy, keys, models, settings
from qsone.app import create_app
from tests.conftest import AUTH, SECRET

KEY = "sk-ant-api03-test-key-never-shown"


def info(model_id: str, name: str, released: str, lifecycle: str = "active") -> dict:
    """One model as Anthropic's models list sends it."""
    return {
        "type": "model",
        "id": model_id,
        "display_name": name,
        "created_at": released,
        "lifecycle": lifecycle,
    }


def anthropic_models(pages: list[list[dict]], seen: list[httpx2.Request]) -> httpx2.AsyncClient:
    """A fake Anthropic models endpoint, one page per request; no request leaves the machine."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        index = len(seen) - 1
        page = pages[index]
        more = index + 1 < len(pages)
        body = {
            "data": page,
            "has_more": more,
            "first_id": page[0]["id"],
            "last_id": page[-1]["id"],
        }
        return httpx2.Response(200, json=body)

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def refusing(status: int, kind: str, message: str) -> httpx2.AsyncClient:
    def handle(request: httpx2.Request) -> httpx2.Response:
        body = {"type": "error", "error": {"type": kind, "message": message}}
        return httpx2.Response(status, json=body, headers={"x-should-retry": "false"})

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handle))


def lister(http_client: httpx2.AsyncClient):
    return lambda api_key: models.list_models(api_key, http_client=http_client)


def client_with(models_lister) -> TestClient:
    return TestClient(create_app(SECRET, models_lister=models_lister))


# GET /settings/models


def test_lists_the_models_the_key_can_use_newest_first():
    seen: list[httpx2.Request] = []
    pages = [
        [
            info("claude-opus-5-5", "Claude Opus 5.5", "2026-09-01T00:00:00Z"),
            info("claude-old-1", "Claude Old 1", "2024-01-01T00:00:00Z", lifecycle="retired"),
        ],
        [info("claude-fable-5-1", "Claude Fable 5.1", "2026-10-01T00:00:00Z")],
    ]
    keys.set_key("anthropic", KEY)
    client = client_with(lister(anthropic_models(pages, seen)))

    r = client.get("/settings/models", headers=AUTH)

    assert r.status_code == 200
    assert r.json() == [
        {"id": "claude-fable-5-1", "name": "Claude Fable 5.1"},
        {"id": "claude-opus-5-5", "name": "Claude Opus 5.5"},
    ]  # every page, newest first, and no retired model
    assert [req.url.path for req in seen] == ["/v1/models", "/v1/models"]
    assert KEY in " ".join(seen[0].headers.values())  # the engineer's own key
    assert seen[1].url.params["after_id"] == "claude-old-1"
    assert KEY not in r.text


def test_no_key_says_how_to_add_one():
    called: list[str] = []

    async def never(api_key: str) -> list[dict[str, str]]:
        called.append(api_key)
        return []

    r = client_with(never).get("/settings/models", headers=AUTH)
    assert r.status_code == 409
    assert r.json() == {"error": copy.NO_KEY, "fix": "ai"}
    assert called == []


@pytest.mark.parametrize(
    "status, kind, message, plain",
    [
        (401, "authentication_error", "invalid x-api-key", copy.KEY_REFUSED),
        (403, "permission_error", "not allowed", copy.KEY_REFUSED),
        (429, "rate_limit_error", "Too many requests", copy.CLAUDE_BUSY),
        (529, "overloaded_error", "Overloaded", copy.CLAUDE_BUSY),
        (500, "api_error", "Internal server error", copy.CLAUDE_BUSY),
        (400, "invalid_request_error", "Bad request", copy.MODELS_FAILED),
    ],
    ids=["key-refused", "forbidden", "rate-limit", "overloaded", "server-error", "other"],
)
def test_provider_errors_reach_the_screen_in_plain_words(status, kind, message, plain, caplog):
    caplog.set_level(logging.DEBUG)
    keys.set_key("anthropic", KEY)
    r = client_with(lister(refusing(status, kind, message))).get("/settings/models", headers=AUTH)
    assert r.status_code == 502
    assert r.json() == copy.error(plain)
    assert message not in r.text and kind not in r.text  # the provider's own words stay out
    assert message in caplog.text  # and go to core.log
    assert KEY not in r.text and KEY not in caplog.text


def test_no_connection_is_plain():
    async def offline(api_key: str) -> list[dict[str, str]]:
        raise anthropic.APIConnectionError(
            request=httpx2.Request("GET", "https://api.anthropic.com/v1/models")
        )

    keys.set_key("anthropic", KEY)
    r = client_with(offline).get("/settings/models", headers=AUTH)
    assert r.status_code == 502 and r.json() == {"error": copy.NO_CONNECTION, "fix": "retry"}


# GET and PUT /settings/model


def test_the_lead_model_starts_as_the_default():
    r = TestClient(create_app(SECRET)).get("/settings/model", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"id": chat.LEAD_MODEL}


def test_chosen_model_is_saved_in_the_settings_file(data_dir):
    client = TestClient(create_app(SECRET))
    r = client.put("/settings/model", json={"id": " claude-fable-5-1 "}, headers=AUTH)
    assert r.status_code == 200 and r.json() == {"id": "claude-fable-5-1"}
    assert client.get("/settings/model", headers=AUTH).json() == {"id": "claude-fable-5-1"}

    saved = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
    lead = {"connector": "anthropic", "model": "claude-fable-5-1"}  # the Lead QS's role (Plan 4)
    assert saved == {"ai": {"roles": {"lead": lead}}}


def test_the_next_message_uses_the_chosen_model():
    keys.set_key("anthropic", KEY)
    client = TestClient(create_app(SECRET))
    client.put("/settings/model", json={"id": "claude-fable-5-1"}, headers=AUTH)
    model = chat.default_model()
    assert isinstance(model, AnthropicModel) and model.model_name == "claude-fable-5-1"


def test_the_key_never_goes_in_the_settings_file(data_dir):
    client = TestClient(create_app(SECRET))
    client.put("/settings/ai-key", json={"provider": "anthropic", "value": KEY}, headers=AUTH)
    client.put("/settings/model", json={"id": "claude-fable-5-1"}, headers=AUTH)
    assert KEY not in (data_dir / "settings.json").read_text(encoding="utf-8")


def test_bad_model_choice_is_refused():
    client = TestClient(create_app(SECRET))
    assert client.put("/settings/model", json={"id": "  "}, headers=AUTH).status_code == 422
    assert client.put("/settings/model", json={}, headers=AUTH).status_code == 422
    assert client.get("/settings/model", headers=AUTH).json() == {"id": chat.LEAD_MODEL}


def test_unwritable_settings_folder_is_plain(data_dir):
    data_dir.write_text("a file where the folder should be", encoding="utf-8")
    r = TestClient(create_app(SECRET)).put("/settings/model", json={"id": "x"}, headers=AUTH)
    assert r.status_code == 503 and r.json() == {"error": copy.MODEL_NOT_SAVED}


def test_unreadable_settings_file_falls_back_to_the_default(data_dir):
    data_dir.mkdir(parents=True)
    (data_dir / "settings.json").write_text("{not json", encoding="utf-8")
    assert chat.lead_model_id() == chat.LEAD_MODEL
    (data_dir / "settings.json").write_text('{"lead_model": 5}', encoding="utf-8")
    assert chat.lead_model_id() == chat.LEAD_MODEL


def test_model_settings_need_the_secret():
    client = TestClient(create_app(SECRET))
    assert client.get("/settings/models").status_code == 401
    assert client.get("/settings/model").status_code == 401
    assert client.put("/settings/model", json={"id": "claude-fable-5-1"}).status_code == 401
    assert chat.lead_model_id() == chat.LEAD_MODEL


def test_settings_live_in_the_app_data_folder(monkeypatch):
    monkeypatch.delenv("QSONE_DATA_DIR")
    # The desktop's identifier, as Tauri names its app data folder.
    assert settings.data_dir().name == "app.qsmind.one"
