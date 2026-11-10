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
def refused_hub(monkeypatch):
    """Every test: the search model's default download answers 403 at once, so an app made
    without a fake hub never tries the real one, nor waits out its retries. A test that wants a
    download passes its own client (tests/hub.py)."""
    import httpx

    from qsone.meaning import download

    def refused() -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))

    monkeypatch.setattr(download, "default_client", refused)


@pytest.fixture(autouse=True)
def quiet_setup(monkeypatch):
    """Every test: an app made without its own `setup` answers GET /setup/parts but never
    starts fetching the manifest's parts. A test that wants setup to run passes one."""
    from qsone import app
    from qsone.setup.runner import Setup

    class Quiet(Setup):
        def start(self) -> None:
            pass

    monkeypatch.setattr(app, "Setup", Quiet)


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


# ---------------------------------------------------------------------------------------------
# Journey and release (Plan 8): the account, Umami, the browser and scrypt.
# ---------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """Every test: `webbrowser.open` records the URL instead of opening a browser."""
    import webbrowser

    opened: list[str] = []

    def record(url, *args, **kwargs) -> bool:
        opened.append(url)
        return True

    for name in ("open", "open_new", "open_new_tab"):
        monkeypatch.setattr(webbrowser, name, record)
    return opened


@pytest.fixture(autouse=True)
def ai_consent(request, monkeypatch):
    """Every test but those that ask for `no_consent`: the engineer said yes to the AI note
    (Plan 8), without writing settings.json, so the AI-call checks let calls through."""
    if "no_consent" in request.fixturenames:
        return
    from qsone.journey import setup_state

    given = {"at": "2026-11-05T08:00:00+00:00", "text_version": setup_state.CONSENT_VERSION}
    monkeypatch.setattr(setup_state, "consent", lambda: given)


@pytest.fixture
def no_consent():
    """The real consent from settings.json: none until the test gives it."""


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    """Every test: `hashlib.scrypt` runs with n at most 2**10, so a recovery code costs
    milliseconds. Code that calls `hashlib.scrypt(...)` through the module gets it."""
    import hashlib

    real = hashlib.scrypt

    def scrypt(password, *, salt, n, r, p, maxmem=0, dklen=64):
        return real(password, salt=salt, n=min(n, 2**10), r=r, p=p, maxmem=maxmem, dklen=dklen)

    monkeypatch.setattr(hashlib, "scrypt", scrypt)


@pytest.fixture
def fake_account(monkeypatch, no_browser):
    """The QS Mind account on 127.0.0.1 (`tests.fakes.FakeAccount`); the core finds it through
    QSONE_AUTH_ISSUER and QSONE_AUTH_CLIENT_ID."""
    from tests.fakes import FakeAccount

    account = FakeAccount(opened=no_browser)
    account.start()
    monkeypatch.setenv("QSONE_AUTH_ISSUER", account.issuer)
    monkeypatch.setenv("QSONE_AUTH_CLIENT_ID", account.client_id)
    yield account
    account.stop()


@pytest.fixture
def fake_umami(monkeypatch):
    """Umami's /api/send on 127.0.0.1 (`tests.fakes.FakeUmami`), at QSONE_USAGE_ENDPOINT."""
    from tests.fakes import FakeUmami

    umami = FakeUmami()
    umami.start()
    monkeypatch.setenv("QSONE_USAGE_ENDPOINT", umami.endpoint)
    yield umami
    umami.stop()


@pytest.fixture
def fake_claude_path() -> Path:
    """The stand-in `claude`. Run it as `engine_fakes.fake_claude_command()`."""
    return Path(__file__).parent / "fakes" / "fake_claude.py"
