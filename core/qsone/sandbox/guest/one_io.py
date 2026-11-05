"""The Sandbox's side of a run, inside CPython on WASI. Never imported by the core.

The host starts the guest as `python -c <this file> <pyzlib.py>`. Its stdin holds the job,
`{"script", "inputs": {name: base64}, "params"}`, and its stdout gets one envelope,
`{"result", "outputs": {name: base64}, "printed", "error"}`. It exits 1 when the script failed.

A script uses `one_io` without importing it:
- `one_io.inputs`: `{name: bytes}`; `one_io.open_input(name)` gives a `BytesIO`;
- `one_io.params`: the job's parameters;
- `one_io.save(name, data)`: an output file (64 MB in all);
- `one_io.result(obj)`: the answer, anything JSON can hold.
`print` goes to a 64 KB buffer. There is no network and no folder to write in.
"""

import base64
import io
import json
import linecache
import sys
import traceback

PRINTED_MAX = 64 * 1024
OUTPUTS_MAX = 64 * 1024 * 1024
CUT = "\n[cut at 64 KB]"

inputs: dict[str, bytes] = {}
params: dict = {}
_outputs: dict[str, bytes] = {}
_result = None


def open_input(name: str) -> io.BytesIO:
    return io.BytesIO(inputs[name])


def save(name: str, data: bytes) -> None:
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("an output needs a file name of 1 to 200 characters")
    if "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("an output name is a file name, not a path")
    data = bytes(data)
    if sum(len(d) for n, d in _outputs.items() if n != name) + len(data) > OUTPUTS_MAX:
        raise ValueError("the outputs are larger than 64 MB in all")
    _outputs[name] = data


def result(obj) -> None:
    global _result
    json.dumps(obj)  # TypeError now, at the script's own line, rather than at the end
    _result = obj


class _Printed(io.TextIOBase):
    """What the script prints: the first 64 KB (UTF-8), then a cut mark."""

    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0
        self.cut = False

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not self.cut:
            room = PRINTED_MAX - len(CUT.encode()) - self.size
            encoded = text.encode("utf-8", "replace")
            if len(encoded) > room:
                text = encoded[:room].decode("utf-8", "ignore")
                self.cut = True
            self.parts.append(text)
            self.size += len(text.encode("utf-8", "replace"))
        return len(text)

    def value(self) -> str:
        return "".join(self.parts) + (CUT if self.cut else "")


def _tail(text: str, lines: int = 40, size: int = 8 * 1024) -> str:
    return "\n".join(text.rstrip("\n").splitlines()[-lines:])[-size:]


def _no_mmap(*args, **kwargs):
    raise OSError("the Sandbox has no mmap: open files from bytes")


def _openpyxl_in_memory(excel) -> None:
    """openpyxl 3.1 writes each sheet to a temporary file, and the guest has no folder to write
    in: each sheet goes to a BytesIO, and zipfile takes a BytesIO where it expects a file.

    With `SOURCE_DATE_EPOCH` set (a re-run), the saved workbook's "modified" time is that
    moment, as zipfile already does for its own times, so the same run gives the same bytes."""
    import datetime
    import os
    import types
    import zipfile

    if epoch := os.environ.get("SOURCE_DATE_EPOCH"):
        moment = datetime.datetime.fromtimestamp(int(epoch), datetime.UTC)
        clock = types.SimpleNamespace(now=lambda tz=None: moment)
        excel.datetime = types.SimpleNamespace(datetime=clock, timezone=datetime.timezone)

    writer = sys.modules["openpyxl.worksheet._writer"]
    writer.create_temporary_file = lambda suffix="": io.BytesIO()
    writer.WorksheetWriter.cleanup = lambda self: None
    write = zipfile.ZipFile.write

    def write_bytes(self, filename, arcname=None, compress_type=None, compresslevel=None):
        if isinstance(filename, io.BytesIO):
            return self.writestr(arcname, filename.getvalue(), compress_type, compresslevel)
        return write(self, filename, arcname, compress_type, compresslevel)

    zipfile.ZipFile.write = write_bytes


class _AfterImport:
    """Runs `patch(module)` right after `name` is first imported, so scripts that do not use
    openpyxl never pay for loading it."""

    def __init__(self, name: str, patch) -> None:
        self.name, self.patch = name, patch

    def find_spec(self, name, path, target=None):
        if name != self.name:
            return None
        from importlib.machinery import PathFinder

        spec = PathFinder.find_spec(name, path)
        if spec is not None and spec.loader is not None:
            run, patch = spec.loader.exec_module, self.patch

            def exec_module(module):
                run(module)
                patch(module)

            spec.loader.exec_module = exec_module
        return spec


def _stand_ins() -> None:
    """What the WASI build of CPython lacks, so openpyxl and xlrd work as they do outside."""
    import types

    try:
        import zlib  # noqa: F401
    except ImportError:  # xlsx parts are deflated: the pure-Python zlib stands in
        module = types.ModuleType("zlib")
        exec(compile(sys.argv[1], "pyzlib.py", "exec"), module.__dict__)
        sys.modules["zlib"] = module
    try:
        import mmap  # noqa: F401
    except ImportError:  # xlrd imports it, and uses it only for files opened by name
        module = types.ModuleType("mmap")
        module.ACCESS_READ, module.mmap = 1, _no_mmap
        sys.modules["mmap"] = module
    sys.meta_path.insert(0, _AfterImport("openpyxl.writer.excel", _openpyxl_in_memory))


def main() -> None:
    sys.modules["one_io"] = sys.modules[__name__]  # `import one_io` in a script finds this
    _stand_ins()
    job = json.loads(sys.stdin.buffer.read())
    inputs.update({name: base64.b64decode(data) for name, data in job["inputs"].items()})
    params.update(job.get("params") or {})
    script = job["script"]
    linecache.cache["script.py"] = (len(script), None, script.splitlines(True), "script.py")
    printed, error = _Printed(), None
    sys.stdout = printed
    try:
        code = compile(script, "script.py", "exec")
        exec(code, {"__name__": "__main__", "one_io": sys.modules["one_io"]})
    except SystemExit as stop:
        if stop.code not in (None, 0):
            error = f"SystemExit: {stop.code}"
    except BaseException as problem:  # noqa: BLE001 - every failure goes back as text
        frames = problem.__traceback__.tb_next if problem.__traceback__ else None
        error = _tail("".join(traceback.format_exception(type(problem), problem, frames)))
    finally:
        sys.stdout = sys.__stdout__
    envelope = {
        "result": _result,
        "outputs": {n: base64.b64encode(d).decode() for n, d in _outputs.items()},
        "printed": printed.value(),
        "error": error,
    }
    try:
        text = json.dumps(envelope, ensure_ascii=False)
    except (TypeError, ValueError):  # the result was changed after `result()` into a non-JSON
        error = error or "TypeError: the result is not something JSON can hold"
        text = json.dumps(envelope | {"result": None, "error": error}, ensure_ascii=False)
    sys.stdout.buffer.write(text.encode())
    sys.stdout.buffer.flush()
    sys.exit(1 if error else 0)


if __name__ == "__main__":
    main()
