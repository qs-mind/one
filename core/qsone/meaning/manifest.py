"""The search models, pinned to an exact Hugging Face commit with each file's size and SHA-256.

These are the very files the search spike measured. Only `tokenizer.json` and the int8 `.onnx`
are fetched.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ModelFile:
    path: str  # inside the repo
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    id: str  # folder name
    kind: Literal["embedder", "reranker"]
    repo: str
    revision: str  # full commit on Hugging Face
    files: tuple[ModelFile, ...]
    licence: str
    dims: int | None  # embedders only
    ram_bytes: int  # measured lean peak (spike §4), for the RAM budget

    @property
    def name(self) -> str:
        """Kept in the project file's meta.embed_model."""
        return f"{self.repo}@{self.revision[:12]}"

    def url(self, f: ModelFile) -> str:
        return f"https://huggingface.co/{self.repo}/resolve/{self.revision}/{f.path}"

    @property
    def size(self) -> int:
        return sum(f.size for f in self.files)


EMBEDDER = ModelSpec(
    id="bge-m3-int8",
    kind="embedder",
    repo="Xenova/bge-m3",
    revision="4de13258303883538bd53b696b452bf8099f0858",
    files=(
        ModelFile(
            "tokenizer.json",
            17_082_821,
            "6710678b12670bc442b99edc952c4d996ae309a7020c1fa0096dd245c2faf790",
        ),
        ModelFile(
            "onnx/model_int8.onnx",
            568_456_694,
            "a206e10e995aa2a833924bcd725ba5dd6c3425cd34bac3cf2b5677cd2a1c51d6",
        ),
    ),
    licence="MIT",
    dims=1024,
    ram_bytes=1_800_000_000,
)

RERANKER = ModelSpec(
    id="bge-reranker-v2-m3-int8",
    kind="reranker",
    repo="onnx-community/bge-reranker-v2-m3-ONNX",
    revision="6f5ff65298512715a1e669753bc754d2bc8f367b",
    files=(
        ModelFile(
            "tokenizer.json",
            17_082_900,
            "8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3",
        ),
        ModelFile(
            "onnx/model_int8.onnx",
            570_727_094,
            "912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d",
        ),
    ),
    licence="Apache-2.0",
    dims=None,
    ram_bytes=1_700_000_000,
)

MODELS = (EMBEDDER, RERANKER)  # 1,173,349,509 bytes in all
