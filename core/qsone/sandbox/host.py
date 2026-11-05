"""The Sandbox host: a child process that runs one job in CPython on WASI under wasmtime.

The runner starts it as `python -I -m qsone.sandbox.host`. Everything travels over OS pipes and
stays in memory:
- stdin: one header line `{"runtime", "timeout", "memory", "output_max", "size", "clock"?}`,
  then `size` bytes of job, which become the guest's whole stdin;
- stdout: the guest's stdout (one JSON envelope), written once the guest has stopped, and only
  if it stayed within `output_max`;
- stderr: one line `{"host": {"exit", "timeout", "memory", "output", "seconds", "stderr"}}`.

The guest sees no host folder but the runtime's `lib/`, read-only, and has no sockets (WASI
preview 1 gives it none). `epoch_interruption` stops it at the time limit, `Store.set_limits`
caps its memory. The host exits as soon as its own stdin closes, so a core that went away
leaves no Sandbox behind. The compiled module is kept as `<runtime>/python.cwasm`: code, not
content.
"""

import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

import wasmtime
from wasmtime import _ffi as ffi  # stdin from bytes in memory: not wrapped by wasmtime-py

GUEST = Path(__file__).parent / "guest"
STDERR_MAX = 64 * 1024
MEMORY_NEAR = 2 << 20  # memory this close to the limit at a failure counts as the limit
ENV = [("PYTHONHASHSEED", "0"), ("PYTHONUTF8", "1"), ("PYTHONDONTWRITEBYTECODE", "1"),
       ("PYTHONSAFEPATH", "1")]  # fmt: skip


def _read_exactly(stream, size: int) -> bytes:
    parts, left = [], size
    while left:
        part = stream.read(left)
        if not part:
            raise EOFError("the job ended early")
        parts.append(part)
        left -= len(part)
    return b"".join(parts)


def _watch_stdin(stream) -> None:
    """Nothing more is sent after the job; the end of stdin means the core has gone."""
    while stream.read(1):
        pass
    os._exit(3)


def _module(engine: wasmtime.Engine, runtime: Path) -> wasmtime.Module:
    """Compiled once; wasmtime refuses a cached file from another version or setting."""
    cached = runtime / "python.cwasm"
    try:
        return wasmtime.Module.deserialize_file(engine, str(cached))
    except (OSError, wasmtime.WasmtimeError):
        pass
    module = wasmtime.Module.from_file(engine, str(runtime / "python.wasm"))
    temporary = cached.with_name(f"python.{os.getpid()}.cwasm.tmp")
    try:
        temporary.write_bytes(module.serialize())
        os.replace(temporary, cached)
    except OSError:
        temporary.unlink(missing_ok=True)  # a read-only install still runs, compiling each time
    return module


class _Capped:
    """A guest stream kept in memory up to `limit` bytes; `over` is called once beyond it."""

    def __init__(self, limit: int, over=None) -> None:
        self.limit, self.over = limit, over
        self.parts: list[bytes] = []
        self.size = 0
        self.overflowed = False

    def __call__(self, data: bytes) -> None:
        if self.size + len(data) > self.limit:
            self.parts.append(data[: max(0, self.limit - self.size)])
            self.size = self.limit
            if not self.overflowed:
                self.overflowed = True
                if self.over:
                    self.over()
            return None  # the guest's write still succeeds, so it never retries forever
        self.parts.append(data)
        self.size += len(data)
        return None

    def value(self) -> bytes:
        return b"".join(self.parts)


def run(header: dict, job: bytes) -> tuple[bytes | None, dict]:
    """Runs the job; returns the guest's stdout (None when it was too large) and the report."""
    runtime = Path(header["runtime"])
    config = wasmtime.Config()
    config.epoch_interruption = True
    engine = wasmtime.Engine(config)
    module = _module(engine, runtime)
    store = wasmtime.Store(engine)
    store.set_limits(memory_size=int(header["memory"]))
    store.set_epoch_deadline(1)
    stopped: list[str] = []

    def stop(why: str) -> None:
        if not stopped:
            stopped.append(why)
            engine.increment_epoch()

    stdout = _Capped(int(header["output_max"]), over=lambda: stop("output"))
    stderr = _Capped(STDERR_MAX)
    wasi = wasmtime.WasiConfig()
    wasi.argv = [
        "python",
        "-c",
        (GUEST / "one_io.py").read_text(encoding="utf-8"),
        (GUEST / "pyzlib.py").read_text(encoding="utf-8"),
    ]
    clock = header.get("clock")  # whole seconds since 1970: zipfile and openpyxl use it
    wasi.env = ENV + ([("SOURCE_DATE_EPOCH", str(int(clock)))] if clock is not None else [])
    wasi.preopen_dir(str(runtime / "lib"), "/lib", fs_mutable=False)
    vector = ffi.bytes_to_capi(job)
    ffi.wasi_config_set_stdin_bytes(wasi.ptr(), ctypes.byref(vector))  # wasmtime takes the bytes
    wasi.stdout_custom = stdout
    wasi.stderr_custom = stderr
    store.set_wasi(wasi)
    linker = wasmtime.Linker(engine)
    linker.define_wasi()
    instance = linker.instantiate(store, module)
    timer = threading.Timer(float(header["timeout"]), stop, ("timeout",))
    timer.daemon = True
    exit_code: int | None = None
    trap = None
    started = time.monotonic()
    timer.start()
    try:
        instance.exports(store)["_start"](store)
        exit_code = 0
    except wasmtime.ExitTrap as done:
        exit_code = done.code
    except (wasmtime.Trap, wasmtime.WasmtimeError) as problem:
        trap = str(problem).splitlines()[0][:300] if str(problem) else type(problem).__name__
    finally:
        timer.cancel()
    seconds = time.monotonic() - started
    memory = instance.exports(store)["memory"]
    near_limit = memory.data_len(store) + MEMORY_NEAR >= int(header["memory"])
    report = {
        "exit": exit_code,
        "timeout": stopped[:1] == ["timeout"],
        "memory": near_limit and exit_code != 0 and not stopped,
        "output": "too_big" if stdout.overflowed else "ok",
        "trap": None if stopped else trap,
        "seconds": f"{seconds:.3f}",
        "stderr": stderr.value()[-4096:].decode("utf-8", "replace"),
    }
    return (None if stdout.overflowed else stdout.value()), report


def main() -> None:
    stdin = sys.stdin.buffer
    try:
        header = json.loads(stdin.readline())
        job = _read_exactly(stdin, int(header["size"]))
    except (ValueError, KeyError, EOFError) as problem:
        sys.stderr.write(json.dumps({"host": {"error": f"bad job: {problem}"}}) + "\n")
        sys.stderr.flush()
        os._exit(2)
    threading.Thread(target=_watch_stdin, args=(stdin,), daemon=True).start()
    try:
        out, report = run(header, job)
    except (OSError, wasmtime.WasmtimeError) as problem:  # a damaged runtime: no traceback
        out, report = None, {"exit": None, "error": f"runtime: {type(problem).__name__}"}
    if out:
        sys.stdout.buffer.write(out)
        sys.stdout.buffer.flush()
    sys.stderr.write(json.dumps({"host": report}) + "\n")
    sys.stderr.flush()
    os._exit(0)  # skips wasmtime's teardown at exit, which can abort after a run


if __name__ == "__main__":
    main()
