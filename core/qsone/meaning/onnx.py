"""multilingual-e5-small on onnxruntime (CPU) with `tokenizers`, as its model card runs it.

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
OUTPUT = "last_hidden_state"
QUERY, PASSAGE = "query: ", "passage: "  # e5 is trained with these, in every language


def default_threads() -> int:
    """Half the cores, at most 4, so the screen keeps some."""
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def session_options(threads: int) -> ort.SessionOptions:
    o = ort.SessionOptions()
    o.intra_op_num_threads = threads
    o.inter_op_num_threads = 1
    o.enable_cpu_mem_arena = False
    return o


class OnnxEmbedder:
    """search.Embedder: "passage: " or "query: " first, then the mean of the token rows (padding
    left out), L2-normalised."""

    def __init__(self, tokenizer: Tokenizer, session, *, name: str, dims: int):
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
        self._output = OUTPUT if OUTPUT in outputs else outputs[0]
        self._tokenizer, self._session, self.name, self.dims = tokenizer, session, name, dims

    @classmethod
    def load(cls, spec: ModelSpec, folder: Path, threads: int | None = None) -> "OnnxEmbedder":
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
        return cls(Tokenizer.from_file(str(tokenizer)), session, name=spec.name, dims=spec.dims)

    def _embed(self, batch: list[str]) -> np.ndarray:
        encs = self._tokenizer.encode_batch(batch)
        ids = np.array([e.ids for e in encs], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
        given = {"input_ids": ids, "attention_mask": mask, "token_type_ids": np.zeros_like(ids)}
        rows = self._session.run([self._output], {n: given[n] for n in self._inputs})[0]
        weights = mask[:, :, None].astype(rows.dtype)
        mean = (rows * weights).sum(axis=1) / np.maximum(weights.sum(axis=1), 1e-9)
        return mean / np.maximum(np.linalg.norm(mean, axis=1, keepdims=True), 1e-12)

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # less padding
        out: list[list[float]] = [[] for _ in texts]
        for start in range(0, len(order), BATCH):
            part = order[start : start + BATCH]
            for i, v in zip(part, self._embed([texts[i] for i in part]), strict=True):
                out[i] = v.tolist()
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._vectors([PASSAGE + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._vectors([QUERY + text])[0]
