"""BGE-M3 and its reranker on onnxruntime (CPU) with `tokenizers`, as the search spike ran them.

This is the only module that imports onnxruntime and tokenizers, and only the model loader
imports it, so the core starts without them.
"""

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from qsone.meaning.manifest import ModelSpec

MAX_TOKENS = 512
BATCH = 4
INPUTS = ("input_ids", "attention_mask", "token_type_ids")


def default_threads() -> int:
    """Half the cores, at most 4, so the screen keeps some."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def session_options(threads: int) -> ort.SessionOptions:
    o = ort.SessionOptions()
    o.intra_op_num_threads = threads
    o.inter_op_num_threads = 1
    o.enable_cpu_mem_arena = False
    return o


def _load(spec: ModelSpec, folder: Path, threads: int | None) -> tuple[Tokenizer, object]:
    tokenizer = folder / "tokenizer.json"
    model = folder / next(f.path for f in spec.files if f.path.endswith(".onnx"))
    for path in (tokenizer, model):
        if not path.is_file():
            raise FileNotFoundError(f"missing model file: {path}")
    session = ort.InferenceSession(
        str(model),
        session_options(threads or default_threads()),
        providers=["CPUExecutionProvider"],
    )
    return Tokenizer.from_file(str(tokenizer)), session


class _Model:
    output = ""

    def __init__(self, tokenizer: Tokenizer, session, *, name: str):
        pad = tokenizer.token_to_id("<pad>")
        if pad is None:
            raise RuntimeError("the tokenizer has no <pad> token")
        tokenizer.enable_padding(pad_id=pad, pad_token="<pad>")
        tokenizer.enable_truncation(MAX_TOKENS)
        self._inputs = [i.name for i in session.get_inputs()]
        unknown = [n for n in self._inputs if n not in INPUTS]
        if unknown:
            raise RuntimeError(f"the model asks for inputs this code does not give: {unknown}")
        outputs = [o.name for o in session.get_outputs()]
        self._output = self.output if self.output in outputs else outputs[0]
        self._tokenizer, self._session, self.name = tokenizer, session, name

    def _run(self, batch: list) -> np.ndarray:
        encs = self._tokenizer.encode_batch(batch)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        given = {
            "input_ids": ids,
            "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64),
            "token_type_ids": np.zeros_like(ids),
        }
        feed = {n: given[n] for n in self._inputs}
        return self._session.run([self._output], feed)[0]


class OnnxEmbedder(_Model):
    """search.Embedder: the CLS row, L2-normalised; no prefix for queries or documents."""

    output = "last_hidden_state"

    def __init__(self, tokenizer: Tokenizer, session, *, name: str, dims: int):
        super().__init__(tokenizer, session, name=name)
        self.dims = dims

    @classmethod
    def load(cls, spec: ModelSpec, folder: Path, threads: int | None = None) -> "OnnxEmbedder":
        tokenizer, session = _load(spec, folder, threads)
        return cls(tokenizer, session, name=spec.name, dims=spec.dims)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # less padding
        out: list[list[float]] = [[] for _ in texts]
        for start in range(0, len(order), BATCH):
            part = order[start : start + BATCH]
            cls_rows = self._run([texts[i] for i in part])[:, 0, :]
            norms = np.maximum(np.linalg.norm(cls_rows, axis=1, keepdims=True), 1e-12)
            for i, v in zip(part, cls_rows / norms, strict=True):
                out[i] = v.tolist()
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OnnxReranker(_Model):
    """search.Reranker: the raw logit of each (query, text) pair, in order."""

    output = "logits"

    @classmethod
    def load(cls, spec: ModelSpec, folder: Path, threads: int | None = None) -> "OnnxReranker":
        tokenizer, session = _load(spec, folder, threads)
        return cls(tokenizer, session, name=spec.name)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        scores: list[float] = []
        for start in range(0, len(texts), BATCH):
            pairs = [(query, t) for t in texts[start : start + BATCH]]
            scores += self._run(pairs).reshape(-1).tolist()
        return scores
