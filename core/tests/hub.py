"""A fake Hugging Face for the download tests: tiny sample models served through
`httpx.MockTransport`, with ranges and faults. Nothing here opens a socket."""

import hashlib
import re

import httpx

from qsone.meaning.manifest import EMBEDDER, RERANKER, ModelFile, ModelSpec

PIECE = 16 * 1024  # the fake network hands the body over in pieces this size


def _bytes(seed: str, size: int) -> bytes:
    """Deterministic sample bytes, starting with a line that says they are a sample."""
    head = f"عينة / sample: {seed}\n".encode()
    body = b"".join(hashlib.sha256(f"{seed}/{i}".encode()).digest() for i in range(size // 32 + 1))
    return (head + body)[:size]


def _spec(id, kind, sizes, dims, ram_bytes) -> tuple[ModelSpec, dict[str, bytes]]:
    paths = ("tokenizer.json", "onnx/model_int8.onnx")
    data = {p: _bytes(f"{id}/{p}", n) for p, n in zip(paths, sizes, strict=True)}
    files = tuple(ModelFile(p, len(b), hashlib.sha256(b).hexdigest()) for p, b in data.items())
    revision = hashlib.sha1(id.encode()).hexdigest()
    spec = ModelSpec(id, kind, f"qsmind-sample/{id}", revision, files, "MIT", dims, ram_bytes)
    return spec, data


def _samples() -> tuple[tuple[ModelSpec, ModelSpec], dict[str, bytes]]:
    embedder, e = _spec("sample-embedder", "embedder", (150_000, 300_000), 5, EMBEDDER.ram_bytes)
    reranker, r = _spec("sample-reranker", "reranker", (120_000, 250_000), None, RERANKER.ram_bytes)
    served = {s.url(f): d[f.path] for s, d in ((embedder, e), (reranker, r)) for f in s.files}
    return (embedder, reranker), served


def sample_specs() -> tuple[ModelSpec, ModelSpec]:
    """Two tiny specs: an embedder with `dims=5` (`ConceptEmbedder.dims`) and a reranker."""
    return _samples()[0]


class _Body(httpx.SyncByteStream):
    """The body in pieces; with `drop`, the connection breaks after that many bytes."""

    def __init__(self, data: bytes, drop: int | None = None) -> None:
        self.data, self.drop = data, drop

    def __iter__(self):
        end = len(self.data) if self.drop is None else min(self.drop, len(self.data))
        for start in range(0, end, PIECE):
            yield self.data[start : min(start + PIECE, end)]
        if self.drop is not None:
            raise httpx.ReadError("connection dropped (fake hub)")


class FakeHub:
    """Serves the sample files at their pinned URLs and records every request."""

    def __init__(self) -> None:
        self.specs, self.files = _samples()
        self.requests: list[httpx.Request] = []
        self.heal()

    def heal(self) -> None:
        """Clears every fault."""
        self._ignore_range = False
        self._drop: tuple[int, int] = (0, 0)  # (bytes, responses left)
        self._corrupt = False
        self._missing = False

    def ignore_range(self) -> None:
        self._ignore_range = True

    def drop_after(self, n: int, times: int = 1) -> None:
        """The next `times` responses break after `n` bytes of body."""
        self._drop = (n, times)

    def corrupt(self) -> None:
        """Every file is served with one byte changed."""
        self._corrupt = True

    def not_found(self) -> None:
        self._missing = True

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        data = self.files.get(str(request.url))
        if data is None or self._missing:
            return httpx.Response(404)
        if self._corrupt:
            data = data[:1000] + bytes([data[1000] ^ 0xFF]) + data[1001:]
        status, headers, start = 200, {}, 0
        asked = request.headers.get("range")
        if asked and not self._ignore_range:
            start = int(re.fullmatch(r"bytes=(\d+)-", asked)[1])
            if start >= len(data):
                return httpx.Response(416, headers={"Content-Range": f"bytes */{len(data)}"})
            status = 206
            headers["Content-Range"] = f"bytes {start}-{len(data) - 1}/{len(data)}"
        drop = None
        if self._drop[1] > 0:
            drop, self._drop = self._drop[0], (self._drop[0], self._drop[1] - 1)
        return httpx.Response(status, headers=headers, stream=_Body(data[start:], drop))
