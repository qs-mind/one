"""The Sandbox runtime: CPython on WASI under wasmtime, in a child process, in memory.

Four groups:
- `pyzlib`, the guest's zlib, checked against the real zlib on this computer;
- the download and unpacking, against a fake server (no socket);
- the host and the runner with tiny hand-written WebAssembly guests, so the limits (time, memory,
  output, a closed core) are tested on every system without the 16 MB runtime;
- the real runtime: opt-in, skipped unless `QSONE_SANDBOX_DIR` points at a folder where
  `python -m qsone.sandbox.runtime --dir <folder>` has installed it. CI never downloads it.
"""

import asyncio
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib
from pathlib import Path
from threading import Event

import httpx
import openpyxl
import pytest
import wasmtime

from qsone.meaning.download import DownloadError
from qsone.sandbox import runtime
from qsone.sandbox.guest import pyzlib
from qsone.sandbox.runner import SandboxRunner
from tests.samples import sample_xls, sample_xlsx

XML = "".join(f'<c r="A{i}" t="s"><v>{i % 97}</v></c>' for i in range(20_000)).encode()


# ---------------------------------------------------------------------------------------------
# pyzlib: the guest's zlib
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("level", [0, 1, 6, 9])
@pytest.mark.parametrize("wbits", [-15, 15, 31])
def test_pyzlib_inflates_what_zlib_deflates(level, wbits):
    for data in (b"", b"a", os.urandom(70_000), XML, "خرسانة مسلحة ".encode() * 3000):
        c = zlib.compressobj(level, zlib.DEFLATED, wbits)
        packed = c.compress(data) + c.flush()
        assert pyzlib.decompress(packed, wbits) == data
        d = pyzlib.decompressobj(wbits)
        out = b"".join(d.decompress(packed[i : i + 4096]) for i in range(0, len(packed), 4096))
        assert out + d.flush() == data and d.eof


@pytest.mark.parametrize("wbits", [-15, 15, 31])
def test_zlib_inflates_what_pyzlib_deflates(wbits):
    for data in (b"", XML, os.urandom(200_000)):
        c = pyzlib.compressobj(pyzlib.Z_DEFAULT_COMPRESSION, pyzlib.DEFLATED, wbits)
        assert zlib.decompress(c.compress(data) + c.flush(), wbits) == data
        assert zlib.decompress(pyzlib.compress(data, wbits=wbits), wbits) == data


def test_pyzlib_checks_and_leftovers():
    packed = zlib.compress(XML)
    d = pyzlib.decompressobj(47)  # zlib or gzip, by the header
    assert d.decompress(packed + b"tail") == XML and d.unused_data == b"tail"
    with pytest.raises(pyzlib.error, match="truncated"):
        pyzlib.decompress(packed[:-10])
    with pytest.raises(pyzlib.error):
        pyzlib.decompress(packed[:-1] + bytes([packed[-1] ^ 1]))  # the Adler-32 is wrong
    with pytest.raises(pyzlib.error):
        pyzlib.decompress(b"\x78\x9c" + bytes(50))
    for value in (1, 12345):
        assert pyzlib.adler32(XML, value) == zlib.adler32(XML, value)
    assert pyzlib.crc32(XML) == zlib.crc32(XML)


def test_openpyxl_reads_and_writes_through_pyzlib(monkeypatch):
    """zipfile finds zlib by its module global, so this is what the guest sees."""
    monkeypatch.setattr(zipfile, "zlib", pyzlib)
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف - عينة", "م3", 120]]})
    wb = openpyxl.load_workbook(io.BytesIO(data))
    wb["BOQ"]["E1"] = "checked"
    out = io.BytesIO()
    wb.save(out)
    monkeypatch.undo()
    again = openpyxl.load_workbook(io.BytesIO(out.getvalue()))["BOQ"]
    assert again["B1"].value == "خرسانة مسلحة للأسقف - عينة" and again["E1"].value == "checked"
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as z:
        assert z.testzip() is None


