"""What keeps the bench off everything real: a key store in memory, no internet, no Claude Code, no
browser.

`install()` is called once, before the core starts. Loopback stays open: the screen reaches the
core, and the core its own MCP server, through 127.0.0.1."""

import asyncio.selector_events
import socket
import webbrowser

import keyring
from keyring.backend import KeyringBackend

from qsone.engine.connectors import claude_code
from qsone.journey import claude_code as first_launch_claude


class MemoryKeyring(KeyringBackend):
    """Keys in a dict: the system key store is never read or written."""

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


def _local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    host = str(host or "").split("%")[0].lower()
    return host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("127.")


def _refuse(family, address) -> None:
    if family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        raise ConnectionRefusedError(f"the bench may not reach the internet: {address[0]}")


def install() -> None:
    keyring.set_keyring(MemoryKeyring())

    connect, connect_ex, getaddrinfo = (
        socket.socket.connect,
        socket.socket.connect_ex,
        socket.getaddrinfo,
    )

    def guarded_connect(self, address):
        _refuse(self.family, address)
        return connect(self, address)

    def guarded_connect_ex(self, address):
        _refuse(self.family, address)
        return connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _local(host):
            raise socket.gaierror(socket.EAI_NONAME, f"the bench may not look up {host}")
        return getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.getaddrinfo = guarded_getaddrinfo
    loop_class = asyncio.selector_events.BaseSelectorEventLoop
    inner = loop_class.sock_connect

    async def guarded_sock_connect(self, sock, address):
        _refuse(sock.family, address)
        return await inner(self, sock, address)

    loop_class.sock_connect = guarded_sock_connect

    # The engineer's own Claude Code is never found, so never run.
    claude_code.executable = lambda picked: (None, "CLAUDE_CODE_MISSING")
    first_launch_claude.on_path = lambda: None  # the first launch's own search, too
    first_launch_claude.find_claude = lambda: (None, None)
    # A link the core opens for the page (terms, privacy, sign-in) opens no browser on this machine.
    webbrowser.open = lambda *args, **kwargs: False
