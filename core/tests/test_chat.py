import asyncio
import json
import logging
import re
import socket
import threading
import time
from pathlib import Path

import httpx
import httpx2
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import (
    ModelAuthenticationError,
    ModelConnectionError,
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
from tests.conftest import AUTH, SECRET, ui_message

KEY = "sk-ant-api03-test-key-never-shown"


async def two_words(messages, info: AgentInfo):
    yield "مرحبا"
    yield " Hello"


def fake(stream_function) -> TestClient:
    return TestClient(
        create_app(SECRET, model_factory=lambda: FunctionModel(stream_function=stream_function))
    )


def test_chat_streams_text_parts():
    client = fake(two_words)
    r = client.post("/chat", json=ui_message("سعّر البند ده"), headers=AUTH)
    body = r.text
    assert r.status_code == 200
    assert '"type":"text-delta"' in body and "مرحبا" in body and " Hello" in body
    assert body.rstrip().endswith("[DONE]")


def test_chat_needs_the_secret():
    client = fake(two_words)
    assert client.post("/chat", json=ui_message("hello")).status_code == 401


def test_chat_without_key_explains_how_to_add_one():
    assert keys.get_key("anthropic") is None
    client = TestClient(create_app(SECRET))  # the real model factory, with an empty key store
    r = client.post("/chat", json=ui_message("hello"), headers=AUTH)
    body = r.text
    assert r.status_code == 200
    assert '"type":"text-delta"' in body
    assert copy.NO_KEY["ar"] in body and copy.NO_KEY["en"] in body
    assert "Traceback" not in body and '"type":"error"' not in body
    assert body.rstrip().endswith("[DONE]")


def test_no_key_reply_names_the_key_button():
    # The reply must send the engineer to the button the screen really shows.
    i18n = (Path(__file__).parents[2] / "ui" / "src" / "i18n.ts").read_text(encoding="utf-8")
    label = re.search(r'aiKey: \{ en: "([^"]+)", ar: "([^"]+)" \}', i18n)
    assert label, "aiKey label not found in ui/src/i18n.ts"
    en, ar = label.groups()
    assert en in copy.NO_KEY["en"] and ar in copy.NO_KEY["ar"]
    assert "Settings" not in copy.NO_KEY["en"] and "الإعدادات" not in copy.NO_KEY["ar"]


def test_lead_instructions_are_short():
    assert len(chat.LEAD_INSTRUCTIONS.split()) <= 80


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


def test_disconnect_stops_the_model(live_server):
    slow = SlowModel()
    app = create_app(SECRET, model_factory=lambda: FunctionModel(stream_function=slow.stream))
    url = live_server(app)
    with httpx.Client(timeout=10) as client:
        with client.stream("POST", f"{url}/chat", json=ui_message("hello"), headers=AUTH) as r:
            assert r.status_code == 200
            lines = r.iter_lines()
            while '"type":"text-delta"' not in next(lines):
                pass
            assert not slow.stopped  # still connected: the model is still working
        # leaving the block closes the connection mid-reply
    deadline = time.monotonic() + 5
    while not slow.stopped and time.monotonic() < deadline:
        time.sleep(0.05)
    assert slow.stopped


def raising(error: Exception):
    async def stream(messages, info: AgentInfo):
        raise error
        yield ""  # makes this an async generator

    return stream


def error_chunk(body: str) -> dict:
    """The one `error` chunk in a UI message stream, with its text read as an {en, ar} pair."""
    chunks = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")]
    errors = [c for c in chunks if c["type"] == "error"]
    assert len(errors) == 1, chunks
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
            copy.KEY_REFUSED,
        ),
        (ModelConnectionError(chat.LEAD_MODEL, "Connection error."), copy.NO_CONNECTION),
        (
            ModelHTTPError.for_category(
                ModelRateLimitError,
                status_code=429,
                model_name=chat.LEAD_MODEL,
                body=anthropic_body("rate_limit_error", "Number of request tokens exceeded"),
            ),
            copy.CLAUDE_BUSY,
        ),
        (
            ModelHTTPError.for_category(
                ModelOverloadedError,
                status_code=529,
                model_name=chat.LEAD_MODEL,
                body=anthropic_body("overloaded_error", "Overloaded"),
            ),
            copy.CLAUDE_BUSY,
        ),
        (UnexpectedModelBehavior("Received empty model response"), copy.MODEL_FAILED),
    ],
    ids=["key-refused", "no-connection", "rate-limit", "overloaded", "other"],
)
def test_model_errors_reach_the_screen_in_plain_words(error, plain, caplog):
    caplog.set_level(logging.INFO)
    client = fake(raising(error))
    r = client.post("/chat", json=ui_message("hello"), headers=AUTH)
    assert r.status_code == 200
    assert error_chunk(r.text) == plain
    assert str(error) not in r.text  # the provider's own words stay out of the stream
    assert str(error) in caplog.text  # and go to core.log


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
    client = TestClient(create_app(SECRET, model_factory=lambda: model))
    r = client.post("/chat", json=ui_message("سعّر البند ده"), headers=AUTH)

    assert sent and KEY in sent[0]  # the request really went out with the key
    assert error_chunk(r.text) == copy.KEY_REFUSED
    assert "invalid x-api-key" not in r.text and "authentication_error" not in r.text
    assert KEY not in r.text and KEY not in caplog.text