# ---------------------------------------------------------------------------------------------
# Download and unpacking
# ---------------------------------------------------------------------------------------------


def _zip(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return out.getvalue()


def _pin(name: str, data: bytes) -> runtime.RuntimeFile:
    return runtime.RuntimeFile(
        name, f"https://sample.invalid/{name}", len(data), hashlib.sha256(data).hexdigest()
    )


@pytest.fixture
def served():
    """A sample CPython zip and one wheel, pinned, and a transport that serves them."""
    wasm = wasmtime.wat2wasm(ECHO)
    python = _zip({"LICENSE": b"sample", "python.wasm": wasm, "lib/python3.15/os.py": b"# sample"})
    wheel = _zip({"openpyxl/__init__.py": b"# sample", "openpyxl-0.dist-info/RECORD": b""})
    files = (
        _pin("python-sample-wasi.zip", python),
        _pin("openpyxl-sample-py3-none-any.whl", wheel),
    )
    bodies = {f.url: d for f, d in zip(files, (python, wheel), strict=True)}
    requests: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, content=bodies[str(request.url)])

    return files, httpx.Client(transport=httpx.MockTransport(answer)), requests, bodies


def test_install_unpacks_once_and_find_sees_it(tmp_path, served):
    files, client, requests, _ = served
    assert runtime.find(tmp_path) is None
    folder = runtime.install(tmp_path, client=client, stop=Event(), files=files)
    assert runtime.find(tmp_path) == folder
    assert (folder / "python.wasm").is_file()
    assert (folder / "lib" / "python3.15" / "os.py").is_file()
    assert (folder / "lib" / "python3.15" / "site-packages" / "openpyxl" / "__init__.py").is_file()
    assert len(requests) == 2
    assert not any(p.suffix in (".zip", ".whl") for p in tmp_path.rglob("*"))  # archives gone
    assert runtime.install(tmp_path, client=client, stop=Event(), files=files) == folder
    assert len(requests) == 2  # already there: nothing fetched


def test_a_damaged_download_is_never_unpacked(tmp_path, served):
    files, client, _, bodies = served
    bodies[files[0].url] = bodies[files[0].url][:-1] + b"!"
    with pytest.raises(DownloadError):
        runtime.install(tmp_path, client=client, stop=Event(), files=files)
    assert runtime.find(tmp_path) is None


def test_the_pins_are_exact():
    for f in runtime.FILES:
        assert f.url.startswith("https://") and len(f.sha256) == 64 and f.size > 0
        assert f.url.rsplit("/", 1)[1] == f.name
    assert runtime.FILES[0].name.startswith(f"python-{runtime.PYTHON_VERSION}-")


def test_the_folder_follows_the_data_folder(data_dir, monkeypatch):
    monkeypatch.delenv("QSONE_SANDBOX_DIR", raising=False)
    assert runtime.root() == data_dir / "sandbox"
    monkeypatch.setenv("QSONE_SANDBOX_DIR", str(data_dir / "elsewhere"))
    assert runtime.root() == data_dir / "elsewhere"


# ---------------------------------------------------------------------------------------------
# Host and runner, with tiny WebAssembly guests (no CPython needed)
# ---------------------------------------------------------------------------------------------

_WASI = """
  (import "wasi_snapshot_preview1" "fd_read" (func $read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write" (func $write (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 2)
"""

# Copies stdin to stdout, then exits 0. iovec at 0, counts at 8, the buffer at 1024.
ECHO = f"""(module {_WASI}
  (func (export "_start")
    (block $done (loop $more
      (i32.store (i32.const 0) (i32.const 1024))
      (i32.store (i32.const 4) (i32.const 60000))
      (drop (call $read (i32.const 0) (i32.const 0) (i32.const 1) (i32.const 8)))
      (br_if $done (i32.eqz (i32.load (i32.const 8))))
      (i32.store (i32.const 4) (i32.load (i32.const 8)))
      (drop (call $write (i32.const 1) (i32.const 0) (i32.const 1) (i32.const 12)))
      (br $more)))
    (call $exit (i32.const 0))))"""

