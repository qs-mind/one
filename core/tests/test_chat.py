import asyncio
import json
import logging
import re
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import httpx
import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelHTTPError,
    ModelOverloadedError,
    ModelRateLimitError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from qsone import chat, copy, keys
from qsone.app import create_app
from qsone.engine.types import ModelChoice
from tests.conftest import AUTH, SECRET, ui_message
from tests.engine_fakes import OPUS, FakeSleep
from tests.test_engine_runner import FakeLink

KEY = "sk-ant-api03-test-key-never-shown"
FABLE = replace(OPUS, choice=ModelChoice("anthropic", "claude-fable-5-1"), name="Fable (sample)")


def message(text: str) -> dict:
    """A chat request body for the General chat, as the AI SDK `useChat` sends it."""
    return ui_message(text) | {"id": "general"}


async def two_words(messages, info: AgentInfo):
    yield "مرحبا"
    yield " Hello"


def link(model) -> list:
    """The Native Link with one model (and a second id for the same model)."""
    models = {OPUS.choice.model: model, FABLE.choice.model: model}
    return [FakeLink("anthropic", "Claude", "anthropic", models, sheet=[OPUS, FABLE])]


def fake(stream_function) -> TestClient:
    model = FunctionModel(stream_function=stream_function)
    return TestClient(create_app(SECRET, connectors=lambda: link(model), sleep=FakeSleep()))


def chunks(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")]


def test_chat_streams_text_parts():
    client = fake(two_words)
    r = client.post("/chat", json=message("سعّر البند ده"), headers=AUTH)
    body = r.text
    assert r.status_code == 200
    assert '"type":"text-delta"' in body and "مرحبا" in body and " Hello" in body
    assert body.rstrip().endswith("[DONE]")


def test_chat_needs_the_secret():
    client = fake(two_words)
    assert client.post("/chat", json=message("hello")).status_code == 401


def test_chat_without_ai_explains_how_to_add_one():
    assert keys.get_key("anthropic") is None
    client = TestClient(create_app(SECRET))  # the real connectors, with an empty key store
    r = client.post("/chat", json=message("hello"), headers=AUTH)
    body = r.text
    assert r.status_code == 200
    assert '"type":"text-delta"' in body
    assert copy.NO_AI["ar"] in body and copy.NO_AI["en"] in body
    assert "Traceback" not in body and '"type":"error"' not in body
    assert body.rstrip().endswith("[DONE]")
    assert client.get("/chat/general/messages", headers=AUTH).json() == {"messages": []}


def test_no_ai_reply_names_the_ai_button():
    # The reply must send the engineer to the button the screen really shows.
    i18n = (Path(__file__).parents[2] / "ui" / "src" / "i18n.ts").read_text(encoding="utf-8")
    label = re.search(r'\bai: \{ en: "([^"]+)", ar: "([^"]+)" \}', i18n)
    assert label, "ai label not found in ui/src/i18n.ts"
    en, ar = label.groups()
    assert f"“{en}”" in copy.NO_AI["en"] and f"«{ar}»" in copy.NO_AI["ar"]
    assert "Settings" not in copy.NO_AI["en"] and "الإعدادات" not in copy.NO_AI["ar"]


def test_lead_model_is_one_constant():
    assert chat.LEAD_MODEL == "claude-opus-5-5"


def test_the_lead_qs_knows_which_model_it_is():
    seen: list[str] = []

    async def note_instructions(messages, info: AgentInfo):
        seen.append(info.instructions or "")
        yield "ok"

    client = fake(note_instructions)
    client.post("/chat", json=message("which model are you?"), headers=AUTH)
    client.put("/settings/model", json={"id": FABLE.choice.model}, headers=AUTH)
    client.post("/chat", json=message("and now?"), headers=AUTH)
    assert "Lead QS" in seen[0]  # the Lead QS's own instructions
    assert chat.LEAD_MODEL in seen[0]  # the default until the engineer picks one
    assert FABLE.choice.model in seen[1] and chat.LEAD_MODEL not in seen[1]  # read per Brief


class SlowModel:
    """Streams one word, then waits a long time, as a model would mid-reply."""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.finished = False

    async def stream(self, messages, info: AgentInfo):
        self.task = asyncio.current_task()  # the task that is calling the model
        yield "أول"
        await asyncio.sleep(30)
        yield " never"
        self.finished = True

    @property
    def stopped(self) -> bool:
        # Ended without finishing. With a real model, ending this task leaves
        # `async with response.source` in AnthropicModel, which closes the HTTP stream.
        return self.task is not None and self.task.done() and not self.finished


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server():
    """Run the app on a real uvicorn server, so a client disconnect is a real one."""
    servers = []

    def start(app) -> str:
        port = free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        threading.Thread(target=server.run, daemon=True).start()
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.02)
        servers.append(server)
        return f"http://127.0.0.1:{port}"

    yield start
    for server in servers:
        server.should_exit = True


