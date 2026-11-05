"""What keeps the bench off everything real: a key store in memory, no internet, no Claude Code, no
browser.

`install()` is called once, before the core starts. Loopback stays open: the screen reaches the
core, and the core its own MCP server, through 127.0.0.1."""

import asyncio.selector_events
import json
import os
import socket
import webbrowser
from pathlib import Path

import keyring
from keyring.backend import KeyringBackend

from qsone.engine.connectors import claude_code
from qsone.journey import claude_code as first_launch_claude


class MemoryKeyring(KeyringBackend):
    """Keys in a dict: the system key store is never read or written."""

    priority = 1

    def __init__(self, file: Path | None = None) -> None:
        """With `file` (an audit's QSONE_BENCH_KEYRING_FILE, inside the bench's throwaway folder)
        the keys also live in that file, so a core killed mid-walk and started again still opens
        its projects. Off by default: the walks keep every key in memory only."""
        super().__init__()
        self.file = file
        self.store: dict[tuple[str, str], str] = {}
        if file is not None and file.exists():
            self.store = {(s, u): p for s, u, p in json.loads(file.read_text("utf8"))}

    def _save(self) -> None:
        if self.file is not None:  # opened owner-only, so the keys are never readable by others
            fd = os.open(self.file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf8") as out:
                json.dump([[s, u, p] for (s, u), p in self.store.items()], out)

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password
        self._save()

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)
        self._save()


def _local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    host = str(host or "").split("%")[0].lower()
    return host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("127.")


_allowed_hosts: set[str] = set()  # named in `install(allow=...)`: an audit's one real AI provider
_allowed_addresses: set[str] = set()  # what those names were looked up to


def _refuse(family, address) -> None:
    if family in (socket.AF_INET, socket.AF_INET6) and not _local(address[0]):
        if str(address[0]).split("%")[0] in _allowed_addresses:
            return
        raise ConnectionRefusedError(f"the bench may not reach the internet: {address[0]}")


def install(allow: tuple[str, ...] = ()) -> None:
    """`allow` names hosts the bench may reach after all (none by default)."""
    _allowed_hosts.update(h.lower() for h in allow)
    file = os.environ.get("QSONE_BENCH_KEYRING_FILE")
    keyring.set_keyring(MemoryKeyring(Path(file) if file else None))

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
        name = host.decode() if isinstance(host, bytes) else str(host or "")
        if name.lower() in _allowed_hosts:
            found = getaddrinfo(host, *args, **kwargs)
            _allowed_addresses.update(str(info[4][0]) for info in found)
            return found
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
