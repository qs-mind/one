"""The Sandbox's Python: CPython built for WASI (wasm32-wasip1), downloaded once, when first needed.

The build is Brett Cannon's (github.com/brettcannon/cpython-wasi-build): the CPython core
developer who looks after WASI support builds every CPython release with the WASI SDK, using
CPython's own `Tools/wasm` script. CPython is PSF-2.0, the build scripts MIT. There is no
python.org build for WASI. The guest packages are PyPI's own wheels: openpyxl and et_xmlfile
(MIT), xlrd (BSD-3-Clause). These builds have no zlib, so the guest brings its own
(`guest/pyzlib.py`).

Every file is pinned by URL, size and SHA-256 and fetched with the search models' download
(`meaning.download`: resumable, checked, never at import) into `<data>/sandbox/`. It is then
unpacked once into `<data>/sandbox/cpython-wasi/<version>/runtime/`, and the archives are
deleted. Sizes: about 16 MB to download, 46 MB unpacked, plus about 19 MB of compiled code
that the host writes on its first run.
"""

import argparse
import json
import os
import shutil
import sys
import threading
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from qsone import copy, settings
from qsone.meaning import download as fetch
from qsone.meaning.manifest import ModelFile

PYTHON_VERSION = "3.15.2"
VERSION = f"{PYTHON_VERSION}-1"  # the last part counts changes to the guest packages
LIB = "python3.15"
STAMP = "unpacked.json"


@dataclass(frozen=True)
class RuntimeFile:
    name: str
    url: str
    size: int
    sha256: str


_GITHUB = "https://github.com/brettcannon/cpython-wasi-build/releases/download"
_PYPI = "https://files.pythonhosted.org/packages"

# The first file is CPython; the rest are wheels unpacked into its site-packages.
FILES = (
    RuntimeFile(
        "python-3.15.2-wasi_sdk-33.zip",
        f"{_GITHUB}/v3.15.2/python-3.15.2-wasi_sdk-33.zip",
        15_528_008,
        "b8a63559c56760bbdc310dedb74fd69d10bcbafae26b705bea0ad353ad256888",
    ),
    RuntimeFile(
        "openpyxl-3.1.5-py2.py3-none-any.whl",
        f"{_PYPI}/c0/da/977ded879c29cbd04de313843e76868e6e13408a94ed6b987245dc7c8506/"
        "openpyxl-3.1.5-py2.py3-none-any.whl",
        250_910,
        "5282c12b107bffeef825f4617dc029afaf41d0ea60823bbb665ef3079dc79de2",
    ),
    RuntimeFile(
        "et_xmlfile-2.0.0-py3-none-any.whl",
        f"{_PYPI}/c1/8b/5fe2cc11fee489817272089c4203e679c63b570a5aaeb18d852ae3cbba6a/"
        "et_xmlfile-2.0.0-py3-none-any.whl",
        18_059,
        "7a91720bc756843502c3b7504c77b8fe44217c85c537d85037f0f536151b2caa",
    ),
    RuntimeFile(
        "xlrd-2.0.2-py2.py3-none-any.whl",
        f"{_PYPI}/1a/62/c8d562e7766786ba6587d09c5a8ba9f718ed3fa8af7f4553e8f91c36f302/"
        "xlrd-2.0.2-py2.py3-none-any.whl",
        96_555,
        "ea762c3d29f4cca48d82df517b6d89fbce4db3107f9d78713e48cd321d5c9aa9",
    ),
)


# The search models' download words, said for the Sandbox's Python instead.
_OURS = ((copy.MEANING_DOWNLOAD_FAILED, copy.SANDBOX_DOWNLOAD_FAILED),)


@dataclass(frozen=True)
class _Spec:
    """What `meaning.download` needs to know about a set of files."""

    files: tuple[ModelFile, ...]
    urls: dict[str, str]
    id: str = "cpython-wasi"
    revision: str = VERSION

    def url(self, f: ModelFile) -> str:
        return self.urls[f.path]

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


def _spec(files: Sequence[RuntimeFile]) -> _Spec:
    return _Spec(
        tuple(ModelFile(f.name, f.size, f.sha256) for f in files), {f.name: f.url for f in files}
    )


def root() -> Path:
    """`<data>/sandbox`; `QSONE_SANDBOX_DIR` points elsewhere (the opt-in tests' cached copy)."""
    override = os.environ.get("QSONE_SANDBOX_DIR")
    return Path(override) if override else settings.data_dir() / "sandbox"


def _folder(base: Path) -> Path:
    return base / "cpython-wasi" / VERSION


def folder(base: Path | None = None) -> Path:
    """Where the unpacked runtime is, or will be once installed."""
    return _folder(base or root()) / "runtime"


def find(base: Path | None = None) -> Path | None:
    """The unpacked runtime (`python.wasm` and `lib/`), or None when it is not installed."""
    runtime = folder(base)
    try:
        stamp = json.loads((runtime / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ok = stamp == {"version": VERSION} and (runtime / "python.wasm").is_file()
    return runtime if ok else None


def _extract(archive: Path, into: Path) -> None:
    """zipfile drops absolute paths and `..` from member names, so nothing lands outside."""
    with zipfile.ZipFile(archive) as z:
        z.extractall(into)


def install(
    base: Path | None = None,
    *,
    client: httpx.Client,
    stop: threading.Event,
    on_progress: Callable[[int, int], None] = lambda done, total: None,
    files: Sequence[RuntimeFile] = FILES,
) -> Path:
    """Downloads what is missing, checks it, unpacks it; returns the runtime folder.

    Raises `meaning.download.DownloadError` (a `copy` pair in `.text`, the Sandbox's own
    words) or `DownloadStopped`."""
    base = base or root()
    if found := find(base):
        return found
    spec = _spec(files)
    try:
        fetch.download([spec], base, client=client, stop=stop, on_progress=on_progress)
    except fetch.NoSpace as e:
        raise fetch.DownloadError(copy.SANDBOX_NO_SPACE) from e
    except fetch.DownloadError as e:
        text = next((ours for theirs, ours in _OURS if e.text == theirs), e.text)
        raise fetch.DownloadError(text) from e
    folder = _folder(base)
    part = folder / "runtime.part"
    shutil.rmtree(part, ignore_errors=True)
    _extract(folder / files[0].name, part)
    site = part / "lib" / LIB / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for wheel in files[1:]:
        _extract(folder / wheel.name, site)
    (part / STAMP).write_text(json.dumps({"version": VERSION}), encoding="utf-8")
    runtime = folder / "runtime"
    shutil.rmtree(runtime, ignore_errors=True)
    os.replace(part, runtime)
    for f in files:  # unpacked and in place: the archives are no longer needed
        (folder / f.name).unlink(missing_ok=True)
    (folder / fetch.VERIFIED).unlink(missing_ok=True)
    return runtime


def ensure(base: Path | None = None) -> Path:
    """`install` with the download client, for the first run that needs the runtime: about
    16 MB, once; a stopped download resumes where it ended. Blocks: run it in a thread."""
    with fetch.default_client() as client:
        return install(base, client=client, stop=threading.Event())


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m qsone.sandbox.runtime [--dir FOLDER]` installs it by hand.

    `npm run sandbox:fetch` runs this."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", type=Path, help="the sandbox folder (default <data>/sandbox)")
    args = parser.parse_args(argv)

    def progress(done: int, total: int) -> None:
        print(f"\r{done / 1e6:.1f} / {total / 1e6:.1f} MB", end="", file=sys.stderr)

    with fetch.default_client() as client:
        folder = install(args.dir, client=client, stop=threading.Event(), on_progress=progress)
    print(f"\n{folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
