import asyncio.proactor_events
import asyncio.selector_events
import ipaddress
import socket
import threading
import time
import uuid
from pathlib import Path

import keyring
import pytest
import uvicorn
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError


class MemoryKeyring(KeyringBackend):
    """Keeps keys in a dict so tests never touch the real system key store."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


class FailingKeyring(KeyringBackend):
    """A key store that is down: every call raises `KeyringError`."""

    priority = 1

    def get_password(self, service: str, username: str) -> str | None:
        raise KeyringError("key store not available")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise KeyringError("key store not available")

    def delete_password(self, service: str, username: str) -> None:
        raise KeyringError("key store not available")


@pytest.fixture
def failing_keyring(memory_keyring):
    """Replaces the autouse memory keyring for one test; it is restored afterwards."""
    backend = FailingKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(memory_keyring)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Tests never touch the real data folder."""
    path = tmp_path / "data"
    monkeypatch.setenv("QSONE_DATA_DIR", str(path))
    return path


SECRET = "s3cret"
AUTH = {"Authorization": f"Bearer {SECRET}"}


def ui_message(text: str) -> dict:
    """A chat request body as the AI SDK `useChat` sends it."""
    return {
        "trigger": "submit-message",
        "id": "chat-1",
        "messages": [{"id": "m-1", "role": "user", "parts": [{"type": "text", "text": text}]}],
    }


# ---------------------------------------------------------------------------------------------
# Agent engine (Plan 4).
# ---------------------------------------------------------------------------------------------


def _local_host(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode()
    host = str(host).split("%")[0]  # an IPv6 scope
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refuse_internet(family, address) -> None:
    if family in (socket.AF_INET, socket.AF_INET6) and not _local_host(address[0]):
        raise ConnectionRefusedError(f"tests may not reach the internet: {address[0]}")


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    """Every test: a connection to anything but this computer is refused, and so is a name
    lookup. Loopback and AF_UNIX work. Covers plain sockets and asyncio's own connect (which
    bypasses `socket.connect` on Windows). Not child processes: the fake `claude` refuses
    non-loopback MCP addresses itself."""
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    getaddrinfo = socket.getaddrinfo

    def guarded_connect(self, address):
        _refuse_internet(self.family, address)
        return connect(self, address)

    def guarded_connect_ex(self, address):
        _refuse_internet(self.family, address)
        return connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _local_host(host):
            raise socket.gaierror(socket.EAI_NONAME, f"tests may not look up {host}")
        return getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    for loop_class in (
        asyncio.selector_events.BaseSelectorEventLoop,
        asyncio.proactor_events.BaseProactorEventLoop,
    ):

        async def guarded_sock_connect(self, sock, address, _inner=loop_class.sock_connect):
            _refuse_internet(sock.family, address)
            return await _inner(self, sock, address)

        monkeypatch.setattr(loop_class, "sock_connect", guarded_sock_connect)


@pytest.fixture
def anyio_backend():
    """`async def` tests run on asyncio, as the core does."""
    return "asyncio"


@pytest.fixture
def fake_clock():
    """A clock the engine takes as an argument: call it for an aware UTC `datetime`."""
    from tests.engine_fakes import FakeClock

    return FakeClock()


@pytest.fixture
def fake_sleep(fake_clock):
    """An `asyncio.sleep` stand-in: records each delay, moves `fake_clock`, returns at once."""
    from tests.engine_fakes import FakeSleep

    return FakeSleep(fake_clock)


@pytest.fixture
def rec(data_dir):
    """An open sample project under `<data>/projects/`, closed after the test."""
    from qsone.records.project import Records

    folder = data_dir / "projects" / uuid.uuid4().hex
    project = Records.create(folder, name="مشروع - عينة", actor="engineer")
    yield project
    project.close()


@pytest.fixture
def general(data_dir):
    """An open Engineer Records file at `<data>/engineer/`, closed after the test."""
    from qsone.engine.general import open_engineer_records

    engineer = open_engineer_records(data_dir)
    yield engineer
    engineer.close()


@pytest.fixture
def serve_app():
    """Runs ASGI apps on real uvicorn servers on 127.0.0.1; `serve_app(app)` gives the base URL."""
    servers = []

    def start(app) -> str:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.02)
        servers.append((server, thread))
        return f"http://127.0.0.1:{port}"

    yield start
    for server, thread in servers:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture
def fake_claude_path() -> Path:
    """The stand-in `claude`. Run it as `engine_fakes.fake_claude_command()`."""
    return Path(__file__).parent / "fakes" / "fake_claude.py"