def test_disconnect_keeps_the_brief_and_stop_ends_it(live_server):
    slow = SlowModel()
    model = FunctionModel(stream_function=slow.stream)
    url = live_server(create_app(SECRET, connectors=lambda: link(model)))
    brief = None
    with httpx.Client(timeout=10) as client:
        with client.stream("POST", f"{url}/chat", json=message("hello"), headers=AUTH) as r:
            assert r.status_code == 200
            for line in r.iter_lines():
                if line.startswith("data: {"):
                    chunk = json.loads(line[6:])
                    if chunk["type"] == "data-status":
                        brief = chunk["id"]
                    if chunk["type"] == "text-delta":
                        break
        # leaving the block closes the connection mid-reply
        time.sleep(0.2)
        assert brief is not None and not slow.stopped  # the Brief runs on without the stream
        with client.stream("GET", f"{url}/chat/general/stream", headers=AUTH) as again:
            assert again.status_code == 200
            for line in again.iter_lines():
                if '"type":"text-delta"' in line:
                    assert "أول" in line  # replayed from its start
                    break
        r = client.post(f"{url}/briefs/{brief}/stop", headers=AUTH)
        assert r.status_code == 200 and r.json() == {"state": "stopped"}
        deadline = time.monotonic() + 5
        while not slow.stopped and time.monotonic() < deadline:
            time.sleep(0.05)
        assert slow.stopped
        assert client.get(f"{url}/chat/general/stream", headers=AUTH).status_code == 204


def raising(error: Exception):
    async def stream(messages, info: AgentInfo):
        raise error
        yield ""  # makes this an async generator

    return stream


def error_chunk(body: str) -> dict:
    """The one `error` chunk in a UI message stream, with its text read as an {en, ar} pair."""
    errors = [c for c in chunks(body) if c["type"] == "error"]
    assert len(errors) == 1, chunks(body)
    return json.loads(errors[0]["errorText"])


def anthropic_body(kind: str, message: str) -> dict:
    return {"type": "error", "error": {"type": kind, "message": message}}


@pytest.mark.parametrize(
    "error, plain",
    [
        (
            ModelHTTPError.for_category(
                ModelAuthenticationError,
                status_code=401,
                model_name=chat.LEAD_MODEL,
                body=anthropic_body("authentication_error", "invalid x-api-key"),
            ),
            copy.fill(copy.AI_KEY_REFUSED, provider="Claude"),
        ),
        (
            ModelHTTPError.for_category(
                ModelRateLimitError,
                status_code=429,
                model_name=chat.LEAD_MODEL,
                body=anthropic_body("rate_limit_error", "Number of request tokens exceeded"),
            ),
            copy.fill(copy.AI_FAILED, provider="Claude"),
        ),
        (
            ModelHTTPError.for_category(
                ModelOverloadedError,
                status_code=529,
                model_name=chat.LEAD_MODEL,
                body=anthropic_body("overloaded_error", "Overloaded"),
            ),
            copy.fill(copy.AI_FAILED, provider="Claude"),
        ),
        (
            UnexpectedModelBehavior("Received empty model response"),
            copy.fill(copy.AI_FAILED, provider="Claude"),
        ),
    ],
    ids=["key-refused", "rate-limit", "overloaded", "other"],
)
def test_model_errors_reach_the_screen_in_plain_words(error, plain, caplog):
    caplog.set_level(logging.INFO)
    model = FunctionModel(stream_function=raising(error))
    only = [FakeLink("anthropic", "Claude", "anthropic", {OPUS.choice.model: model}, sheet=[OPUS])]
    client = TestClient(create_app(SECRET, connectors=lambda: only, sleep=FakeSleep()))
    r = client.post("/chat", json=message("hello"), headers=AUTH)
    assert r.status_code == 200
    assert error_chunk(r.text) == plain
    assert str(error) not in r.text  # the provider's own words stay out of the stream
    assert str(error) in caplog.text  # and go to core.log


def test_no_connection_waits_and_then_answers():
    calls = []

    async def once_offline(messages, info: AgentInfo):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("no route - sample")
        yield "رجعنا"

    sleep = FakeSleep()
    model = FunctionModel(stream_function=once_offline)
    client = TestClient(create_app(SECRET, connectors=lambda: link(model), sleep=sleep))
    r = client.post("/chat", json=message("hello"), headers=AUTH)
    states = [c["data"]["state"] for c in chunks(r.text) if c["type"] == "data-status"]
    assert "waiting_connection" in states and states[-1] == "done"
    assert copy.WAITING_INTERNET["en"] in r.text and "رجعنا" in r.text
    assert sleep.delays == [5] and '"type":"error"' not in r.text


def test_refused_key_from_anthropic_is_plain_and_never_shows_the_key(caplog):
    caplog.set_level(logging.INFO)
    sent: list[str] = []

    def anthropic(request: httpx2.Request) -> httpx2.Response:
        sent.append(" ".join(request.headers.values()))
        body = anthropic_body("authentication_error", "invalid x-api-key")
        return httpx2.Response(401, json=body, headers={"x-should-retry": "false"})

    provider = AnthropicProvider(
        api_key=KEY, http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(anthropic))
    )
    model = AnthropicModel(chat.LEAD_MODEL, provider=provider)
    client = TestClient(create_app(SECRET, connectors=lambda: link(model)))
    r = client.post("/chat", json=message("سعّر البند ده"), headers=AUTH)

    assert sent and KEY in sent[0]  # the request really went out with the key
    assert error_chunk(r.text) == copy.fill(copy.AI_KEY_REFUSED, provider="Claude")
    assert "invalid x-api-key" not in r.text and "authentication_error" not in r.text
    assert KEY not in r.text and KEY not in caplog.text
