"""Private local sessions. Never launch against ONE's normal profile or stop an unowned PID."""

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from qsone import settings
from qsone.cli.texts import CliError

CORE = Path(__file__).resolve().parents[2]
ROOT = CORE.parent


def default_data_dir():
    override = os.environ.pop("QSONE_DATA_DIR", None)
    try:
        return settings.data_dir().resolve()
    finally:
        if override is not None:
            os.environ["QSONE_DATA_DIR"] = override


def session_path(value=None):
    return Path(
        value
        or os.environ.get("QSONE_CLI_SESSION")
        or Path(tempfile.gettempdir()) / f"qsone-cli-{os.getuid()}" / "session.json"
    )


def port_ok(port):
    if port in (1440, 1442) or not 0 <= port <= 65535:
        raise CliError("unsafe")


def data_ok(path):
    path = Path(path).resolve()
    if path == default_data_dir() or default_data_dir() in path.parents:
        raise CliError("unsafe")
    return path


def private_parent(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise CliError("session")


def save(path, value):
    private_parent(path)
    fd, temporary = tempfile.mkstemp(prefix=".session-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load(path):
    if path.is_symlink():
        raise CliError("session")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise CliError("missing") from None
    port_ok(value["port"])
    if value.get("data_dir"):
        data_ok(value["data_dir"])
    return value


def process_identity(pid):
    """Linux birth time prevents PID reuse; cmdline separately proves the exact launcher/data."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return stat[19]
    except (OSError, IndexError):
        return None


def command(mode, port, folder, samples):
    if mode == "scripted":
        return [
            sys.executable,
            "-m",
            "tests.bench",
            "--port",
            str(port),
            "--data-dir",
            str(folder),
            "--samples",
            str(samples),
        ]
    return [
        sys.executable,
        str(ROOT / "scripts/realapp/realcore.py"),
        "--port",
        str(port),
        "--data-dir",
        str(folder),
    ]


def start(path, *, port=0, data_dir=None, mode="scripted"):
    port_ok(port)
    folder = data_ok(data_dir) if data_dir else None
    if path.exists():
        raise CliError("session")
    private_parent(path)
    # Even explicit folders must be empty: no profile reuse or key-store cross-contamination.
    if folder is not None and folder.exists() and any(folder.iterdir()):
        raise CliError("session")
    folder = folder or Path(tempfile.mkdtemp(prefix="qsone-cli-data-"))
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    samples = folder / "samples"
    if not port:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        port_ok(port)
    secret = secrets.token_urlsafe(32)
    # Whitelist OS/runtime essentials; never inherit provider keys or bench network overrides.
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        in (
            "PATH",
            "HOME",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "TMPDIR",
            "TEMP",
            "TMP",
        )
    }
    env.update(
        QSONE_SECRET=secret,
        PYTHONPATH=str(CORE),
        PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring",
    )
    argv = command(mode, port, folder, samples)
    with (folder / "core.log").open("wb") as log:
        process = subprocess.Popen(
            argv,
            cwd=CORE,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    value = dict(
        port=port,
        secret=secret,
        pid=process.pid,
        birth=process_identity(process.pid),
        data_dir=str(folder),
        samples=str(samples),
        mode=mode,
        owned=True,
        cards={},
    )
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    response = client.get(
                        f"http://127.0.0.1:{port}/health",
                        headers={"Authorization": f"Bearer {secret}"},
                    )
                    if response.is_success:
                        save(path, value)
                        return public(value)
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        raise CliError("timeout")
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def public(value):
    return {k: v for k, v in value.items() if k not in ("secret", "birth", "cards")}


def attach(path, *, port, secret_file):
    port_ok(port)
    if path.exists():
        raise CliError("session")
    secret = Path(secret_file).read_text().strip()
    with httpx.Client(trust_env=False) as client:
        response = client.get(
            f"http://127.0.0.1:{port}/health", headers={"Authorization": f"Bearer {secret}"}
        )
        if not response.is_success:
            raise CliError()
    # Attach cannot prove the server's mode; treat it conservatively as real for walk caps.
    value = dict(port=port, secret=secret, owned=False, mode="real", cards={}, samples="")
    save(path, value)
    return public(value)


def stop(path):
    value = load(path)
    if value["owned"]:
        pid = value["pid"]
        identity = process_identity(pid)
        if identity is not None:
            # A process can exit between reading stat and cmdline. Zombies keep their
            # birth identity but have no command line and must never be signalled.
            stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if stat[19] != value.get("birth"):
                raise CliError("identity")
            if stat[0] == "Z":
                path.unlink()
                return {"state": "stopped"}
            expected = command(value["mode"], value["port"], value["data_dir"], value["samples"])
            actual = Path(f"/proc/{pid}/cmdline").read_bytes().decode().rstrip("\0").split("\0")
            if identity != value.get("birth") or actual != expected:
                try:
                    ended = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                except FileNotFoundError:
                    ended = None
                if ended is None or (ended[19] == value.get("birth") and ended[0] == "Z"):
                    path.unlink()
                    return {"state": "stopped"}
                raise CliError("identity")
            os.kill(pid, signal.SIGTERM)
            # Graceful shutdown drains active work and bounded background reader /
            # model-download calls before closing Records. Their cleanup can exceed
            # ten seconds. Keep ownership checks and retain the session on timeout.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
                except FileNotFoundError:
                    break
                if stat[0] == "Z":
                    break
                time.sleep(0.1)
            else:
                raise CliError("stop_timeout")
    path.unlink()
    return {"state": "stopped" if value["owned"] else "detached"}
