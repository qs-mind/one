"""Runs a script in the Sandbox: one host child process per run, one run at a time.

The job goes to the child's stdin and the result comes back on its stdout, both in memory; no
file is written. The child is killed when the run is cancelled, when it outlives its time limit
by `GRACE` seconds, or when its stdout passes `output_max`. Its stdin stays open for the whole
run: when the core dies, the pipe closes and the child exits by itself.

The app holds one runner (`tools.services`), so every Brief shares its one-run-at-a-time lock.
Given `install`, `ready()` downloads the runtime the first time a run needs it, and a runtime
that turns out damaged is forgotten, so the next `ready()` downloads it again.
"""

import asyncio
import base64
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from qsone.sandbox import runtime

MiB = 1 << 20
TIMEOUT = 60
MAX_TIMEOUT = 600
MEMORY = 512 * MiB
OUTPUT_MAX = 90 * MiB  # 64 MB of outputs, in base64, plus the envelope
GRACE = 10  # seconds after the limit; covers the child's start and its first compile
STDERR_MAX = 1 * MiB


@dataclass(frozen=True)
class RunResult:
    exit: int | None  # the guest's exit status; None when it was stopped or crashed
    result: object
    outputs: dict[str, bytes] = field(default_factory=dict)
    printed: str = ""
    error: str | None = None  # the script's traceback (its last lines), or what stopped it
    timed_out: bool = False
    memory_exceeded: bool = False
    seconds: str = "0.000"  # wall time of the guest, as exact text


class _TooBig(Exception):
    pass


async def _read(stream: asyncio.StreamReader, limit: int) -> bytes:
    parts, size = [], 0
    while chunk := await stream.read(1 << 16):
        size += len(chunk)
        if size > limit:
            raise _TooBig
        parts.append(chunk)
    return b"".join(parts)


def _report(stderr: bytes) -> dict:
    for line in reversed(stderr.decode("utf-8", "replace").splitlines()):
        try:
            report = json.loads(line).get("host")
        except (ValueError, AttributeError):
            continue
        if isinstance(report, dict):
            return report
    return {}


class SandboxRunner:
    def __init__(
        self,
        runtime_dir: Path,
        *,
        output_max: int = OUTPUT_MAX,
        command: Sequence[str] = (sys.executable, "-I", "-m", "qsone.sandbox.host"),
        install: Callable[[], Path] | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.output_max = output_max
        self.command = tuple(command)
        self.install = install  # puts the runtime in `runtime_dir` (`runtime.ensure`), or None
        self.child: asyncio.subprocess.Process | None = None  # the run in progress
        self._one = asyncio.Semaphore(1)  # one run at a time (a 14 GB machine)
        self._installing = asyncio.Lock()

    async def ready(self) -> None:
        """Returns once the runtime is in place, downloading it first when it is missing.
        Raises `meaning.download.DownloadError` (the Sandbox's own words in `.text`)."""
        if self.install is not None:
            async with self._installing:
                await asyncio.to_thread(self.install)

    async def run(
        self,
        script: str,
        inputs: Mapping[str, bytes],
        params: Mapping,
        *,
        timeout: float = TIMEOUT,
        memory: int = MEMORY,
        clock: int | None = None,
    ) -> RunResult:
        """`clock` (seconds since 1970) fixes the time saved inside zip and xlsx outputs; a
        re-run given the first run's clock gives the same bytes."""
        timeout = min(max(timeout, 1), MAX_TIMEOUT)
        job = json.dumps(
            {
                "script": script,
                "inputs": {name: base64.b64encode(data).decode() for name, data in inputs.items()},
                "params": dict(params),
            },
            ensure_ascii=False,
        ).encode()
        header = {
            "runtime": str(self.runtime_dir),
            "timeout": timeout,
            "memory": memory,
            "output_max": self.output_max,
            "size": len(job),
            "clock": clock,
        }
        async with self._one:
            child = self.child = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                child.stdin.write(json.dumps(header).encode() + b"\n")
                child.stdin.write(job)
                del job
                await child.stdin.drain()
                out, err = await asyncio.wait_for(
                    asyncio.gather(
                        _read(child.stdout, self.output_max), _read(child.stderr, STDERR_MAX)
                    ),
                    timeout + GRACE,
                )
                await child.wait()
            except (TimeoutError, _TooBig, ConnectionError) as problem:
                child.kill()
                await child.wait()
                if isinstance(problem, TimeoutError):
                    return RunResult(None, None, error="timeout", timed_out=True)
                if isinstance(problem, _TooBig):
                    return RunResult(None, None, error="output too large")
                return RunResult(None, None, error="the Sandbox stopped unexpectedly")
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
                child.stdin.close()
                self.child = None
        result = _result(out, _report(err))
        if self.install is not None and (result.error or "").startswith("runtime:"):
            (self.runtime_dir / runtime.STAMP).unlink(missing_ok=True)  # download it again
        return result


def _result(out: bytes, host: dict) -> RunResult:
    try:
        envelope = json.loads(out) if out else {}
    except ValueError:
        envelope = {}
    if not isinstance(envelope, dict):
        envelope = {}
    error = envelope.get("error")
    if host.get("output") == "too_big":
        error = "output too large"
    elif not envelope:
        error = host.get("trap") or host.get("error") or host.get("stderr") or None
        if not error and not host.get("timeout"):
            error = "the Sandbox stopped unexpectedly"
    last = error.strip().splitlines()[-1] if error and error.strip() else ""
    return RunResult(
        exit=host.get("exit"),
        result=envelope.get("result"),
        outputs={n: base64.b64decode(d) for n, d in (envelope.get("outputs") or {}).items()},
        printed=envelope.get("printed") or "",
        error=error,
        timed_out=bool(host.get("timeout")),
        memory_exceeded=bool(host.get("memory")) or last.startswith("MemoryError"),
        seconds=host.get("seconds") or "0.000",
    )
