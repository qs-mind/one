"""Where keys are kept: the system key store, or a protected file when this computer has none.

Every key (AI keys, project keys, the Backup key, account tokens) goes through `keyring`. Most
computers have a key store (Windows Credential Manager, macOS Keychain, a Secret Service on Linux),
but some Linux desktops have none, and the core could not even create a project. `choose()` runs
once at core start: when the system has no usable key store it installs `FileKeyring`, a file in
One's data folder (folder 0700, file 0600, written atomically), and records `"key_store": "file"`
in settings.json.

When a later start finds a system key store, every entry in the file is moved there and read back,
then the file is deleted and `"key_store": "system"` recorded. Moving (rather than staying on the
file) is the safer rule: keys made before the file store was needed are in the system store, so
staying on the file would leave them out of reach, and the file is the weaker place to keep keys.
The file is only ever written while it is the store in use, so its values are the newest and win.
If any step fails, the file stays the store for this start and the next start tries again.

The file sits next to the encrypted projects, so someone who copies the whole folder gets the keys
with it. That is weaker than a key store, and still better than One not starting.

Never log a value: logs name the backend and the file only.
"""

import contextlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

import keyring
from keyring.backend import KeyringBackend
from keyring.backends import chainer, fail
from keyring.errors import KeyringError, PasswordDeleteError

from qsone import settings

FILE_NAME = "keystore.json"
VERSION = 1
log = logging.getLogger(__name__)


class FileKeyring(KeyringBackend):
    """Keys in `<data folder>/keystore.json`: {"version": 1, "keys": {service: {user: value}}}.

    Errors are `KeyringError`, as from any key store, so callers keep their plain messages. A file
    that cannot be read is never written over: it may still hold keys.
    """

    viable = False  # keyring never picks it by itself; only `choose()` installs it
    priority = 0

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self._lock = threading.Lock()  # the routes run in worker threads

    def get_password(self, service: str, username: str) -> str | None:
        with self._lock:
            return self._read().get(service, {}).get(username)

    def set_password(self, service: str, username: str, password: str) -> None:
        with self._lock:
            keys = self._read()
            keys.setdefault(service, {})[username] = password
            self._write(keys)

    def delete_password(self, service: str, username: str) -> None:
        with self._lock:
            keys = self._read()
            if username not in keys.get(service, {}):
                raise PasswordDeleteError("no such key")
            del keys[service][username]
            if not keys[service]:
                del keys[service]
            self._write(keys)

    def entries(self) -> list[tuple[str, str, str]]:
        with self._lock:
            keys = self._read()
        return [(s, u, v) for s, users in keys.items() for u, v in users.items()]

    def protect(self) -> None:
        """Folder 0700 and file 0600 on POSIX, also for a file copied in by hand."""
        if os.name != "posix":
            return  # the data folder is under the user's own profile
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(self.path.parent, 0o700)
            if self.path.exists():
                os.chmod(self.path, 0o600)

    def _read(self) -> dict[str, dict[str, str]]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as error:
            raise KeyringError(f"the key file cannot be read ({type(error).__name__})") from None
        try:
            saved = json.loads(text)
            keys = saved["keys"]
            ok = isinstance(keys, dict) and all(
                isinstance(users, dict)
                and all(isinstance(u, str) and isinstance(v, str) for u, v in users.items())
                for users in keys.values()
            )
        except (ValueError, KeyError, TypeError):
            ok = False
        if not ok:
            raise KeyringError("the key file is damaged")  # its text is never put in a message
        return keys

    def _write(self, keys: dict[str, dict[str, str]]) -> None:
        data = json.dumps({"version": VERSION, "keys": keys}, ensure_ascii=False).encode()
        try:
            _write_atomic(self.path, data)
        except OSError as error:
            raise KeyringError(f"the key file cannot be written ({type(error).__name__})") from None


def _write_atomic(path: Path, data: bytes) -> None:
    """A temporary file (0600 from `mkstemp`), synced, then moved over the old one: a crash
    leaves the old file or the new one, never half of one."""
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(folder, 0o700)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".keystore-", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    if os.name == "posix":
        directory = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(directory)  # the rename itself survives a power cut
        finally:
            os.close(directory)


def name(backend: KeyringBackend) -> str:
    return f"{type(backend).__module__}.{type(backend).__name__}"


def usable(backend: KeyringBackend) -> bool:
    """False for keyring's "no backend" stand-ins: the fail backend, an empty chainer, or any
    backend whose priority is 0 or less (or cannot be told)."""
    if isinstance(backend, fail.Keyring | FileKeyring):
        return False
    if isinstance(backend, chainer.ChainerBackend) and not backend.backends:
        return False
    try:
        return backend.priority > 0
    except Exception:  # a backend's priority check may raise anything when its service is gone
        return False


def kind() -> str:
    """ "file" when this start keeps keys in the file, else "system"."""
    return "file" if isinstance(keyring.get_keyring(), FileKeyring) else "system"


def choose() -> str:
    """Pick where keys are kept for this start, install it, and return "system" or "file"."""
    store = FileKeyring(settings.data_dir() / FILE_NAME)
    system = keyring.get_keyring()
    if not usable(system):
        log.warning("No system key store (%s): keys are kept in %s", name(system), FILE_NAME)
        return _use_file(store)
    if store.path.exists() and not _move(store, system):
        return _use_file(store)
    _record("system")
    return "system"


def _use_file(store: FileKeyring) -> str:
    store.protect()
    keyring.set_keyring(store)
    _record("file")
    return "file"


def _move(store: FileKeyring, system: KeyringBackend) -> bool:
    """Every key from the file into the system store, each read back; then the file goes."""
    try:
        entries = store.entries()
        for service, user, value in entries:
            system.set_password(service, user, value)
            if system.get_password(service, user) != value:
                raise KeyringError("a key read back differently")
        store.path.unlink()
    except Exception as error:  # any failure: the file stays the store, the next start retries
        log.warning(
            "Keys stay in %s: moving them to the system key store (%s) failed (%s)",
            FILE_NAME,
            name(system),
            type(error).__name__,
        )
        return False
    log.info(
        "Moved %d keys from %s to the system key store (%s)", len(entries), FILE_NAME, name(system)
    )
    return True


def _record(store: str) -> None:
    """The flag in settings.json says which store this folder uses; the file itself decides."""
    if settings.load().get("key_store", "system") == store:
        return
    try:
        settings.save("key_store", store)
    except OSError as error:
        log.warning("Could not record the key store in settings.json (%s)", type(error).__name__)
