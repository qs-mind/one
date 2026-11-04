import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from pydantic_ai.models.function import AgentInfo, FunctionModel

from qsone import copy, keys
from qsone.app import create_app
from tests.conftest import AUTH, SECRET, ui_message


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


def test_lead_instructions_are_short():
    from qsone import chat

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