SPIN = f"""(module {_WASI} (func (export "_start") (loop $l (br $l))))"""

GROW = f"""(module {_WASI}
  (func (export "_start")
    (loop $l (br_if $l (i32.ne (memory.grow (i32.const 16)) (i32.const -1))))
    (call $exit (i32.const 7))))"""

SPAM = f"""(module {_WASI}
  (func (export "_start")
    (i32.store (i32.const 0) (i32.const 1024))
    (i32.store (i32.const 4) (i32.const 60000))
    (loop $l (drop (call $write (i32.const 1) (i32.const 0) (i32.const 1) (i32.const 12)))
      (br $l))))"""


def fake_runtime(folder: Path, wat: str) -> Path:
    (folder / "lib").mkdir(parents=True)
    (folder / "python.wasm").write_bytes(wasmtime.wat2wasm(wat))
    return folder


def start_host(folder: Path, job: bytes, *, timeout=30, memory=64 << 20, output_max=1 << 20):
    header = {"runtime": str(folder), "timeout": timeout, "memory": memory,
              "output_max": output_max, "size": len(job)}  # fmt: skip
    host = subprocess.Popen(
        [sys.executable, "-I", "-m", "qsone.sandbox.host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    host.stdin.write(json.dumps(header).encode() + b"\n" + job)
    host.stdin.flush()
    return host


def host_line(stderr: bytes) -> dict:
    return json.loads(stderr.decode().strip().splitlines()[-1])["host"]


def test_host_gives_the_guest_its_job_and_returns_its_stdout(tmp_path):
    job = json.dumps({"script": "عينة", "inputs": {}, "params": {}}).encode()
    host = start_host(fake_runtime(tmp_path / "rt", ECHO), job)
    out, err = host.stdout.read(), host.stderr.read()  # stdin stays open, as the runner does
    host.stdin.close()
    host.wait(timeout=10)
    assert out == job
    line = host_line(err)
    assert line["exit"] == 0 and not line["timeout"] and not line["memory"]
    assert (tmp_path / "rt" / "python.cwasm").is_file()  # compiled once, for the next runs


def test_host_stops_when_its_stdin_closes(tmp_path):
    """The core went away: no Sandbox process is left behind."""
    host = start_host(fake_runtime(tmp_path / "rt", SPIN), b"{}", timeout=120)
    time.sleep(1)
    assert host.poll() is None
    started = time.monotonic()
    host.stdin.close()
    host.wait(timeout=10)
    assert time.monotonic() - started < 5
    host.stdout.close()
    host.stderr.close()


async def test_runner_stops_an_endless_loop(tmp_path):
    runner = SandboxRunner(fake_runtime(tmp_path / "rt", SPIN))
    started = time.monotonic()
    r = await runner.run("while True: pass", {}, {}, timeout=1)
    assert r.timed_out and r.exit is None and time.monotonic() - started < 8
    assert not r.memory_exceeded


async def test_runner_reports_the_memory_limit(tmp_path):
    runner = SandboxRunner(fake_runtime(tmp_path / "rt", GROW))
    r = await runner.run("x = bytearray(2**30)", {}, {}, memory=32 << 20)
    assert r.memory_exceeded and r.exit == 7 and not r.timed_out


async def test_runner_stops_endless_output(tmp_path):
    runner = SandboxRunner(fake_runtime(tmp_path / "rt", SPAM), output_max=1 << 20)
    r = await runner.run("print('x' * 10**9)", {}, {}, timeout=30)
    assert r.error == "output too large" and r.outputs == {} and r.seconds


async def test_runner_runs_one_at_a_time(tmp_path):
    runner = SandboxRunner(fake_runtime(tmp_path / "rt", SPIN))
    ended = []

    async def one():
        await runner.run("", {}, {}, timeout=1)
        ended.append(time.monotonic())

    await asyncio.gather(one(), one())
    assert ended[1] - ended[0] >= 0.9  # the second waited for the first


async def test_a_cancelled_run_leaves_no_child(tmp_path):
    runner = SandboxRunner(fake_runtime(tmp_path / "rt", SPIN))
    task = asyncio.ensure_future(runner.run("", {}, {}, timeout=120))
    await asyncio.sleep(1.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runner.child is None


async def test_a_damaged_runtime_is_a_plain_failure(tmp_path):
    (tmp_path / "rt" / "lib").mkdir(parents=True)  # no python.wasm
    r = await SandboxRunner(tmp_path / "rt").run("one_io.result(1)", {}, {})
    assert r.exit is None and r.error == "runtime: FileNotFoundError" and r.result is None


# ---------------------------------------------------------------------------------------------
# The real runtime (opt-in)
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def real_runtime() -> Path:
    base = os.environ.get("QSONE_SANDBOX_DIR")
    found = runtime.find(Path(base)) if base else None
    if found is None:
        pytest.skip("the Sandbox runtime is not installed: set QSONE_SANDBOX_DIR (see module doc)")
    return found


@pytest.fixture
def runner(real_runtime) -> SandboxRunner:
    return SandboxRunner(real_runtime)


async def test_hello_and_exact_decimal(runner):
    r = await runner.run(
        "from decimal import Decimal as D\none_io.result(str(D('39850.50') * 3))", {}, {}
    )
    assert r.exit == 0 and r.result == "119551.50" and r.error is None


async def test_arabic_round_trip(runner):
    r = await runner.run(
        "one_io.result(one_io.inputs['n'].decode() + ' ✓')", {"n": "خرسانة مسلحة".encode()}, {}
    )
    assert r.result == "خرسانة مسلحة ✓"


async def test_openpyxl_reads_and_writes_in_memory(runner):
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة للأسقف", "م3", 120]]})
    script = (
        "import openpyxl, io\nwb = openpyxl.load_workbook(one_io.open_input('boq.xlsx'))\n"
        "ws = wb['BOQ']; ws['E1'] = 'checked'\nb = io.BytesIO(); wb.save(b)\n"
        "one_io.save('out.xlsx', b.getvalue())\n"
        "one_io.result(ws['B1'].value)"
    )
    r = await runner.run(script, {"boq.xlsx": data}, {})
    assert r.result == "خرسانة مسلحة للأسقف", r.error
    assert openpyxl.load_workbook(io.BytesIO(r.outputs["out.xlsx"]))["BOQ"]["E1"].value == "checked"


async def test_a_rerun_with_the_same_clock_gives_the_same_bytes(runner):
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة - عينة", "م3", 120]]})
    script = (
        "import openpyxl, io\nwb = openpyxl.load_workbook(one_io.open_input('boq.xlsx'))\n"
        "b = io.BytesIO(); wb.save(b); one_io.save('out.xlsx', b.getvalue())"
    )
    first = await runner.run(script, {"boq.xlsx": data}, {}, clock=1_762_329_600)
    await asyncio.sleep(1.1)  # a second later: the real clock would show in the bytes
    again = await runner.run(script, {"boq.xlsx": data}, {}, clock=1_762_329_600)
    assert first.outputs["out.xlsx"] == again.outputs["out.xlsx"], first.error
    saved = openpyxl.load_workbook(io.BytesIO(first.outputs["out.xlsx"])).properties.modified
    assert saved.isoformat() == "2025-11-05T08:00:00"


async def test_xlrd_reads_an_old_excel_file(runner):
    data = sample_xls({"BOQ": [["03/02", "خرسانة - عينة", "م3", 120]]})
    script = (
        "import xlrd\nbook = xlrd.open_workbook(file_contents=one_io.inputs['boq.xls'])\n"
        "one_io.result(book.sheet_by_name('BOQ').cell_value(0, 1))"
    )
    r = await runner.run(script, {"boq.xls": data}, {})
    assert r.result == "خرسانة - عينة", r.error


async def test_params_and_a_script_error(runner):
    r = await runner.run("x = one_io.params['n']\n\n1 / x", {}, {"n": 0})
    assert r.exit == 1 and "script.py" in r.error and "line 3" in r.error
    assert "ZeroDivisionError" in r.error.splitlines()[-1]


async def test_no_network(runner):
    script = (
        "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
        "    one_io.result('connected')\n"
        "except Exception as e:\n    one_io.result(type(e).__name__)"
    )
    r = await runner.run(script, {}, {})
    assert r.exit == 0 and r.result not in (None, "connected")


async def test_sees_only_lib_read_only(runner):
    script = """
import os
seen = {}
def attempt(name, f):
    try:
        f()
        seen[name] = "allowed"
    except Exception as e:
        seen[name] = type(e).__name__
attempt("list root", lambda: seen.setdefault("root", os.listdir("/")))
attempt("passwd", lambda: open("/etc/passwd").read())
attempt("write lib", lambda: open("/lib/x", "w").write("x"))
attempt("write tmp", lambda: open("/tmp/x", "w").write("x"))
attempt("mkdir", lambda: os.mkdir("/lib/d"))
seen["lib"] = os.listdir("/lib")
one_io.result(seen)
"""
    r = await runner.run(script, {}, {})
    seen = r.result
    assert seen["root"] == ["lib"] if seen["list root"] == "allowed" else True
    for name in ("passwd", "write lib", "write tmp", "mkdir"):
        assert seen[name] != "allowed", name
    assert seen["lib"] == [f"python{runtime.PYTHON_VERSION.rsplit('.', 1)[0]}"]


async def test_endless_loop_stops(runner):
    started = time.monotonic()
    r = await runner.run("while True: pass", {}, {}, timeout=2)
    assert r.timed_out and time.monotonic() - started < 8


async def test_memory_bomb_stops(runner):
    r = await runner.run("x = bytearray(2**30)", {}, {})
    assert r.memory_exceeded and "MemoryError" in r.error
    r = await runner.run("x = []\nwhile True: x.append(bytearray(10**6))", {}, {}, timeout=60)
    assert r.memory_exceeded and not r.timed_out


async def test_printed_text_is_capped(runner):
    r = await runner.run("for i in range(20000): print('سطر', i, 'x' * 40)", {}, {})
    assert len(r.printed.encode()) <= 64 * 1024 and r.printed.endswith("[cut at 64 KB]")
    assert r.printed.startswith("سطر 0 ")


def _snapshot(*folders: Path) -> dict:
    return {
        str(p): p.stat().st_size
        for folder in folders
        for p in sorted(folder.rglob("*"))
        if p.name != "python.cwasm"  # the compiled code: code, not content
    }


async def test_nothing_written_to_disk(runner, real_runtime, data_dir, tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    temp.mkdir()
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in ("TMPDIR", "TEMP", "TMP"):
        monkeypatch.setenv(name, str(temp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    await runner.run("one_io.result(1)", {}, {})  # the compiled code is in place first
    before = _snapshot(temp, data_dir, real_runtime)
    data = sample_xlsx({"BOQ": [["03/02", "خرسانة مسلحة - عينة", "م3", 120]]})
    script = (
        "import openpyxl, io\nwb = openpyxl.load_workbook(one_io.open_input('boq.xlsx'))\n"
        "b = io.BytesIO(); wb.save(b); one_io.save('نتيجة.xlsx', b.getvalue())"
    )
    r = await runner.run(script, {"boq.xlsx": data}, {})
    assert r.exit == 0 and "نتيجة.xlsx" in r.outputs, r.error
    assert _snapshot(temp, data_dir, real_runtime) == before
